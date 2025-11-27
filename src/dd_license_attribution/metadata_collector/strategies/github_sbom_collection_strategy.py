# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json
import logging
from io import StringIO
from typing import Any

from agithub.GitHub import GitHub
from giturlparse import parse as parse_git_url
from spdx.document import Document
from spdx.package import Package
from spdx.parsers.jsonparser import Parser as JSONParser
from spdx.parsers.jsonyamlxmlbuilders import Builder
from spdx.parsers.loggers import StandardLogger

from dd_license_attribution.artifact_management.source_code_manager import (
    NonAccessibleRepository,
    SourceCodeManager,
    UnauthorizedRepository,
)
from dd_license_attribution.config import string_formatting_config
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from dd_license_attribution.utils.custom_splitting import CustomSplit

__all__ = ["GitHubSbomMetadataCollectionStrategy", "ProjectScope"]

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")


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

    def _extract_license_string(self, license_expression: Any) -> str | None:
        """Extract license string from SPDX license expression object."""
        if license_expression is None:
            return None
        # SPDX library may return the license as a string or as an object
        # Handle both cases
        if isinstance(license_expression, str):
            return license_expression
        # If it's an object with a string representation, use that
        return str(license_expression) if license_expression else None

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
                logger.debug(
                    "Attempting to retrieve GitHub-generated SBOM for '%s/%s'.",
                    owner,
                    repo,
                )
                sbom_document = self.__get_github_generated_sbom(owner, repo)
                packages_in_sbom: list[Package] = sbom_document.packages
                logger.debug(
                    "Loaded %d package(s) from SBOM for '%s/%s'.",
                    len(packages_in_sbom),
                    owner,
                    repo,
                )
            except Exception as e:
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
                packages_in_sbom = [
                    pkg
                    for pkg in packages_in_sbom
                    if canonical_package_name != pkg.name
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
                        and pkg.name.lower().startswith(m_pkg.name.lower())
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
                pkg_name = sbom_package.name if sbom_package.name else "<no-name>"
                logger.debug("Processing SBOM package: '%s'", pkg_name)
                # skipping CI dependencies declared as actions
                if sbom_package.spdx_id and sbom_package.spdx_id.startswith(
                    "SPDXRef-githubactions-"
                ):
                    logger.debug(
                        "Skipping CI dependency (GitHub Action) package: '%s'", pkg_name
                    )
                    continue

                # search if there is a package with the same name in the metadata and set it in old_package_metadata variable
                old_package_metadata = next(
                    (
                        old_package_metadata
                        for old_package_metadata in metadata
                        if old_package_metadata.name == sbom_package.name
                    ),
                    None,
                )
                new_package_metadata = next(
                    (
                        new_package_metadata
                        for new_package_metadata in updated_metadata
                        if new_package_metadata.name == sbom_package.name
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
                    and sbom_package.version
                    and sbom_package.version != "NOASSERTION"
                ):
                    version = sbom_package.version
                if not origin:
                    if (
                        sbom_package.download_location
                        and sbom_package.download_location != "NOASSERTION"
                        and sbom_package.download_location != ""
                    ):
                        origin = sbom_package.download_location
                    elif sbom_package.name and sbom_package.name.startswith(
                        "github.com"
                    ):
                        origin = "https://{sbom_name}".format(
                            sbom_name=sbom_package.name
                        )
                    else:  # fallback guess
                        origin = sbom_package.name
                if not license:
                    license_declared_str = self._extract_license_string(
                        sbom_package.license_declared
                    )
                    if license_declared_str and license_declared_str != "NOASSERTION":
                        license = [license_declared_str]
                    else:
                        license_concluded_str = self._extract_license_string(
                            sbom_package.conc_lics
                        )
                        if (
                            license_concluded_str
                            and license_concluded_str != "NOASSERTION"
                        ):
                            license = [license_concluded_str]
                        else:
                            license = []
                if not copyright:
                    if sbom_package.cr_text and sbom_package.cr_text != "NOASSERTION":
                        copyright = list(
                            set(self.splitter.custom_split(sbom_package.cr_text, ","))
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
                    sbom_is_root = sbom_package.name == canonical_package_name

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
                            name=sbom_package.name if sbom_package.name else "",
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

    def __get_github_generated_sbom(self, owner: str, repo: str) -> Document:
        logger.debug(
            "Attempting to retrieve GitHub-generated SBOM for '%s/%s'.", owner, repo
        )
        status, result = self.client.repos[owner][repo]["dependency-graph"].sbom.get()
        logger.debug(
            "GitHub SBOM API response for '%s/%s': status=%s", owner, repo, status
        )
        if status == 200:
            # Parse the SBOM JSON using spdx-tools library (version 0.7.0rc0)
            sbom_json = result["sbom"]
            sbom_json_str = json.dumps(sbom_json)
            sbom_file = StringIO(sbom_json_str)
            builder = Builder()
            standard_logger = StandardLogger()
            parser = JSONParser(builder, standard_logger)
            parser.parse(sbom_file)
            document = parser.document
            logger.debug("Successfully parsed SPDX document for '%s/%s'.", owner, repo)
            return document
        if status == 404:
            error_message = (
                f"Inexistent repository or private repository and not enough permissions in the GitHub token.\n"
                f"If {owner}/{repo} is a valid repository, check if the token has the content-read and metadata-read required permissions."
            )
            logger.error(
                "SBOM retrieval failed for '%s/%s': %s", owner, repo, error_message
            )
            raise NonAccessibleRepository(error_message)
        if status == 401:
            error_message = (
                f"The GitHub token doesn't have enough permissions to access the {owner}/{repo} repository.\n"
                f"Check if the token has the content-read and metadata-read required permissions."
            )
            logger.error(
                "SBOM retrieval unauthorized for '%s/%s': %s",
                owner,
                repo,
                error_message,
            )
            raise UnauthorizedRepository(error_message)
        logger.error(
            "Failed to get SBOM for '%s/%s', unexpected status code: %s",
            owner,
            repo,
            status,
        )
        raise ValueError(f"Failed to get SBOM for {owner}/{repo}")
