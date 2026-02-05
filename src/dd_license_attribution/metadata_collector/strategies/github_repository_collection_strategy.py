# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from agithub.GitHub import GitHub
from giturlparse import parse as parse_git_url

from dd_license_attribution.artifact_management.source_code_manager import (
    SourceCodeManager,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


class GitHubRepositoryMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(self, github_client: GitHub, source_code_manager: SourceCodeManager):
        self.client = github_client
        self.source_code_manager = source_code_manager

    # method to get the metadata
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = []
        for package in metadata:
            # Skip packages without an origin URL
            if not package.origin:
                updated_metadata.append(package)
                continue

            # Resolve canonical URLs to handle renamed/transferred repositories
            canonical_url, api_url = self.source_code_manager.get_canonical_urls(
                package.origin
            )
            if api_url is None:
                # Not a valid GitHub repository
                updated_metadata.append(package)
                continue

            # Parse the canonical URL to get owner and repo
            parsed_url = parse_git_url(canonical_url)
            if not parsed_url.valid or not parsed_url.github:
                updated_metadata.append(package)
                continue

            owner = parsed_url.owner
            repo = parsed_url.repo

            # Update package origin to use canonical URL
            # This ensures consistency when this package is referenced by other strategies
            package.origin = canonical_url

            if not package.copyright or not package.license:
                # get the repository information
                status, repository = self.source_code_manager.get_repository_info(
                    owner, repo
                )

                if status == 200 and repository:
                    if not package.copyright:
                        package.copyright = [repository["owner"]["login"]]
                    if repository["license"] and not package.license:
                        # get the license information
                        if repository["license"].get("spdx_id", None) == "NOASSERTION":
                            package.license = []
                        else:
                            package.license = [repository["license"].get("spdx_id")]
                else:
                    raise ValueError(
                        f"Failed to get repository information for {owner}/{repo}"
                    )
            updated_metadata.append(package)
        return updated_metadata
