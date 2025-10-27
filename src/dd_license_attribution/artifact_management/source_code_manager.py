# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import logging

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional

import pytz
from giturlparse import parse as parse_git_url

from dd_license_attribution.adaptors.os import (
    create_dirs,
    expand_user_path,
    get_absolute_path,
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
    logger.debug(f"Extracting ref {ref} from {url}")
    split_ref = ref.split("/")
    for i in range(len(split_ref)):
        ref_guess = "/".join(split_ref[: i + 1])
        validated = run_command(
            f"git ls-remote {url} {ref_guess} | grep -q {ref_guess}"
        )
        if validated == 0:
            logger.debug(f"Found valid ref: {ref_guess}")
            return ref_guess
    if len(split_ref) > 0:  # may be a hash
        ref_guess = split_ref[0]
        validated = run_command(f"git ls-remote {url} | grep -q {ref_guess}")
        if validated == 0:
            logger.debug(f"Found valid ref from hash: {ref_guess}")
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
    ref_mapping: Optional[dict[tuple[RefType, str], tuple[RefType, str]]] = (
        None  # Maps (ref_type, ref_name) to (ref_type, ref_name)
    )


class SourceCodeManager(ArtifactManager):
    def __init__(
        self,
        local_cache_dir: str,
        local_cache_ttl: int = 86400,
        mirrors: Optional[list[MirrorSpec]] = None,
    ) -> None:
        super().__init__(local_cache_dir, local_cache_ttl)
        self.mirrors = mirrors or []
        logger.info(
            f"SourceCodeManager initialized with {len(self.mirrors)} mirror(s) with {self.local_cache_ttl} seconds TTL."
        )

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
                f"Discovered default branch in repository: {discovered_branch}"
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
                    f"Failed to discover default branch for original repository {original_url}: {str(e)}"
                )

        for mirror_map in self.mirrors:
            if mirror_map.original_url == original_url:
                logger.debug(
                    f"Found mirror definition for {original_url}: {mirror_map.mirror_url}"
                )
                mirror_url = mirror_map.mirror_url
                if original_ref_name == "default_branch":
                    try:
                        original_ref_name = self._discover_default_branch(mirror_url)
                    except NonAccessibleRepository as e:
                        # ignoring the failure, we will try with the mirror url if found next
                        logger.error(
                            f"Failed to discover default branch for mirror repository {mirror_url}: {str(e)}"
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
                        f"Mapped {original_ref_type}:{original_ref_name} to mirror {effective_ref_type}:{effective_ref_name} in {mirror_url}"
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

    def _handle_local_path(self, local_path: str) -> SourceCodeReference | None:
        """Handle a local git repository path.
        Args:
            local_path: Path to the local git repository (should already be expanded)
        Returns:
            SourceCodeReference pointing to the local path, or None if invalid
        """
        # Normalize the path (resolve relative paths, symlinks, etc.)
        local_path = get_absolute_path(expand_user_path(local_path))

        # Verify it's a git repository by checking for .git directory
        git_dir = f"{local_path}/.git"
        if not path_exists(git_dir):
            logger.error(
                f"Path {local_path} is not a git repository (no .git directory found)"
            )
            raise NonAccessibleRepository(f"Path {local_path} is not a git repository")

        # Try to extract the repository URL from git config
        try:
            remote_url = output_from_command(
                f"cd {local_path} && git config --get remote.origin.url"
            ).strip()
            logger.debug(f"Extracted remote URL from local repo: {remote_url}")
        except Exception as e:
            logger.warning(f"Could not extract remote URL from local repository: {e}")
            remote_url = f"file://{local_path}"

        # Try to get the current branch name
        try:
            branch = output_from_command(
                f"cd {local_path} && git rev-parse --abbrev-ref HEAD"
            ).strip()
            logger.debug(f"Extracted branch from local repo: {branch}")
        except Exception as e:
            logger.warning(f"Could not extract branch from local repository: {e}")
            branch = "unknown"

        logger.info(f"Using local repository at {local_path} (branch: {branch})")

        return SourceCodeReference(
            repo_url=remote_url,
            branch=branch,
            local_root_path=local_path,
            local_full_path=local_path,
        )

    def get_code(
        self, resource_url: str, force_update: bool = False
    ) -> SourceCodeReference | None:
        logger.debug(f"Getting code for resource URL: {resource_url}")

        # Check if resource_url is a local path
        # Expand ~ and make path absolute before checking
        expanded_path = expand_user_path(resource_url)
        if path_exists(expanded_path):
            logger.debug(f"Detected local path: {expanded_path}")
            return self._handle_local_path(expanded_path)

        parsed_url = parse_git_url(resource_url)
        if not parsed_url.valid:
            return None
        if not parsed_url.github:  # Only GitHub supported for now
            return None
        owner = parsed_url.owner
        repo = parsed_url.repo
        repository_url = f"{parsed_url.protocol}://{parsed_url.host}/{parsed_url.owner}/{parsed_url.repo}"
        logger.debug(
            f"Parsed repository URL: {repository_url} with owner: {owner}, repo: {repo}"
        )
        branch = "default_branch"
        if parsed_url.branch:
            # branches are guessed from url, and may fail to be correct specially on tags and branches with slashes
            validated_ref = extract_ref(parsed_url.branch, repository_url)
            if validated_ref != "":
                branch = validated_ref
        if parsed_url.path_raw.startswith("/tree/"):
            path = parsed_url.path_raw.removeprefix(f"/tree/{branch}")
        elif parsed_url.path_raw.startswith("/blob/"):
            path = "/".join(parsed_url.path_raw.removeprefix("/blob/").split("/")[:-1])
            validated_ref = extract_ref(path, repository_url)
            if validated_ref != "":
                branch = validated_ref
                path = path.removeprefix(f"{branch}")
        else:
            path = ""
        logger.debug(
            f"Using branch: {branch} and path: {path} for repository URL: {repository_url}"
        )
        # Get mirror URL and branch if available
        effective_repository_url, _, effective_branch, branch = (
            self._get_mirror_url_and_ref(repository_url, RefType.BRANCH, branch)
        )
        logger.debug(
            f"Effective repository URL: {effective_repository_url}, effective branch: {effective_branch}"
        )

        cached_timestamps = list_dir(self.local_cache_dir)
        cached_timestamps.sort(reverse=True)
        if not force_update:
            # check if there is a cache
            logger.debug(f"Checking local cache for {owner}/{repo} at branch {branch}.")
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
                        f"Found cached branch {branch} for {owner}/{repo} at {local_branch_path}"
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
            f"Cloning repository {effective_repository_url} at branch {effective_branch} to {local_branch_path}"
        )
        run_command(
            f"git clone -c advice.detachedHead=False --depth 1 --branch={effective_branch} {effective_repository_url} {local_branch_path}"
        )

        logger.debug(
            f"Cloned repository {effective_repository_url} at branch {effective_branch} to {local_branch_path}"
        )
        return SourceCodeReference(
            repo_url=repository_url,
            branch=branch,
            local_root_path=f"{local_branch_path}",
            local_full_path=f"{local_branch_path}{path}",
        )
