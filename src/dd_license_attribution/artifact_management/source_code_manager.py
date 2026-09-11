# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import logging
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
    list_dir,
    output_from_command,
    path_exists,
    run_command,
    sleep,
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


class NonAccessibleRepository(Exception):
    """Exception raised when a repository is not accessible."""

    pass


class UnauthorizedRepository(Exception):
    """Exception raised when the GitHub token doesn't have enough permissions."""

    pass


def _output_from_git_command(args: list[str], git_env: dict[str, str] | None) -> str:
    if git_env is None:
        return output_from_command(args)
    return output_from_command(
        args, env=git_env, timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS
    )


def _response_headers(github_client: GitHub) -> dict[str, str] | None:
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
      (primary rate limit), or by the message mentioning a rate limit
      (e.g. "You have exceeded a secondary rate limit").

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
    return "rate limit" in str(message).lower()


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
    headers = _response_headers(github_client)
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
        headers = _response_headers(github_client)
    return (status, result, attempt)


def extract_ref(ref: str, url: str, git_env: dict[str, str] | None = None) -> str:
    logger.debug("Extracting ref %s from %s", ref, url)
    split_ref = ref.split("/")
    for i in range(len(split_ref)):
        ref_guess = "/".join(split_ref[: i + 1])
        ls_output = _output_from_git_command(
            ["git", "ls-remote", url, ref_guess], git_env
        )
        if ref_guess in ls_output:
            logger.debug("Found valid ref: %s", ref_guess)
            return ref_guess
    if len(split_ref) > 0:  # may be a hash
        ref_guess = split_ref[0]
        ls_output = _output_from_git_command(["git", "ls-remote", url], git_env)
        if ref_guess in ls_output:
            logger.debug("Found valid ref from hash: %s", ref_guess)
            return ref_guess
    return ""


class RefType(Enum):
    BRANCH = "branch"
    TAG = "tag"
    COMMIT = "commit"


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
        logger.debug(
            "Failed to resolve canonical URLs (status %s), returning: %s", status, url
        )
        original_url = f"{parsed_url.protocol}://{parsed_url.host}/{owner}/{repo}"
        fallback_result = (original_url, None)
        # Transient failures (429, a 403 confirmed as a rate limit by the
        # rate limit headers or, failing that, the message, or 5xx server
        # errors): don't cache the fallback so a later call can retry once
        # they recover. Other failures (e.g. 404 not found, or a permanent
        # 403) are safe to cache.
        if not _is_transient_response(
            status, repository, _response_headers(self.github_client)
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
            status, result, _response_headers(self.github_client)
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
        logger.debug(
            "Cached repository info for %s/%s with status %s", owner, repo, status
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
                    ["git", "ls-remote", "--symref", url, "HEAD"],
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

    def _get_mirror_url_and_ref(
        self,
        original_url: str,
        original_ref_type: RefType,
        original_ref_name: str,
        git_env: dict[str, str] | None = None,
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

        for mirror_map in self.mirrors:
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
                    if effective_ref_type != RefType.BRANCH:
                        raise NotImplementedError(
                            f"Mirror reference type {effective_ref_type} is not yet implemented. Only branch-to-branch mapping is supported."
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

    def get_code(
        self,
        resource_url: str,
        force_update: bool = False,
        skip_canonical_lookup: bool = False,
    ) -> SourceCodeReference | None:
        logger.debug("Getting code for resource URL: %s", resource_url)

        original_parsed_url = parse_git_url(resource_url)
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
        branch = "default_branch"
        if original_parsed_url.branch:
            # branches are guessed from url, and may fail to be correct specially on tags and branches with slashes
            validated_ref = extract_ref(
                original_parsed_url.branch, repository_url, git_env=git_env
            )
            if validated_ref != "":
                branch = validated_ref
        if original_parsed_url.path_raw.startswith("/tree/"):
            path = original_parsed_url.path_raw.removeprefix(f"/tree/{branch}")
        elif original_parsed_url.path_raw.startswith("/blob/"):
            path = "/".join(
                original_parsed_url.path_raw.removeprefix("/blob/").split("/")[:-1]
            )
            validated_ref = extract_ref(path, repository_url, git_env=git_env)
            if validated_ref != "":
                branch = validated_ref
                path = path.removeprefix(f"{branch}")
        else:
            path = ""
        logger.debug(
            "Using branch: %s and path: %s for repository URL: %s",
            branch,
            path,
            repository_url,
        )
        # Get mirror URL and branch if available
        try:
            effective_repository_url, _, effective_branch, branch = (
                self._get_mirror_url_and_ref(
                    repository_url,
                    RefType.BRANCH,
                    branch,
                    git_env=git_env,
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
                local_branch_path = (
                    f"{self.local_cache_dir}/{time_copy_str}/{owner}-{repo}/{branch}"
                )
                if path_exists(local_branch_path):
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
        local_branch_path = (
            f"{self.local_cache_dir}/{self.timestamped_dir}/{owner}-{repo}/{branch}"
        )

        create_dirs(local_branch_path)
        logger.debug(
            "Cloning repository %s at branch %s to %s",
            effective_repository_url,
            effective_branch,
            local_branch_path,
        )
        clone_command = [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            f"--branch={effective_branch}",
            effective_repository_url,
            local_branch_path,
        ]
        if git_env is None:
            clone_result = run_command(clone_command)
        else:
            clone_result = run_command(
                clone_command, env=git_env, timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS
            )
        if clone_result != 0:
            logger.error(
                "Failed to clone repository %s at branch %s to %s",
                effective_repository_url,
                effective_branch,
                local_branch_path,
            )
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
