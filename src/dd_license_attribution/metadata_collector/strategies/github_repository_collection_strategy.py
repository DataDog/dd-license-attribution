# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from agithub.GitHub import GitHub
from giturlparse import parse as parse_git_url

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


class GitHubRepositoryMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(self, github_client: GitHub):
        self.client = github_client

    # method to get the metadata
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = []
        for package in metadata:
            parsed_url = parse_git_url(package.origin)
            if parsed_url.valid and parsed_url.github:
                owner = parsed_url.owner
                repo = parsed_url.repo
            else:
                updated_metadata.append(package)
                continue
            if not package.copyright or not package.license:
                # get the repository information
                status, repository = self.client.repos[owner][repo].get()

                # If the repository has moved, follow the redirect
                # The redirect URL will use /repositories/{id}, which always returns
                # the final/current repository data (never another redirect)
                if status == 301 and repository and "url" in repository:
                    redirect_url = repository["url"]
                    api_prefix = "https://api.github.com/"
                    if redirect_url.startswith(api_prefix):
                        path = redirect_url[len(api_prefix) :]
                        path_parts = path.split("/")
                        # Navigate the GitHub client to the correct endpoint
                        endpoint = self.client
                        for part in path_parts:
                            endpoint = endpoint[part]
                        status, repository = endpoint.get()

                if status == 200:
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
