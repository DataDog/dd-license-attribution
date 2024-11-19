from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.purl_parser import PurlParser
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from agithub.GitHub import GitHub


class GitHubRepositoryMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(self, github_client: GitHub):
        self.client = github_client
        self.purl_parser = PurlParser()

    # method to get the metadata
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = []
        for package in metadata:
            owner, repo = self.purl_parser.get_github_owner_and_repo(package.origin)
            if owner is None or repo is None:
                updated_metadata.append(package)
                continue
            if not package.copyright or not package.license:
                # get the repository information
                status, repository = self.client.repos[owner][repo].get()
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
                    continue  # repository moved but we not supporting redirects here yet
                else:
                    raise ValueError(
                        f"Failed to get repository information for {owner}/{repo}"
                    )
            updated_metadata.append(package)
        return updated_metadata
