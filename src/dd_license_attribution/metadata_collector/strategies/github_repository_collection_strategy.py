# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import logging
import re

from agithub.GitHub import GitHub
from giturlparse import parse as parse_git_url

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)

logger = logging.getLogger("dd_license_attribution")

MAX_REDIRECTS = 5


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
                redirects_followed = 0

                while status == 301 and redirects_followed < MAX_REDIRECTS:
                    # repository moved, follow the redirect
                    if repository and "url" in repository:
                        redirect_url = repository["url"]

                        # Check if it's a /repositories/{id} format
                        repo_id_match = re.match(
                            r"https://api\.github\.com/repositories/(\d+)", redirect_url
                        )
                        if repo_id_match:
                            # Direct API call to the repository ID endpoint
                            repo_id = repo_id_match.group(1)
                            status, repository = self.client.repositories[repo_id].get()
                            redirects_followed += 1
                        else:
                            # Try parsing as a git URL (e.g., https://github.com/owner/repo)
                            parsed_redirect = parse_git_url(redirect_url)
                            if parsed_redirect.valid and parsed_redirect.github:
                                owner = parsed_redirect.owner
                                repo = parsed_redirect.repo
                                status, repository = self.client.repos[owner][
                                    repo
                                ].get()
                                redirects_followed += 1
                            else:
                                logger.warning(
                                    f"Unable to parse redirect URL: {redirect_url}"
                                )
                                break
                    else:
                        break

                if status == 200:
                    if not package.copyright:
                        package.copyright = [repository["owner"]["login"]]
                    if repository["license"] and not package.license:
                        # get the license information
                        if repository["license"].get("spdx_id", None) == "NOASSERTION":
                            package.license = []
                        else:
                            package.license = [repository["license"].get("spdx_id")]
                elif status == 301:
                    continue  # more than MAX_REDIRECTS redirects, skip the repository
                else:
                    raise ValueError(
                        f"Failed to get repository information for {owner}/{repo}"
                    )
            updated_metadata.append(package)
        return updated_metadata
