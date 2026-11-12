# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")

from dd_license_attribution.adaptors.os import sleep
from dd_license_attribution.config import string_formatting_config
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from dd_license_attribution.utils.custom_splitting import CustomSplit

__all__ = ["GitHubSbomMetadataCollectionStrategy", "ProjectScope"]

from agithub.GitHub import GitHub
from giturlparse import parse as parse_git_url

from dd_license_attribution.artifact_management.source_code_manager import (
    NonAccessibleRepository,
    SourceCodeManager,
    UnauthorizedRepository,
    github_api_get_with_retry,
    github_response_headers,
)
from dd_license_attribution.utils.bounded_download import download_bounded

# Delays applied between successive fetch attempts of a pending GitHub SBOM
# report. The first fetch is immediate; each pending (202) response is
# followed by one sleep from this schedule. The fixed schedule deliberately
# overrides any Retry-After header on 202 responses.
SBOM_FETCH_RETRY_DELAYS_SECONDS: tuple[int, ...] = (1, 2, 4, 8, 16)
# SPDXID prefix identifying CI dependencies declared as GitHub Actions; a
# package entry is only allowed to lack a "name" when it is skipped by this
# predicate (the same predicate drives the skip in augment_metadata).
SBOM_ACTIONS_PACKAGE_PREFIX = "SPDXRef-githubactions-"
_SBOM_REPORT_URL_PATTERN = re.compile(
    r"^/repos/(?P<owner>[^/]+)/(?P<repo>[^/]+)"
    r"/dependency-graph/sbom/fetch-report/(?P<report_id>[A-Za-z0-9._-]+)$"
)


def _is_action_package(package: dict[str, Any]) -> bool:
    """Return True when a SBOM package entry is a CI (GitHub Actions) dependency."""
    spdx_id = package.get("SPDXID")
    return isinstance(spdx_id, str) and spdx_id.startswith(SBOM_ACTIONS_PACKAGE_PREFIX)


def _validate_sbom_report_url(sbom_url: object, owner: str, repo: str) -> str:
    """Validate the sbom_url from the generation response and return its report id.

    The URL must be an https URL on api.github.com, without userinfo, an
    explicit port, a query or a fragment, pointing exactly at the
    dependency-graph fetch-report endpoint of the requested repository.
    Raises redacted ValueError messages (the URL itself is never included,
    and exception chains are suppressed so the URL cannot leak in logs).
    """
    if not isinstance(sbom_url, str):
        raise ValueError(
            f"SBOM generation response for '{owner}/{repo}' did not contain a sbom_url string"
        ) from None
    parsed = urlparse(sbom_url)
    if parsed.scheme != "https":
        raise ValueError(f"sbom_url for '{owner}/{repo}' must use https") from None
    if parsed.hostname != "api.github.com":
        raise ValueError(
            f"sbom_url for '{owner}/{repo}' must be on api.github.com"
        ) from None
    if parsed.username is not None or parsed.password is not None:
        raise ValueError(
            f"sbom_url for '{owner}/{repo}' must not carry credentials"
        ) from None
    try:
        explicit_port = parsed.port
    except ValueError:
        explicit_port = 1
    if explicit_port is not None:
        raise ValueError(
            f"sbom_url for '{owner}/{repo}' must not carry an explicit port"
        ) from None
    if parsed.query or parsed.fragment:
        raise ValueError(
            f"sbom_url for '{owner}/{repo}' must not carry a query or fragment"
        ) from None
    match = _SBOM_REPORT_URL_PATTERN.match(parsed.path)
    if match is None:
        raise ValueError(
            f"sbom_url for '{owner}/{repo}' does not point at the dependency-graph SBOM fetch-report endpoint"
        ) from None
    if (
        match.group("owner").lower() != owner.lower()
        or match.group("repo").lower() != repo.lower()
    ):
        raise ValueError(
            f"sbom_url for '{owner}/{repo}' points at a different repository"
        ) from None
    report_id = match.group("report_id")
    if not any(character.isalnum() for character in report_id):
        raise ValueError(
            f"sbom_url for '{owner}/{repo}' carries an invalid report id"
        ) from None
    return report_id


def _validate_report_download_url(location: object, owner: str, repo: str) -> str:
    """Validate the Location header of a ready report; return the download URL.

    The signed download URL served by GitHub need not be on the API host (it
    is currently an Azure storage host, an implementation detail), so any
    absolute https URL is accepted.
    """
    if not isinstance(location, str) or not location:
        raise ValueError(
            f"GitHub SBOM report for '{owner}/{repo}' was ready but carried no usable Location header"
        ) from None
    parsed = urlparse(location)
    if parsed.scheme != "https" or not parsed.hostname:
        raise ValueError(
            f"GitHub SBOM report download URL for '{owner}/{repo}' is not a valid https URL"
        ) from None
    return location


def _validate_sbom_document(document: object, owner: str, repo: str) -> dict[str, Any]:
    """Validate the downloaded SBOM document shape at the retrieval boundary.

    Guarantees that augment_metadata's SBOM processing, which runs outside its
    per-package recovery handler, only ever sees well-shaped data: a JSON
    object whose "packages" is a list of objects whose "name" and "SPDXID",
    when present, are strings. Entries without a "name" are allowed only when
    they are CI (GitHub Actions) dependencies skipped by _is_action_package.
    Returns the validated document.
    """
    context = f"Malformed GitHub SBOM report for '{owner}/{repo}'"
    if not isinstance(document, dict):
        raise ValueError(f"{context}: the report is not a JSON object") from None
    packages = document.get("packages")
    if not isinstance(packages, list):
        raise ValueError(f"{context}: 'packages' is missing or not a list") from None
    for package in packages:
        if not isinstance(package, dict):
            raise ValueError(
                f"{context}: package entries must be JSON objects"
            ) from None
        name = package.get("name")
        if name is not None and not isinstance(name, str):
            raise ValueError(f"{context}: package 'name' must be a string") from None
        spdx_id = package.get("SPDXID")
        if spdx_id is not None and not isinstance(spdx_id, str):
            raise ValueError(f"{context}: package 'SPDXID' must be a string") from None
        if name is None and not _is_action_package(package):
            raise ValueError(
                f"{context}: package entries must carry a 'name'"
            ) from None
    return document


class GitHubSbomMetadataCollectionStrategy(MetadataCollectionStrategy):
    # constructor
    def __init__(
        self,
        github_client: GitHub,
        source_code_manager: SourceCodeManager,
        project_scope: ProjectScope,
    ) -> None:
        self.client = github_client
        self.source_code_manager = source_code_manager
        self.company_suffixes_sometimes_used_after_commas = (
            string_formatting_config.default_config.preset_company_suffixes
        )
        self.splitter = CustomSplit(
            protected_terms=self.company_suffixes_sometimes_used_after_commas
        )
        if project_scope == ProjectScope.ONLY_ROOT_PROJECT:
            self.with_root_project = True
            self.with_transitive_dependencies = False
        elif project_scope == ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES:
            self.with_root_project = False
            self.with_transitive_dependencies = True
        elif project_scope == ProjectScope.ALL:
            self.with_root_project = True
            self.with_transitive_dependencies = True

    # method to get the metadata
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = []
        #  Track which package is the root project (the first one in the list is typically the one being analyzed)
        root_package_index = 0
        for package_index, package in enumerate(metadata):
            # Skip packages without an origin URL
            if not package.origin:
                logger.debug("Package '%s' has no origin URL, skipping", package.name)
                updated_metadata.append(package)
                continue

            canonical_url, api_url = self.source_code_manager.get_canonical_urls(
                package.origin
            )
            if api_url is None:
                logger.debug(
                    "Package origin '%s' is not a valid GitHub repository. Skipping.",
                    package.origin,
                )
                updated_metadata.append(package)
                continue

            parsed_url = parse_git_url(canonical_url)
            if not parsed_url.valid or not parsed_url.github:
                logger.debug(
                    "Parsed canonical URL '%s' is not a valid GitHub URL. Skipping.",
                    canonical_url,
                )
                updated_metadata.append(package)
                continue

            owner = parsed_url.owner
            repo = parsed_url.repo

            # Update package origin to use canonical URL
            package.origin = canonical_url

            # Update package name to use canonical repo name for correct filtering
            # This is critical for matching with SBOM packages and subsequent strategy processing
            old_name = package.name
            if package.name and (
                package.name.startswith("github.com/")
                or package.name.startswith("https://github.com/")
                or package.name.startswith("http://github.com/")
            ):
                # Use github.com format (not com.github) to match PyPI and other strategies
                package.name = f"github.com/{owner}/{repo}"
                logger.debug(
                    "Updated package name from '%s' to '%s' (canonical)",
                    old_name,
                    package.name,
                )

            # SBOM uses format like "com.github.owner/repo"
            canonical_package_name = f"com.github.{owner}/{repo}"
            logger.debug(
                "Canonical package name determined: '%s'", canonical_package_name
            )

            try:
                sbom = self.__get_github_generated_sbom(owner, repo)
                packages_in_sbom = sbom["packages"]
                logger.debug(
                    "Loaded %d package(s) from SBOM for '%s/%s'.",
                    len(packages_in_sbom),
                    owner,
                    repo,
                )
            except (
                NonAccessibleRepository,
                UnauthorizedRepository,
                ValueError,
                KeyError,
                TypeError,
                OSError,
            ) as e:
                logger.error(
                    "Failed to retrieve or parse GitHub SBOM for '%s/%s': %s",
                    owner,
                    repo,
                    str(e),
                    exc_info=True,
                )
                updated_metadata.append(package)
                continue

            if not self.with_root_project:
                before_count = len(packages_in_sbom)
                # Exclude the root project from the metadata using the canonical name
                # (nameless action entries are guarded so they cannot raise here)
                packages_in_sbom = [
                    pkg
                    for pkg in packages_in_sbom
                    if canonical_package_name != pkg.get("name")
                ]
                after_count = len(packages_in_sbom)
                logger.debug(
                    "Excluded root project '%s'. Packages before: %d, after: %d.",
                    canonical_package_name,
                    before_count,
                    after_count,
                )
            if not self.with_transitive_dependencies:
                before_count = len(packages_in_sbom)
                filtered_packages = [
                    pkg
                    for pkg in packages_in_sbom
                    if any(
                        m_pkg.name is not None
                        # "or ''" also covers an explicit json null name,
                        # which .get(name, "") would pass through unchanged
                        and (pkg.get("name") or "")
                        .lower()
                        .startswith(m_pkg.name.lower())
                        for m_pkg in metadata
                    )
                ]
                packages_in_sbom = filtered_packages
                after_count = len(packages_in_sbom)
                logger.debug(
                    "Filtered packages to only those matching original metadata (transitive dependencies skipped). Packages before: %d, after: %d.",
                    before_count,
                    after_count,
                )

            # Track if the initial package was updated by SBOM processing
            # If no SBOM packages match or update it, we still need to include it with canonical URL/name
            initial_package_processed = False

            # Check if this package represents the root project by comparing with canonical formats
            is_root_package = package_index == root_package_index

            for sbom_package in packages_in_sbom:
                pkg_name = sbom_package.get("name", "<no-name>")
                logger.debug("Processing SBOM package: '%s'", pkg_name)
                # skipping CI dependencies declared as actions
                if _is_action_package(sbom_package):
                    logger.debug(
                        "Skipping CI dependency (GitHub Action) package: '%s'", pkg_name
                    )
                    continue

                # search if there is a package with the same name in the metadata and set it in old_package_metadata variable
                old_package_metadata = next(
                    (
                        old_package_metadata
                        for old_package_metadata in metadata
                        if old_package_metadata.name == sbom_package["name"]
                    ),
                    None,
                )
                new_package_metadata = next(
                    (
                        new_package_metadata
                        for new_package_metadata in updated_metadata
                        if new_package_metadata.name == sbom_package["name"]
                    ),
                    None,
                )
                version, origin, license, copyright = None, None, [], []

                # if there was previous values copy them to the new metadata
                if old_package_metadata and not new_package_metadata:
                    version = old_package_metadata.version
                    origin = old_package_metadata.origin
                    license = old_package_metadata.license
                    copyright = old_package_metadata.copyright
                # if there is a new package metadata copy it to the new metadata
                # we can ignore the old metadata as it was copied in previous iterations if existent
                if new_package_metadata:
                    version = new_package_metadata.version
                    origin = new_package_metadata.origin
                    license = new_package_metadata.license
                    copyright = new_package_metadata.copyright
                # last, we update with sbom data to fill gaps if available
                if (
                    not version
                    and "versionInfo" in sbom_package
                    and sbom_package["versionInfo"] != "NOASSERTION"
                ):
                    version = sbom_package["versionInfo"]
                if not origin:
                    if (
                        "downloadLocation" in sbom_package
                        and sbom_package["downloadLocation"] != "NOASSERTION"
                        and sbom_package["downloadLocation"] != ""
                    ):
                        origin = sbom_package["downloadLocation"]
                    elif sbom_package["name"].startswith("github.com"):
                        origin = "https://{sbom_name}".format(
                            sbom_name=sbom_package["name"]
                        )
                    else:  # fallback guess
                        origin = sbom_package["name"]
                if not license:
                    if (
                        "licenseDeclared" in sbom_package
                        and sbom_package["licenseDeclared"] != "NOASSERTION"
                    ):
                        license = [sbom_package["licenseDeclared"]]
                    elif (
                        "licenseConcluded" in sbom_package
                        and sbom_package["licenseConcluded"] != "NOASSERTION"
                    ):
                        license = [sbom_package["licenseConcluded"]]
                    else:
                        license = []
                if not copyright:
                    if (
                        "copyrightText" in sbom_package
                        and sbom_package["copyrightText"] != "NOASSERTION"
                    ):
                        copyright = list(
                            set(
                                self.splitter.custom_split(
                                    sbom_package["copyrightText"], ","
                                )
                            )
                        )
                    else:
                        copyright = []

                if new_package_metadata:  # update with new information
                    new_package_metadata.version = version
                    new_package_metadata.origin = origin
                    new_package_metadata.license = license
                    new_package_metadata.copyright = copyright
                    # Check if this is the initial package being updated
                    if new_package_metadata.name == package.name:
                        initial_package_processed = True
                else:
                    # create a new metadata and append it to the updated_metadata
                    # Check if this SBOM package represents the root project
                    # SBOM uses "com.github.owner/repo" but we use "github.com/owner/repo"
                    # Don't create a duplicate if this is the root project and the initial package was already updated
                    sbom_is_root = sbom_package["name"] == canonical_package_name

                    if is_root_package and sbom_is_root:
                        package.version = version or package.version
                        package.license = license if license else package.license
                        package.copyright = (
                            copyright if copyright else package.copyright
                        )
                        # Only update origin if it's better than what we have
                        if origin and origin != package.origin:
                            # Prefer the canonical URL we already set
                            logger.debug(
                                "Keeping canonical origin '%s' over SBOM origin '%s'",
                                package.origin,
                                origin,
                            )
                        # Add the updated initial package to the output
                        updated_metadata.append(package)
                        initial_package_processed = True
                    else:
                        # This is a different package, create new metadata
                        updated_package = Metadata(
                            name=sbom_package["name"],
                            version=version,
                            origin=origin,
                            local_src_path=None,
                            license=license,
                            copyright=copyright,
                        )
                        logger.debug(
                            "Created new metadata entry for package '%s'", pkg_name
                        )
                        updated_metadata.append(updated_package)
                        # Check if this is the initial package
                        if updated_package.name == package.name:
                            initial_package_processed = True

            # If the initial package wasn't processed/updated by any SBOM package, add it with canonical URL/name
            if not initial_package_processed:
                if not self.with_root_project and is_root_package:
                    logger.debug(
                        "Initial package '%s' is the root project (index %d) and with_root_project=False, not adding",
                        package.name,
                        package_index,
                    )
                else:
                    logger.debug(
                        "Initial package '%s' not found in SBOM, adding with canonical URL/name",
                        package.name,
                    )
                    updated_metadata.append(package)

        return updated_metadata

    def __get_github_generated_sbom(self, owner: str, repo: str) -> dict[str, Any]:
        """Retrieve the GitHub-generated SBOM document through the async API.

        Requests report generation, polls the same report until it is ready,
        and downloads the bare SPDX document through the bounded downloader.
        Generation is requested exactly once; pending (202) fetch responses
        retry the same report following SBOM_FETCH_RETRY_DELAYS_SECONDS (the
        fixed schedule deliberately overrides any Retry-After on 202
        responses, per the accepted design). All failures raise the existing
        recoverable exception types with redacted messages: temporary signed
        report and download URLs are never logged.
        """
        logger.debug(
            "Requesting GitHub SBOM report generation for '%s/%s'.", owner, repo
        )
        status, result, _ = github_api_get_with_retry(
            lambda: self.client.repos[owner][repo]["dependency-graph"]["sbom"][
                "generate-report"
            ].get(),
            self.client,
        )
        if status == 201:
            sbom_url = result.get("sbom_url") if isinstance(result, dict) else None
            report_id = _validate_sbom_report_url(sbom_url, owner, repo)
            logger.debug(
                "GitHub SBOM report generation accepted for '%s/%s'.", owner, repo
            )
            return self.__fetch_github_generated_sbom(owner, repo, report_id)
        if status == 404:
            error_message = (
                f"Inexistent repository or private repository and not enough permissions in the GitHub token.\n"
                f"If {owner}/{repo} is a valid repository, check if the token has the content-read and metadata-read required permissions."
            )
            raise NonAccessibleRepository(error_message)
        if status == 401:
            error_message = (
                f"The GitHub token doesn't have enough permissions to access the {owner}/{repo} repository.\n"
                f"Check if the token has the content-read and metadata-read required permissions."
            )
            raise UnauthorizedRepository(error_message)
        raise ValueError(
            f"Failed to request GitHub SBOM generation for {owner}/{repo} (status {status})"
        )

    def __fetch_github_generated_sbom(
        self, owner: str, repo: str, report_id: str
    ) -> dict[str, Any]:
        """Poll one SBOM report until ready, then download and parse it."""
        pending_retries = 0
        while True:
            status, _, _ = github_api_get_with_retry(
                lambda: self.client.repos[owner][repo]["dependency-graph"]["sbom"][
                    "fetch-report"
                ][report_id].get(),
                self.client,
            )
            logger.debug(
                "GitHub SBOM report fetch for '%s/%s': status=%s", owner, repo, status
            )
            if status == 302:
                logger.debug("GitHub SBOM report ready for '%s/%s'.", owner, repo)
                return self.__download_github_generated_sbom(owner, repo)
            if status != 202:
                break
            if pending_retries >= len(SBOM_FETCH_RETRY_DELAYS_SECONDS):
                raise ValueError(
                    f"GitHub SBOM report for '{owner}/{repo}' was not ready after "
                    f"{sum(SBOM_FETCH_RETRY_DELAYS_SECONDS)} seconds"
                )
            delay = SBOM_FETCH_RETRY_DELAYS_SECONDS[pending_retries]
            pending_retries += 1
            logger.debug(
                "GitHub SBOM report for '%s/%s' pending; retrying in %d second(s).",
                owner,
                repo,
                delay,
            )
            sleep(delay)
        if status == 404:
            raise ValueError(
                f"GitHub SBOM report for '{owner}/{repo}' expired or is unavailable"
            )
        if status == 401:
            error_message = (
                f"The GitHub token doesn't have enough permissions to access the {owner}/{repo} repository.\n"
                f"Check if the token has the content-read and metadata-read required permissions."
            )
            raise UnauthorizedRepository(error_message)
        raise ValueError(
            f"Failed to fetch GitHub SBOM report for {owner}/{repo} (status {status})"
        )

    def __download_github_generated_sbom(self, owner: str, repo: str) -> dict[str, Any]:
        """Download a ready SBOM report and parse it as a bare SPDX document."""
        headers = github_response_headers(self.client)
        location = _validate_report_download_url(
            headers.get("location") if headers is not None else None, owner, repo
        )
        logger.debug("Downloading GitHub SBOM report for '%s/%s'.", owner, repo)
        try:
            content = download_bounded(location)
        except OSError:
            # Redact the signed download URL that download_bounded embeds in
            # its error messages, and suppress the exception chain so it
            # cannot leak through exc_info logging either.
            raise OSError(
                f"Failed to download GitHub SBOM report for {owner}/{repo}"
            ) from None
        try:
            document = json.loads(content)
        except ValueError:
            # Covers JSONDecodeError and UnicodeDecodeError (invalid UTF-8).
            raise ValueError(
                f"GitHub SBOM report for '{owner}/{repo}' is not valid JSON"
            ) from None
        return _validate_sbom_document(document, owner, repo)
