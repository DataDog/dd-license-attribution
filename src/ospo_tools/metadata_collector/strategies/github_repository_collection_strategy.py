from agithub.GitHub import GitHub

from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.purl_parser import PurlParser
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


class GitHubRepositoryMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(self, github_token):
        if not github_token:
            self.client = GitHub()
        else:
            self.client = GitHub(token=github_token)
        self.purl_parser = PurlParser()

    # method to get the metadata
    def augment_metadata(self, metadata):
        updated_metadata = []
        for package in metadata:
            if not package.origin:
                updated_metadata.append(package)
                continue
            owner, repo = self.purl_parser.get_github_owner_and_repo(package.origin)
            if owner is None or repo is None:
                updated_metadata.append(package)
                continue
            if not package.copyright or not package.license:
                # get the repository information
                status, repository = self.client.repos[owner][repo].get()
                if status == 200:
                    package.copyright = repository["owner"]["login"]
                    if repository["license"]:
                        # get the license information
                        package.license = repository["license"].get("spdx_id", None)
                        if package.license == "NOASSERTION":
                            package.license = None
            updated_metadata.append(package)
        metadata.clear()
        metadata.extend(updated_metadata)
