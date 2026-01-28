# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")

import pytz
from agithub.GitHub import GitHub
from giturlparse import parse as parse_git_url

from dd_license_attribution.adaptors.os import (
    create_dirs,
    list_dir,
    output_from_command,
    path_exists,
    run_command,
)
from dd_license_attribution.artifact_management.artifact_manager import (
    ArtifactManager,
    SourceCodeReference,
)


class NonAccessibleRepository(Exception):
    """Exception raised when a repository is not accessible."""

    pass


class UnauthorizedRepository(Exception):
    """Exception raised when the GitHub token doesn't have enough permissions."""

    pass


def extract_ref(ref: str, url: str) -> str:
    logger.debug("Extracting ref %s from %s", ref, url)
    split_ref = ref.split("/")
    for i in range(len(split_ref)):
        ref_guess = "/".join(split_ref[: i + 1])
        validated = run_command(
            f"git ls-remote {url} {ref_guess} | grep -q {ref_guess}"
        )
        if validated == 0:
            logger.debug("Found valid ref: %s", ref_guess)
            return ref_guess
    if len(split_ref) > 0:  # may be a hash
        ref_guess = split_ref[0]
        validated = run_command(f"git ls-remote {url} | grep -q {ref_guess}")
        if validated == 0:
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
        status, api_result = self.github_client.repos[owner][repo].get()

        if status == 301 and api_result and "url" in api_result:
            redirect_url = api_result["url"]
            logger.debug("Repository has moved, following redirect: %s", redirect_url)

            # Check if the redirect is still to GitHub
            api_prefix = "https://api.github.com/"
            if redirect_url.startswith(api_prefix):
                path = redirect_url[len(api_prefix) :]
                path_parts = path.split("/")
                endpoint = self.github_client
                for part in path_parts:
                    endpoint = endpoint[part]
                status, api_result = endpoint.get()

        if status == 200 and api_result:
            canonical_repo_url = api_result.get("html_url")
            api_url = api_result.get("url")
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
        self._canonical_urls_cache[url] = fallback_result
        return fallback_result

    def _discover_default_branch(self, url: str) -> str:
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
                output_from_command(f"git ls-remote --symref {url} HEAD")
                .split()[1]
                .removeprefix("refs/heads/")
            )
            logger.debug(
                "Discovered default branch in repository: %s", discovered_branch
            )
            return discovered_branch
        except Exception as e:
            raise NonAccessibleRepository(
                f"Could not discover default branch for {url}"
            ) from e

    def _get_mirror_url_and_ref(
        self, original_url: str, original_ref_type: RefType, original_ref_name: str
    ) -> tuple[str, RefType, str, str]:
        """Get the mirror URL and reference for a given original URL and reference.
        Returns a tuple of (mirror_url, ref_type, effective_ref_name, discovered_branch) where discovered_branch
        is the original branch name if it was discovered, or the original_ref_name if no discovery was needed.
        """
        if original_ref_name == "default_branch":
            try:
                original_ref_name = self._discover_default_branch(original_url)
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
                        original_ref_name = self._discover_default_branch(mirror_url)
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
        return original_url, original_ref_type, original_ref_name, original_ref_name

    def get_code(
        self, resource_url: str, force_update: bool = False
    ) -> SourceCodeReference | None:
        logger.debug("Getting code for resource URL: %s", resource_url)

        original_parsed_url = parse_git_url(resource_url)
        if not original_parsed_url.valid or not original_parsed_url.github:
            return None

        canonical_url, api_url = self.get_canonical_urls(resource_url)
        if api_url is None:
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
            validated_ref = extract_ref(original_parsed_url.branch, repository_url)
            if validated_ref != "":
                branch = validated_ref
        if original_parsed_url.path_raw.startswith("/tree/"):
            path = original_parsed_url.path_raw.removeprefix(f"/tree/{branch}")
        elif original_parsed_url.path_raw.startswith("/blob/"):
            path = "/".join(
                original_parsed_url.path_raw.removeprefix("/blob/").split("/")[:-1]
            )
            validated_ref = extract_ref(path, repository_url)
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
        effective_repository_url, _, effective_branch, branch = (
            self._get_mirror_url_and_ref(repository_url, RefType.BRANCH, branch)
        )
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
        run_command(
            f"git clone -c advice.detachedHead=False --depth 1 --branch={effective_branch} {effective_repository_url} {local_branch_path}"
        )

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
