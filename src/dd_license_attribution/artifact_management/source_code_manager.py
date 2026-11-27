# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import hashlib
import json
import logging
import re
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")

import pytz
from agithub.GitHub import GitHub
from giturlparse import parse as parse_git_url

from dd_license_attribution.adaptors.os import (
    create_dirs,
    current_time,
    is_dir,
    is_file,
    list_dir,
    open_file,
    output_from_command,
    path_exists,
    path_join,
    path_parent,
    real_path,
    remove_file,
    remove_tree,
    rename_path,
    replace_path,
    run_command,
    sleep,
    write_file,
)
from dd_license_attribution.artifact_management.artifact_manager import (
    ArtifactManager,
    SourceCodeReference,
)

NONINTERACTIVE_GIT_ENV = {
    "GIT_TERMINAL_PROMPT": "0",
}
NONINTERACTIVE_GIT_TIMEOUT_SECONDS = 30
GITHUB_API_MAX_RETRIES = 3
GITHUB_API_RETRY_BASE_DELAY_SECONDS = 2.0
GITHUB_API_RETRY_MAX_DELAY_SECONDS = 60.0
GITHUB_API_RETRY_BUFFER_SECONDS = 1.0
GITHUB_API_TRANSIENT_STATUS_CODES = frozenset({500, 502, 503, 504})
# GitHub signals rate limits in 403 response messages in several ways: the
# message may mention a rate limit ("You have exceeded a secondary rate
# limit"), or - for secondary/abuse rate limits - use phrasing that does
# NOT contain the phrase "rate limit" and often carries no Retry-After
# header ("You have triggered an abuse detection mechanism"). Matched
# case-insensitively against the lowercased response message.
GITHUB_RATE_LIMIT_MESSAGE_PHRASES = (
    "rate limit",
    "abuse detection",
    "blocked from the api",
)


class NonAccessibleRepository(Exception):
    """Exception raised when a repository is not accessible."""

    pass


class UnauthorizedRepository(Exception):
    """Exception raised when the GitHub token doesn't have enough permissions."""

    pass


def _repository_identity(parsed_url: Any) -> tuple[str, str, str]:
    # Hostnames are case-insensitive everywhere, GitHub owner/repo names too.
    if parsed_url.github:
        return (
            parsed_url.host.lower(),
            parsed_url.owner.lower(),
            parsed_url.repo.lower(),
        )
    return (parsed_url.host.lower(), parsed_url.owner, parsed_url.repo)


def _output_from_git_command(args: list[str], git_env: dict[str, str] | None) -> str:
    if git_env is None:
        return output_from_command(args)
    return output_from_command(
        args, env=git_env, timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS
    )


def github_response_headers(github_client: GitHub) -> dict[str, str] | None:
    """Return the API client's most recent response headers, if usable.

    The agithub API class exposes getheaders() returning the headers of
    the last performed request (list of (name, value) pairs or a mapping,
    depending on the client version). Tolerate any client implementation
    and return None when the headers cannot be read, so callers can fall
    back to inspecting the response body.

    Args:
        github_client: The GitHub API client instance.

    Returns:
        A lowercase header-name -> value dict, or None when unavailable.
    """
    getheaders = getattr(github_client, "getheaders", None)
    if not callable(getheaders):
        return None
    try:
        raw = getheaders()
    except (AttributeError, TypeError, ValueError):
        return None
    if isinstance(raw, dict):
        return {str(k).lower(): str(v) for k, v in raw.items()}
    items = getattr(raw, "items", None)
    if callable(items):
        try:
            return {str(k).lower(): str(v) for k, v in items()}
        except (AttributeError, TypeError, ValueError):
            return None
    if isinstance(raw, (list, tuple)):
        try:
            return {str(k).lower(): str(v) for k, v in raw}
        except (TypeError, ValueError):
            return None
    return None


def _is_rate_limit_response(
    status: int, result: dict[str, Any] | None, headers: dict[str, str] | None = None
) -> bool:
    """Check whether a GitHub API response is a rate limit response.

    GitHub signals rate limits on API responses in several ways:
    - A 429 (Too Many Requests) response - used for secondary rate limits.
    - A 403 response confirmed as a rate limit by a Retry-After header
      (secondary rate limit), by the X-RateLimit-Remaining header reaching 0
      (primary rate limit), or by the message matching one of the documented
      rate limit phrases (GITHUB_RATE_LIMIT_MESSAGE_PHRASES): either phrasing
      that mentions a rate limit (e.g. "You have exceeded a secondary rate
      limit") or GitHub's secondary/abuse limit phrasing that does not
      ("abuse detection", "blocked from the API") - the latter often
      carries no Retry-After header.

    The X-RateLimit-Remaining header tracks only the PRIMARY quota, so a
    positive value does NOT rule out a secondary rate limit: a positive
    remaining header never overrides the Retry-After header or the message.
    Other 403 responses (e.g. "Resource not accessible by integration") are
    permanent access failures and must not be retried.

    Args:
        status: The HTTP status code of the response.
        result: The parsed response body, if any.
        headers: The response headers if available; None to fall back to
            inspecting the response body message.

    Returns:
        True if the response is a confirmed rate limit response, False
        otherwise (including when a 403 cause cannot be confirmed - such
        responses are treated as permanent failures).
    """
    if status == 429:
        return True
    if status != 403:
        return False
    if headers is not None:
        if headers.get("retry-after") is not None:
            # A 403 carrying Retry-After is a secondary rate limit, even when
            # the primary quota (X-RateLimit-Remaining) is not exhausted.
            return True
        remaining = headers.get("x-ratelimit-remaining")
        if remaining is not None:
            try:
                if int(remaining) <= 0:
                    return True
            except ValueError:
                logger.debug(
                    "Unparseable X-RateLimit-Remaining header value: %s", remaining
                )
    message = result.get("message") if isinstance(result, dict) else None
    message_text = str(message).lower()
    return any(phrase in message_text for phrase in GITHUB_RATE_LIMIT_MESSAGE_PHRASES)


def _advised_retry_delay_seconds(headers: dict[str, str] | None) -> float | None:
    """Compute the server-advised retry wait from rate limit headers.

    Secondary rate limits (429, or a 403 carrying Retry-After) advise a wait
    via the Retry-After header (seconds). Primary rate limits (403 with
    X-RateLimit-Remaining reaching 0) carry X-RateLimit-Reset (unix epoch) -
    the advised wait is until that quota window resets. The reset header
    only tracks the PRIMARY quota window, so it is only consulted when the
    primary quota is actually exhausted; for a secondary rate limit with
    primary quota left it is irrelevant and no advice is derived (callers
    fall back to exponential backoff). A small buffer is added on top of
    the server's advice.

    Args:
        headers: The response headers if available; None when not.

    Returns:
        The advised delay in seconds, or None when the headers carry no
        usable advice.
    """
    if headers is None:
        return None
    retry_after = headers.get("retry-after")
    if retry_after is not None:
        try:
            return float(retry_after) + GITHUB_API_RETRY_BUFFER_SECONDS
        except ValueError:
            logger.debug("Unparseable Retry-After header value: %s", retry_after)
    remaining = headers.get("x-ratelimit-remaining")
    if remaining is None:
        return None
    try:
        if int(remaining) > 0:
            # Primary quota not exhausted: the X-RateLimit-Reset epoch would
            # be bad advice for this response.
            return None
    except ValueError:
        logger.debug("Unparseable X-RateLimit-Remaining header value: %s", remaining)
        return None
    reset = headers.get("x-ratelimit-reset")
    if reset is not None:
        try:
            delay = float(reset) - current_time() + GITHUB_API_RETRY_BUFFER_SECONDS
        except ValueError:
            logger.debug("Unparseable X-RateLimit-Reset header value: %s", reset)
            return None
        if delay > 0:
            return delay
    return None


def _is_transient_response(
    status: int, result: dict[str, Any] | None, headers: dict[str, str] | None
) -> bool:
    """Check whether a GitHub API response is a transient failure.

    Transient failures are rate limit responses (see _is_rate_limit_response)
    or 5xx server errors, which GitHub documents as temporary and safe to
    retry. Everything else (success, 404, permanent 403, 301, ...) is final.

    Args:
        status: The HTTP status code of the response.
        result: The parsed response body, if any.
        headers: The response headers if available.

    Returns:
        True if the response is a transient failure worth retrying.
    """
    if status in GITHUB_API_TRANSIENT_STATUS_CODES:
        return True
    return _is_rate_limit_response(status, result, headers)


def github_api_get_with_retry(
    fetch: Callable[[], tuple[int, dict[str, Any] | None]],
    github_client: GitHub,
) -> tuple[int, dict[str, Any] | None, int]:
    """Perform a GitHub API fetch, retrying transient failures.

    Rate limit responses (a 429, or a 403 confirmed as a rate limit by the
    X-RateLimit-Remaining header or, failing that, the response message)
    are retried following the server-advised timeline when rate limit
    headers are available: Retry-After for secondary rate limits, or until
    the X-RateLimit-Reset epoch for primary ones. 5xx server errors are
    also transient and retried (with exponential backoff - they carry no
    retry advice). When no advice is available the retry uses exponential
    backoff. An advised wait longer than GITHUB_API_RETRY_MAX_DELAY_SECONDS
    is not retried: retrying before the server allows it would be
    aggressive, and blocking a scan for minutes is worse than letting the
    caller fail (transiently - transient failures must not be cached by
    callers).

    Args:
        fetch: Zero-argument callable performing one API request and
            returning its (status, parsed body).
        github_client: The GitHub API client used to read response headers.

    Returns:
        A tuple of (status, result, attempts) - the final (status, parsed
        body) after retries are exhausted or the request succeeds, and the
        number of fetch attempts performed (1 when no retry happened).
    """
    status, result = fetch()
    headers = github_response_headers(github_client)
    attempt = 1
    while (
        _is_transient_response(status, result, headers)
        and attempt < GITHUB_API_MAX_RETRIES
    ):
        # Only rate limit responses carry retry advice: 5xx server errors
        # use the exponential backoff even when rate limit headers (which
        # GitHub sends on every response) happen to be present.
        rate_limited = _is_rate_limit_response(status, result, headers)
        advised_delay = _advised_retry_delay_seconds(headers) if rate_limited else None
        if (
            advised_delay is not None
            and advised_delay > GITHUB_API_RETRY_MAX_DELAY_SECONDS
        ):
            logger.warning(
                "GitHub API rate limit advises waiting %.0f seconds, which "
                "exceeds the %.0f second cap; not retrying this request",
                advised_delay,
                GITHUB_API_RETRY_MAX_DELAY_SECONDS,
            )
            break
        delay = (
            advised_delay
            if advised_delay is not None
            else GITHUB_API_RETRY_BASE_DELAY_SECONDS * (2 ** (attempt - 1))
        )
        logger.warning(
            "GitHub API transient failure (status %s, attempt %d/%d), "
            "retrying in %s seconds...",
            status,
            attempt,
            GITHUB_API_MAX_RETRIES,
            delay,
        )
        sleep(delay)
        attempt += 1
        status, result = fetch()
        headers = github_response_headers(github_client)
    return (status, result, attempt)


class RefType(Enum):
    BRANCH = "branch"
    TAG = "tag"
    COMMIT = "commit"


class _ExtractedRef(str):
    """String subclass returned by `extract_ref` carrying ref type and verification state."""

    ref_type: RefType
    verified: bool

    def __new__(
        cls,
        value: str,
        ref_type: RefType = RefType.BRANCH,
        verified: bool = True,
    ) -> "_ExtractedRef":
        obj = super().__new__(cls, value)
        obj.ref_type = ref_type
        obj.verified = verified
        return obj


def _ls_remote_match_ref_type(ls_output: str, ref_guess: str) -> RefType | None:
    """Return the advertised RefType if `git ls-remote` contains an exact branch/tag named ref_guess."""
    branch_ref = f"refs/heads/{ref_guess}"
    tag_refs = (f"refs/tags/{ref_guess}", f"refs/tags/{ref_guess}^{{}}")
    matched_tag = False
    for line in ls_output.splitlines():
        parts = line.split("\t", 1)
        if len(parts) != 2:
            continue
        ref_name = parts[1].strip()
        if ref_name == branch_ref:
            return RefType.BRANCH
        if ref_name in tag_refs:
            matched_tag = True
    return RefType.TAG if matched_tag else None


def _ls_remote_matches_sha(ls_output: str, sha_guess: str) -> bool:
    """Check whether `git ls-remote` output contains a ref pointing to exact commit sha_guess."""
    for line in ls_output.splitlines():
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[0].strip() == sha_guess:
            return True
    return False


_COMMIT_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{40}$")


def _is_safe_git_ref_name(ref_name: str) -> bool:
    """Validate a Git ref name against git-check-ref-format and path-safety rules."""
    if not ref_name:
        return False
    if ref_name.startswith("/") or ref_name.endswith("/") or ref_name.endswith("."):
        return False
    if ".." in ref_name or "//" in ref_name or "@{" in ref_name or "\\" in ref_name:
        return False
    if any(ord(ch) < 0x20 or ord(ch) == 0x7F or ch in " ~^:?*[" for ch in ref_name):
        return False
    for segment in ref_name.split("/"):
        if (
            not segment
            or segment in (".", "..")
            or segment.startswith(".")
            or segment.endswith(".lock")
        ):
            return False
    return True


def extract_ref(ref: str, url: str, git_env: dict[str, str] | None = None) -> str:
    logger.debug("Extracting Git ref %s", ref)
    split_ref = [segment for segment in ref.split("/") if segment]
    if not split_ref:
        return ""
    candidate_refs = ["/".join(split_ref[:i]) for i in range(len(split_ref), 0, -1)]
    ls_output = _output_from_git_command(
        ["git", "ls-remote", "--", url, *candidate_refs], git_env
    )
    # Probe longest prefix first so slash branches (e.g. "release/v2") win over "release".
    for ref_guess in candidate_refs:
        matched_type = _ls_remote_match_ref_type(ls_output, ref_guess)
        if matched_type is not None:
            logger.debug("Found valid ref: %s", ref_guess)
            return _ExtractedRef(ref_guess, ref_type=matched_type, verified=True)
    # May be a commit hash: reachable historical commits may not be advertised
    # by `git ls-remote`, so accept full 40-char SHAs provisionally and let
    # Git fetch confirm commit existence.
    ref_guess = split_ref[0]
    if _COMMIT_SHA_PATTERN.fullmatch(ref_guess):
        logger.debug("Found provisional full commit SHA ref: %s", ref_guess)
        return _ExtractedRef(ref_guess, ref_type=RefType.COMMIT, verified=False)
    ls_output = _output_from_git_command(["git", "ls-remote", "--", url], git_env)
    if _ls_remote_matches_sha(ls_output, ref_guess):
        logger.debug("Found valid ref from hash: %s", ref_guess)
        return _ExtractedRef(ref_guess, ref_type=RefType.COMMIT, verified=True)
    return ""


def _strip_url_query_and_fragment(url: str) -> str:
    return url.split("#", 1)[0].split("?", 1)[0]


def _sanitize_repo_subpath(path: str) -> str | None:
    """Normalize a repository-relative subpath and reject any `..` traversal.

    Returns "" for the repository root, "/a/b" for a valid nested path, or
    None when any path segment is "..".
    """
    stripped = path.strip("/")
    if not stripped:
        return ""
    parts: list[str] = []
    for part in stripped.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None
        parts.append(part)
    if not parts:
        return ""
    return "/" + "/".join(parts)


@dataclass
class MirrorSpec:
    """Specification for a mirror repository.
    original_url: The original repository URL.
    mirror_url: The URL of the mirror repository.
    ref_mapping: Optional mapping of references.
    This maps (ref_type, ref_name) from the original repository to (ref_type, ref_name) in the mirror.
    It is used to determine how branches, tags, or commits in the original repository map to the mirror.
    For example, if a branch in the original repository is named "main" and in the mirror it is "master",
    the mapping would be {("branch", "main"): ("branch", "master")}.
    This is useful for repositories that have different naming conventions or structures in their mirrors.
    The mapping is optional, and if not provided, the original URL ref spec will be reused as the mirror URL ref spec.
    The ref_mapping is a dictionary where the keys are tuples of (RefType, str) representing the type and name of the
    reference in the original repository,and the values are tuples of (RefType, str) representing the type and name
    of the reference in the mirror.
    Example:
    {
        ("branch", "main"): ("tag", "v0.9"),
        ("tag", "v1.0"): ("branch", "development")
    }
    This means that the "main" branch in the original repository maps to the "v0.9" tag in the mirror, and
    the "v1.0" tag in the original repository maps to the "development" branch in the mirror.
    """

    original_url: str
    mirror_url: str
    ref_mapping: dict[tuple[RefType, str], tuple[RefType, str]] | None = (
        None  # Maps (ref_type, ref_name) to (ref_type, ref_name)
    )


@dataclass(frozen=True)
class _ResolvedRef:
    ref_name: str
    ref_type: RefType = RefType.BRANCH
    mirror_spec: MirrorSpec | None = None
    verified: bool = True


class SourceCodeManager(ArtifactManager):
    def __init__(
        self,
        local_cache_dir: str,
        github_client: GitHub,
        local_cache_ttl: int = 86400,
        mirrors: list[MirrorSpec] | None = None,
    ) -> None:
        super().__init__(local_cache_dir, local_cache_ttl)
        self.mirrors = mirrors or []
        self.github_client = github_client
        self._canonical_urls_cache: dict[str, tuple[str, str | None]] = {}
        self._repository_info_cache: dict[str, tuple[int, dict[str, Any] | None]] = {}
        logger.info(
            "SourceCodeManager initialized with %d mirror(s) with %d seconds TTL.",
            len(self.mirrors),
            self.local_cache_ttl,
        )

    def get_canonical_urls(self, url: str) -> tuple[str, str | None]:
        """Get the canonical repository URL and API URL for a given URL.

        This method resolves redirects for renamed or transferred GitHub repositories (301).

        Args:
            url: The repository URL to resolve (can be any GitHub URL format)

        Returns:
            A tuple of (canonical_repo_url, api_url) where:
            - canonical_repo_url: The canonical repository URL (html_url from GitHub API, or original URL if not GitHub)
            - api_url: The GitHub API URL for the repository (None if not a GitHub repository)

        Examples:
            https://github.com/DataDog/ospo-tools:
            ("https://github.com/DataDog/dd-license-attribution", "https://api.github.com/repos/DataDog/dd-license-attribution")

            https://github.com/DataDog/dd-license-attribution:
            ("https://github.com/DataDog/dd-license-attribution", "https://api.github.com/repos/DataDog/dd-license-attribution")

            https://gitlab.com/some/repo:
            ("https://gitlab.com/some/repo", None)
        """
        # Check cache
        if url in self._canonical_urls_cache:
            logger.debug("Returning cached canonical URLs for: %s", url)
            return self._canonical_urls_cache[url]

        logger.debug("Getting canonical URLs for: %s", url)
        parsed_url = parse_git_url(url)

        if not parsed_url.valid or not parsed_url.github:
            logger.debug("URL is not a GitHub URL: %s", url)
            result = (url, None)
            self._canonical_urls_cache[url] = result
            return result

        owner = parsed_url.owner
        repo = parsed_url.repo
        status, repository = self.get_repository_info(owner, repo)

        if status == 200 and repository:
            canonical_repo_url: str = repository.get("html_url", "")
            api_url: str | None = repository.get("url")
            logger.debug(
                "Resolved canonical URLs - Repo URL: %s, API URL: %s",
                canonical_repo_url,
                api_url,
            )
            canonical_result = (canonical_repo_url, api_url)
            self._canonical_urls_cache[url] = canonical_result
            return canonical_result

        # If we couldn't get the repository information, return the original URL
        logger.warning(
            "Failed to resolve canonical URLs (status %s) for: %s", status, url
        )
        original_url = f"{parsed_url.protocol}://{parsed_url.host}/{owner}/{repo}"
        fallback_result = (original_url, None)
        # Transient failures (429, a 403 confirmed as a rate limit by the
        # rate limit headers or, failing that, the message, or 5xx server
        # errors): don't cache the fallback so a later call can retry once
        # they recover. Other failures (e.g. 404 not found, or a permanent
        # 403) are safe to cache.
        if not _is_transient_response(
            status, repository, github_response_headers(self.github_client)
        ):
            self._canonical_urls_cache[url] = fallback_result
        return fallback_result

    def get_repository_info(
        self, owner: str, repo: str
    ) -> tuple[int, dict[str, Any] | None]:
        """Get repository information from GitHub API with caching.

        This method fetches repository information from the GitHub API and caches the result.
        It automatically follows redirects (301) for renamed or transferred repositories when
        the redirect target is still a GitHub URL. If a redirect points to a non-GitHub URL,
        the 301 status is returned without following.

        Args:
            owner: The repository owner
            repo: The repository name

        Returns:
            A tuple of (status_code, repository_dict) where:
            - status_code: The HTTP status code - typically 200 (success), 404 (not found),
              403 (forbidden), etc. A 301 will only be returned if the redirect is to a
              non-GitHub URL (rare edge case).
            - repository_dict: The repository information dict on success, None on error

        Transient failures - confirmed rate limit responses (a 429, or a 403
        confirmed as a rate limit by the X-RateLimit-Remaining header when
        available, else by the message) and 5xx server errors - are
        retried following the server-advised timeline (Retry-After /
        X-RateLimit-Reset, capped at GITHUB_API_RETRY_MAX_DELAY_SECONDS) or
        exponential backoff when no advice is available: up to
        GITHUB_API_MAX_RETRIES attempts. Transient results are never cached
        so that later callers get a fresh chance once the failure recovers;
        other results (success or permanent errors like 404, including
        non-rate-limit 403 responses) are cached.

        Examples:
            (200, {"html_url": "...", "license": {...}, ...})  # Normal case
            (404, None)  # Repository not found
            (301, {"url": "https://example.com/..."})  # Redirect to non-GitHub URL (rare)
        """
        cache_key = f"{owner}/{repo}"

        # Check cache
        if cache_key in self._repository_info_cache:
            logger.debug("Returning cached repository info for: %s/%s", owner, repo)
            return self._repository_info_cache[cache_key]

        logger.debug("Fetching repository info for: %s/%s", owner, repo)
        status, result, attempts = github_api_get_with_retry(
            lambda: self._fetch_repository_info(owner, repo), self.github_client
        )

        if _is_transient_response(
            status, result, github_response_headers(self.github_client)
        ):
            # Transient failures (rate limits, 5xx server errors): don't
            # cache them so a later caller can retry once they recover.
            logger.error(
                "GitHub API transient failure for %s/%s after %d attempts",
                owner,
                repo,
                attempts,
            )
            return (status, result)

        # Cache the result (including permanent errors like 404 and permanent
        # 403 responses) and return
        cached_result = (status, result)
        self._repository_info_cache[cache_key] = cached_result
        if status != 200:
            # A non-transient failure (permanent 403, 404, ...): cached, so
            # every later lookup for this owner/repo silently returns the
            # failure. Log at INFO so downstream skips stay diagnosable at
            # the default log level.
            logger.info(
                "Cached repository info failure for %s/%s with status %s",
                owner,
                repo,
                status,
            )
        else:
            logger.debug(
                "Cached repository info for %s/%s with status %s",
                owner,
                repo,
                status,
            )
        return cached_result

    def _fetch_repository_info(
        self, owner: str, repo: str
    ) -> tuple[int, dict[str, Any] | None]:
        """Perform a single GitHub API repository lookup, following 301 redirects.

        Follows redirects for renamed/transferred repositories when the redirect
        target is still a GitHub URL. If a redirect points to a non-GitHub URL,
        the 301 status is returned without following.

        Args:
            owner: The repository owner
            repo: The repository name

        Returns:
            A tuple of (status_code, repository_dict) for the (possibly
            redirect-resolved) lookup.
        """
        status, result = self.github_client.repos[owner][repo].get()

        # Handle redirects (301) for renamed/transferred repositories
        if status == 301 and result and "url" in result:
            redirect_url = result["url"]
            logger.debug(
                "Repository %s/%s has moved, following redirect: %s",
                owner,
                repo,
                redirect_url,
            )

            # Check if the redirect is still to GitHub
            api_prefix = "https://api.github.com/"
            if redirect_url.startswith(api_prefix):
                path = redirect_url[len(api_prefix) :]
                path_parts = path.split("/")
                endpoint = self.github_client
                for part in path_parts:
                    endpoint = endpoint[part]
                status, result = endpoint.get()

        return (status, result)

    def _discover_default_branch(
        self, url: str, git_env: dict[str, str] | None = None
    ) -> str:
        """Discover the default branch for a repository.
        Args:
            url: The URL of the repository to check
        Returns:
            The name of the default branch
        Raises:
            NonAccessibleRepository: If the default branch cannot be discovered
        """
        try:
            discovered_branch = (
                _output_from_git_command(
                    ["git", "ls-remote", "--symref", "--", url, "HEAD"],
                    git_env,
                )
                .split()[1]
                .removeprefix("refs/heads/")
            )
            logger.debug(
                "Discovered default branch in repository: %s", discovered_branch
            )
            return discovered_branch
        except (OSError, IndexError) as e:
            raise NonAccessibleRepository(
                f"Could not discover default branch for {url}"
            ) from e

    def remaps_default_branch(self, repository_url: str) -> bool:
        """Whether a mirror ref_mapping replaces the default branch of a repository.

        When it does, the code analyzed for the repository is not its default
        branch, so default-branch-only data (e.g. the GitHub dependency graph
        SBOM) does not describe it.

        Args:
            repository_url: The canonical repository URL, as matched against
                MirrorSpec.original_url.

        Returns:
            True if a mirror maps the repository's default branch to another
            ref. When the default branch cannot be resolved, True if the
            mirror maps any branch, since it may be the default one.
        """
        mirror = next(
            (m for m in self.mirrors if m.original_url == repository_url),
            None,
        )
        if mirror is None or not mirror.ref_mapping:
            return False

        default_branch: str | None = None
        parsed_url = parse_git_url(repository_url)
        parsed_mirror_url = parse_git_url(mirror.mirror_url)
        # Compared by host/owner/repo so a token in the mirror URL doesn't count
        # as a different repository.
        same_repository = (
            parsed_url.valid
            and parsed_mirror_url.valid
            and _repository_identity(parsed_mirror_url)
            == _repository_identity(parsed_url)
        )
        if parsed_url.valid and parsed_url.github:
            status, repository = self.get_repository_info(
                parsed_url.owner, parsed_url.repo
            )
            if status == 200 and repository:
                default_branch = repository.get("default_branch")

        for (ref_type, ref_name), target_ref in mirror.ref_mapping.items():
            # A same-repository identity mapping still checks out the original
            # branch, so it doesn't replace it.
            if same_repository and target_ref == (ref_type, ref_name):
                continue
            if ref_type == RefType.BRANCH and (
                default_branch is None or ref_name == default_branch
            ):
                return True
        return False

    def _get_mirror_url_and_ref(
        self,
        original_url: str,
        original_ref_type: RefType,
        original_ref_name: str,
        git_env: dict[str, str] | None = None,
        preferred_mirror: MirrorSpec | None = None,
    ) -> tuple[str, RefType, str, str]:
        """Get the mirror URL and reference for a given original URL and reference.
        Returns a tuple of (mirror_url, ref_type, effective_ref_name, discovered_branch) where discovered_branch
        is the original branch name if it was discovered, or the original_ref_name if no discovery was needed.
        """
        if original_ref_name == "default_branch":
            try:
                original_ref_name = self._discover_default_branch(
                    original_url, git_env=git_env
                )
            except NonAccessibleRepository as e:
                # ignoring the failure, we will try with the mirror url if found next
                logger.debug(
                    "Failed to discover default branch for original repository %s: %s",
                    original_url,
                    str(e),
                )

        candidate_mirrors = (
            [preferred_mirror] if preferred_mirror is not None else self.mirrors
        )
        for mirror_map in candidate_mirrors:
            if mirror_map.original_url == original_url:
                logger.debug(
                    "Found mirror definition for %s: %s",
                    original_url,
                    mirror_map.mirror_url,
                )
                mirror_url = mirror_map.mirror_url
                if original_ref_name == "default_branch":
                    try:
                        original_ref_name = self._discover_default_branch(
                            mirror_url, git_env=git_env
                        )
                    except NonAccessibleRepository as e:
                        # ignoring the failure, we will try with the mirror url if found next
                        logger.error(
                            "Failed to discover default branch for mirror repository %s: %s",
                            mirror_url,
                            str(e),
                        )
                        raise NonAccessibleRepository(
                            f"Could not discover default branch for neither original repository {original_url} nor mirror repository {mirror_url}"
                        ) from e

                if (
                    mirror_map.ref_mapping
                    and (original_ref_type, original_ref_name) in mirror_map.ref_mapping
                ):
                    effective_ref_type, effective_ref_name = mirror_map.ref_mapping[
                        (original_ref_type, original_ref_name)
                    ]
                    logger.debug(
                        "Mapped %s:%s to mirror %s:%s in %s",
                        original_ref_type,
                        original_ref_name,
                        effective_ref_type,
                        effective_ref_name,
                        mirror_url,
                    )
                    if effective_ref_type == RefType.COMMIT:
                        raise NotImplementedError(
                            f"Mirror reference type {effective_ref_type} is not yet implemented. Only branch and tag mapping targets are supported."
                        )
                    return (
                        mirror_url,
                        effective_ref_type,
                        effective_ref_name,
                        original_ref_name,
                    )
                return (
                    mirror_url,
                    original_ref_type,
                    original_ref_name,
                    original_ref_name,
                )
        if original_ref_name == "default_branch":
            raise NonAccessibleRepository(
                f"Could not discover default branch for {original_url}"
            )
        return original_url, original_ref_type, original_ref_name, original_ref_name

    def _is_within_cache_dir(self, path: str) -> bool:
        cache_root = real_path(self.local_cache_dir)
        resolved = real_path(path)
        return resolved != cache_root and resolved.startswith(path_join(cache_root, ""))

    @staticmethod
    def _is_within_checkout_root(checkout_root: str, path: str) -> bool:
        root = real_path(checkout_root)
        resolved = real_path(path)
        return resolved == root or resolved.startswith(path_join(root, ""))

    def _get_staging_clone_path(self, repository_cache_path: str) -> str:
        return path_join(repository_cache_path, f".checkout-staging-{uuid.uuid4().hex}")

    @staticmethod
    def _get_ref_pointer_path(repository_cache_path: str, branch: str) -> str:
        digest = hashlib.sha256(branch.encode("utf-8")).hexdigest()
        return path_join(repository_cache_path, f".checkout-ref-{digest}")

    def _get_cached_checkout_path(self, repository_cache_path: str, branch: str) -> str:
        legacy_path = path_join(repository_cache_path, branch)
        pointer = self._get_ref_pointer_path(repository_cache_path, branch)
        if not self._is_within_cache_dir(pointer) or not is_file(pointer):
            return legacy_path
        try:
            name = open_file(pointer).strip()
        except (OSError, UnicodeError):
            return legacy_path
        if re.fullmatch(r"\.checkout-[0-9a-f]{32}", name) is None:
            return legacy_path
        target = path_join(repository_cache_path, name)
        if (
            self._is_within_cache_dir(target)
            and self._is_within_checkout_root(repository_cache_path, target)
            and is_dir(path_join(target, ".git"))
        ):
            return target
        return legacy_path

    def _publish_ref_pointer(
        self, repository_cache_path: str, branch: str, checkout_name: str
    ) -> bool:
        pointer = self._get_ref_pointer_path(repository_cache_path, branch)
        temporary = path_join(
            repository_cache_path, f".checkout-pointer-{uuid.uuid4().hex}"
        )
        if not self._is_within_cache_dir(pointer) or not self._is_within_cache_dir(
            temporary
        ):
            return False
        try:
            write_file(temporary, checkout_name)
            replace_path(temporary, pointer)
        except OSError:
            try:
                remove_file(temporary)
            except OSError:
                pass
            return False
        return True

    def _publish_staging_checkout(self, staging_path: str, target_path: str) -> bool:
        """Publish a new immutable checkout without moving an existing reader's path."""
        if not is_dir(staging_path):
            return is_dir(path_join(target_path, ".git"))
        try:
            parent = path_parent(target_path)
            if not is_dir(parent):
                create_dirs(parent)
            rename_path(staging_path, target_path)
        except OSError:
            if self._is_within_cache_dir(staging_path):
                remove_tree(staging_path)
            return is_dir(path_join(target_path, ".git"))
        return True

    def _extract_ref_with_mirror_fallback(
        self,
        ref: str,
        repository_url: str,
        git_env: dict[str, str] | None,
    ) -> _ResolvedRef | None:
        failures: list[OSError] = []

        def try_extract(candidate: str, url: str) -> str:
            try:
                return extract_ref(candidate, url, git_env=git_env)
            except OSError as error:
                failures.append(error)
                return ""

        def target_exists(
            mirror: MirrorSpec, target_type: RefType, target_ref: str
        ) -> bool:
            if target_type not in (
                RefType.BRANCH,
                RefType.TAG,
            ) or not _is_safe_git_ref_name(target_ref):
                return False
            namespace = "heads" if target_type == RefType.BRANCH else "tags"
            qualified_ref = f"refs/{namespace}/{target_ref}"
            try:
                output = _output_from_git_command(
                    ["git", "ls-remote", "--", mirror.mirror_url, qualified_ref],
                    git_env,
                )
            except OSError as error:
                failures.append(error)
                return False
            return any(
                line.partition("\t")[2].strip() == qualified_ref
                for line in output.splitlines()
            )

        validated_ref = try_extract(ref, repository_url)
        if validated_ref != "" and _is_safe_git_ref_name(validated_ref):
            source = _ResolvedRef(
                ref_name=str(validated_ref),
                ref_type=getattr(validated_ref, "ref_type", RefType.BRANCH),
                verified=getattr(validated_ref, "verified", True),
            )
            if source.ref_type == RefType.COMMIT:
                return source
            source_key = (source.ref_type, source.ref_name)
            mirrors = [m for m in self.mirrors if m.original_url == repository_url]
            if not any(m.ref_mapping and source_key in m.ref_mapping for m in mirrors):
                return source
            for mirror in mirrors:
                mapping = mirror.ref_mapping or {}
                target_type, target_ref = mapping.get(source_key, source_key)
                if target_type == RefType.COMMIT:
                    raise NotImplementedError(
                        f"Mirror reference type {target_type} is not yet implemented. Only branch and tag mapping targets are supported."
                    )
                if target_exists(mirror, target_type, target_ref):
                    return _ResolvedRef(
                        ref_name=source.ref_name,
                        ref_type=source.ref_type,
                        mirror_spec=mirror,
                        verified=source.verified,
                    )
            if failures:
                raise failures[-1]
            return None
        split_ref = [segment for segment in ref.split("/") if segment]
        candidate_refs = ["/".join(split_ref[:i]) for i in range(len(split_ref), 0, -1)]
        for mirror_map in self.mirrors:
            if mirror_map.original_url != repository_url:
                continue
            validated_ref = try_extract(ref, mirror_map.mirror_url)
            for ref_guess in candidate_refs:
                if not _is_safe_git_ref_name(ref_guess):
                    continue
                has_mapping = False
                if mirror_map.ref_mapping:
                    for ref_type in (RefType.COMMIT, RefType.BRANCH, RefType.TAG):
                        if (
                            ref_type == RefType.COMMIT
                            and not _COMMIT_SHA_PATTERN.fullmatch(ref_guess)
                        ):
                            continue
                        mapped = mirror_map.ref_mapping.get((ref_type, ref_guess))
                        if mapped is None:
                            continue
                        has_mapping = True
                        target_type, target_ref = mapped
                        if target_exists(mirror_map, target_type, target_ref):
                            return _ResolvedRef(
                                ref_name=ref_guess,
                                ref_type=ref_type,
                                mirror_spec=mirror_map,
                                verified=ref_type != RefType.COMMIT,
                            )
                if has_mapping:
                    break
                if ref_guess == validated_ref:
                    return _ResolvedRef(
                        ref_name=str(validated_ref),
                        ref_type=getattr(validated_ref, "ref_type", RefType.BRANCH),
                        mirror_spec=mirror_map,
                        verified=getattr(validated_ref, "verified", True),
                    )
        if failures:
            raise failures[-1]
        return None

    def _resolve_ref_and_path(
        self,
        original_parsed_url: Any,
        repository_url: str,
        git_env: dict[str, str] | None,
    ) -> tuple[str, str | None, RefType, MirrorSpec | None, bool]:
        """Split a parsed GitHub URL into its ref, sanitized subdirectory, ref type, matched mirror, and verification state.

        Returns `(branch, None, ...)` if the path contains a `..` traversal segment
        or if a `/tree/` or `/blob/` URL's ref cannot be resolved.
        """
        branch = "default_branch"
        resolved_ref_type = RefType.BRANCH
        matched_mirror: MirrorSpec | None = None
        verified = True
        if original_parsed_url.branch:
            # branches are guessed from url, and may fail to be correct specially on tags and branches with slashes
            resolved_ref = self._extract_ref_with_mirror_fallback(
                original_parsed_url.branch, repository_url, git_env=git_env
            )
            if resolved_ref is not None:
                branch = resolved_ref.ref_name
                resolved_ref_type = resolved_ref.ref_type
                matched_mirror = resolved_ref.mirror_spec
                verified = resolved_ref.verified
        if original_parsed_url.path_raw.startswith("/tree/"):
            if branch == "default_branch":
                return branch, None, resolved_ref_type, matched_mirror, False
            segments = [
                segment
                for segment in original_parsed_url.path_raw.removeprefix(
                    "/tree/"
                ).split("/")
                if segment
            ]
            branch_parts = branch.split("/")
            if segments[: len(branch_parts)] != branch_parts:
                return branch, None, resolved_ref_type, matched_mirror, False
            raw_path = "/".join(segments[len(branch_parts) :])
            return (
                branch,
                _sanitize_repo_subpath(raw_path),
                resolved_ref_type,
                matched_mirror,
                verified,
            )
        if original_parsed_url.path_raw.startswith("/blob/"):
            blob_segments = [
                segment
                for segment in original_parsed_url.path_raw.removeprefix(
                    "/blob/"
                ).split("/")
                if segment
            ][:-1]
            blob_dir = "/".join(blob_segments)
            resolved_ref = self._extract_ref_with_mirror_fallback(
                blob_dir, repository_url, git_env=git_env
            )
            if resolved_ref is None:
                return branch, None, resolved_ref_type, matched_mirror, False
            branch = resolved_ref.ref_name
            resolved_ref_type = resolved_ref.ref_type
            matched_mirror = resolved_ref.mirror_spec
            verified = resolved_ref.verified
            branch_parts = branch.split("/")
            if blob_segments[: len(branch_parts)] != branch_parts:
                return branch, None, resolved_ref_type, matched_mirror, False
            raw_path = "/".join(blob_segments[len(branch_parts) :])
            return (
                branch,
                _sanitize_repo_subpath(raw_path),
                resolved_ref_type,
                matched_mirror,
                verified,
            )
        return branch, "", resolved_ref_type, matched_mirror, verified

    def _checkout_ref(
        self,
        url: str,
        ref_type: RefType,
        ref_name: str,
        destination: str,
        git_env: dict[str, str] | None,
        fetch_only: bool = False,
    ) -> bool:
        if ref_type in (RefType.TAG, RefType.COMMIT) or fetch_only:
            if ref_type == RefType.TAG:
                refspec = f"refs/tags/{ref_name}:refs/tags/{ref_name}"
            elif ref_type == RefType.BRANCH:
                refspec = f"refs/heads/{ref_name}"
            else:
                refspec = ref_name
            fetch = ["git", "fetch"]
            checkout = ["git", "-c", "advice.detachedHead=False", "checkout"]
            if fetch_only:
                fetch.append("--force")
                checkout.append("--force")
            commands = [
                ["git", "init", "--quiet"],
                ["git", "config", "remote.origin.url", url],
                [*fetch, "--depth", "1", "origin", refspec],
                [*checkout, "FETCH_HEAD"],
            ]
            if fetch_only:
                commands.append(["git", "clean", "-ffdx"])
            kwargs: dict[str, Any] = {"cwd": destination}
        else:
            commands = [
                [
                    "git",
                    "clone",
                    "-c",
                    "advice.detachedHead=False",
                    "--depth",
                    "1",
                    f"--branch={ref_name}",
                    url,
                    destination,
                ]
            ]
            kwargs = {}
        if git_env is not None:
            kwargs["env"] = git_env
        if git_env is not None or fetch_only:
            kwargs["timeout"] = NONINTERACTIVE_GIT_TIMEOUT_SECONDS
        for command in commands:
            if run_command(command, **kwargs) != 0:
                return False
        return True

    def _record_mapped_commit(
        self,
        checkout: str,
        source_ref: str,
        target: tuple[str, RefType, str],
        git_env: dict[str, str] | None,
    ) -> bool:
        try:
            commit = output_from_command(
                ["git", "rev-parse", "--verify", "HEAD"],
                cwd=checkout,
                env=git_env,
                timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
            ).strip()
        except OSError:
            return False
        if not _COMMIT_SHA_PATTERN.fullmatch(commit):
            return False
        url, ref_type, ref_name = target
        provenance = json.dumps([source_ref, url, ref_type.value, ref_name, commit])
        return (
            run_command(
                ["git", "config", "--local", "ddla.resolved-ref", provenance],
                cwd=checkout,
                env=git_env,
                timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
            )
            == 0
        )

    def _cached_commit_matches_mapping(
        self,
        checkout: str,
        source_ref: str,
        commit: str,
        candidates: list[tuple[str, RefType, str]],
        git_env: dict[str, str] | None,
    ) -> bool:
        if not _COMMIT_SHA_PATTERN.fullmatch(commit):
            return False
        candidates = [
            candidate
            for candidate in candidates
            if candidate[1] in (RefType.BRANCH, RefType.TAG)
        ]
        if not candidates:
            return False
        try:
            provenance = json.loads(
                output_from_command(
                    ["git", "config", "--local", "--get", "ddla.resolved-ref"],
                    cwd=checkout,
                    env=git_env,
                    timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
                )
            )
        except (OSError, ValueError):
            return False
        if (
            not isinstance(provenance, list)
            or len(provenance) != 5
            or not all(isinstance(value, str) for value in provenance)
            or provenance[0] != source_ref
            or provenance[4].lower() != commit.lower()
        ):
            return False
        return any(
            provenance[1:4] == [url, ref_type.value, ref_name]
            for url, ref_type, ref_name in candidates
        )

    def get_code(
        self,
        resource_url: str,
        force_update: bool = False,
        skip_canonical_lookup: bool = False,
    ) -> SourceCodeReference | None:
        logger.debug("Getting code for resource URL: %s", resource_url)

        original_parsed_url = parse_git_url(_strip_url_query_and_fragment(resource_url))
        if not original_parsed_url.valid or not original_parsed_url.github:
            return None

        if skip_canonical_lookup:
            canonical_url = (
                f"{original_parsed_url.protocol}://{original_parsed_url.host}/"
                f"{original_parsed_url.owner}/{original_parsed_url.repo}"
            )
            api_url = None
            git_env = NONINTERACTIVE_GIT_ENV
        else:
            canonical_url, api_url = self.get_canonical_urls(resource_url)
            git_env = None

        if api_url is None and not skip_canonical_lookup:
            logger.debug(
                "Could not resolve canonical URL for %s, not a GitHub repository",
                resource_url,
            )
            return None

        parsed_url = parse_git_url(canonical_url)
        if not parsed_url.valid or not parsed_url.github:
            return None

        owner = parsed_url.owner
        repo = parsed_url.repo
        repository_url = canonical_url

        logger.debug(
            "Resolved canonical repository URL: %s with owner: %s, repo: %s",
            repository_url,
            owner,
            repo,
        )
        try:
            branch, path, resolved_ref_type, matched_mirror, _verified_ref = (
                self._resolve_ref_and_path(original_parsed_url, repository_url, git_env)
            )
        except OSError:
            logger.warning("Failed to resolve ref/path for %s", resource_url)
            return None
        if path is None or not _is_safe_git_ref_name(branch):
            return None
        commit_checkout = resolved_ref_type == RefType.COMMIT
        logger.debug(
            "Using branch: %s and path: %s for repository URL: %s",
            branch,
            path,
            repository_url,
        )
        # Get mirror URL and branch if available
        try:
            effective_repository_url, effective_ref_type, effective_branch, branch = (
                self._get_mirror_url_and_ref(
                    repository_url,
                    resolved_ref_type,
                    branch,
                    git_env=git_env,
                    preferred_mirror=matched_mirror,
                )
            )
        except NonAccessibleRepository as e:
            logger.error(
                "Failed to resolve repository branch for %s: %s", resource_url, e
            )
            return None
        logger.debug(
            "Effective repository URL: %s, effective branch: %s",
            effective_repository_url,
            effective_branch,
        )

        candidates = [(effective_repository_url, effective_ref_type, effective_branch)]
        if commit_checkout:
            for mirror in self.mirrors:
                if mirror.original_url != repository_url:
                    continue
                try:
                    candidate_url, candidate_type, candidate_ref, _ = (
                        self._get_mirror_url_and_ref(
                            repository_url,
                            resolved_ref_type,
                            branch,
                            git_env=git_env,
                            preferred_mirror=mirror,
                        )
                    )
                except (NonAccessibleRepository, NotImplementedError):
                    continue
                candidate = (candidate_url, candidate_type, candidate_ref)
                if candidate not in candidates:
                    candidates.append(candidate)

        cached_timestamps = list_dir(self.local_cache_dir)
        cached_timestamps.sort(reverse=True)
        if not force_update:
            # check if there is a cache
            logger.debug(
                "Checking local cache for %s/%s at branch %s.", owner, repo, branch
            )
            for time_copy_str in cached_timestamps:
                time_copy = datetime.strptime(time_copy_str, "%Y%m%d_%H%M%SZ").replace(
                    tzinfo=pytz.UTC
                )
                if (self.setup_time - time_copy).total_seconds() > self.local_cache_ttl:
                    break
                repository_cache_path = (
                    f"{self.local_cache_dir}/{time_copy_str}/{owner}-{repo}"
                )
                local_branch_path = self._get_cached_checkout_path(
                    repository_cache_path, branch
                )
                if not self._is_within_cache_dir(local_branch_path):
                    continue
                if path_exists(local_branch_path):
                    if not is_dir(path_join(local_branch_path, ".git")):
                        continue
                    if resolved_ref_type == RefType.COMMIT:
                        try:
                            cached_commit = output_from_command(
                                ["git", "rev-parse", "--verify", "HEAD"],
                                cwd=local_branch_path,
                                env=git_env,
                                timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
                            ).strip()
                        except OSError:
                            continue
                        if (
                            effective_ref_type != RefType.COMMIT
                            or cached_commit.lower() != branch.lower()
                        ) and not self._cached_commit_matches_mapping(
                            local_branch_path,
                            branch,
                            cached_commit,
                            candidates,
                            git_env,
                        ):
                            continue
                    local_full_path = f"{local_branch_path}{path}"
                    if path and (
                        not is_dir(local_full_path)
                        or not self._is_within_checkout_root(
                            local_branch_path, local_full_path
                        )
                    ):
                        return None
                    logger.debug(
                        "Found cached branch %s for %s/%s at %s",
                        branch,
                        owner,
                        repo,
                        local_branch_path,
                    )
                    return SourceCodeReference(
                        repo_url=repository_url,
                        branch=branch,
                        local_root_path=f"{local_branch_path}",
                        local_full_path=f"{local_branch_path}{path}",
                    )
        # we need to clone
        repository_cache_path = (
            f"{self.local_cache_dir}/{self.timestamped_dir}/{owner}-{repo}"
        )
        checkout_name = f".checkout-{uuid.uuid4().hex}"
        local_branch_path = path_join(repository_cache_path, checkout_name)
        staging_branch_path = self._get_staging_clone_path(repository_cache_path)
        if not self._is_within_cache_dir(
            local_branch_path
        ) or not self._is_within_cache_dir(staging_branch_path):
            return None
        create_dirs(staging_branch_path)
        logger.debug(
            "Cloning repository %s at branch %s to %s",
            effective_repository_url,
            effective_branch,
            local_branch_path,
        )
        clone_result = 1
        for attempt, (
            effective_repository_url,
            effective_ref_type,
            effective_branch,
        ) in enumerate(candidates):
            if attempt:
                if not self._is_within_cache_dir(staging_branch_path):
                    return None
                remove_tree(staging_branch_path)
                staging_branch_path = self._get_staging_clone_path(
                    repository_cache_path
                )
                if not self._is_within_cache_dir(staging_branch_path):
                    return None
                create_dirs(staging_branch_path)
            if self._checkout_ref(
                effective_repository_url,
                effective_ref_type,
                effective_branch,
                staging_branch_path,
                git_env,
                fetch_only=commit_checkout,
            ):
                clone_result = 0
                break
        if clone_result != 0:
            if self._is_within_cache_dir(staging_branch_path):
                remove_tree(staging_branch_path)
            logger.error(
                "Failed to clone repository %s at branch %s to %s",
                effective_repository_url,
                effective_branch,
                local_branch_path,
            )
            return None

        if (
            resolved_ref_type == RefType.COMMIT
            and effective_ref_type in (RefType.BRANCH, RefType.TAG)
            and not self._record_mapped_commit(
                staging_branch_path,
                branch,
                (effective_repository_url, effective_ref_type, effective_branch),
                git_env,
            )
        ):
            if self._is_within_cache_dir(staging_branch_path):
                remove_tree(staging_branch_path)
            return None

        if not self._publish_staging_checkout(staging_branch_path, local_branch_path):
            logger.error("Failed to publish checkout for %s", repository_url)
            return None
        if not self._publish_ref_pointer(repository_cache_path, branch, checkout_name):
            logger.error("Failed to publish checkout pointer for %s", repository_url)
            return None
        local_full_path = f"{local_branch_path}{path}"
        if path and (
            not is_dir(local_full_path)
            or not self._is_within_checkout_root(local_branch_path, local_full_path)
        ):
            return None

        logger.debug(
            "Cloned repository %s at branch %s to %s",
            effective_repository_url,
            effective_branch,
            local_branch_path,
        )
        return SourceCodeReference(
            repo_url=repository_url,
            branch=branch,
            local_root_path=f"{local_branch_path}",
            local_full_path=f"{local_branch_path}{path}",
        )
