from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.purl_parser import PurlParser
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from enum import Enum
from agithub.GitHub import GitHub
from typing import Any


class ProjectScope(Enum):
    ONLY_ROOT_PROJECT = "Only Root Project"
    ONLY_TRANSITIVE_DEPENDENCIES = "Only Transitive Dependencies"
    ALL = "All"


class GitHubSbomMetadataCollectionStrategy(MetadataCollectionStrategy):
    # constructor
    def __init__(self, github_client: GitHub, project_scope: ProjectScope) -> None:
        self.client = github_client
        self.purl_parser = PurlParser()
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
        for package in metadata:
            owner, repo = self.purl_parser.get_github_owner_and_repo(package.origin)
            if owner is None or repo is None:
                updated_metadata.append(package)
                continue
            sbom = self.__get_github_generated_sbom(owner, repo)
            packages_in_sbom = sbom["packages"]
            if not self.with_root_project:
                # Exclude the root project from the metadata
                packages_in_sbom = [
                    pkg for pkg in packages_in_sbom if package.name != pkg["name"]
                ]
            if not self.with_transitive_dependencies:
                filtered_packages = [
                    pkg
                    for pkg in packages_in_sbom
                    if any(
                        m_pkg.name is not None
                        and pkg["name"].lower().startswith(m_pkg.name.lower())
                        for m_pkg in metadata
                    )
                ]
                packages_in_sbom = filtered_packages
            for sbom_package in packages_in_sbom:
                # skipping CI dependencies declared as actoin:
                if sbom_package["name"].startswith("action"):
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
                if (
                    not origin
                    and "downloadLocation" in sbom_package
                    and sbom_package["downloadLocation"] != "NOASSERTION"
                ):
                    origin = sbom_package["downloadLocation"]
                if (
                    not license
                    and "licenseDeclared" in sbom_package
                    and sbom_package["licenseDeclared"] != "NOASSERTION"
                ):
                    license = [sbom_package["licenseDeclared"]]
                if not copyright:
                    copyright = []

                if new_package_metadata:  # update with new information
                    new_package_metadata.version = version
                    new_package_metadata.origin = origin
                    new_package_metadata.license = license
                    new_package_metadata.copyright = copyright
                else:  # create a new metadata and append it to the updated_metadata
                    updated_package = Metadata(
                        name=sbom_package["name"],
                        version=version,
                        origin=origin,
                        license=license,
                        copyright=copyright,
                    )
                    updated_metadata.append(updated_package)
        return updated_metadata

    def __get_github_generated_sbom(self, owner: str, repo: str) -> Any:
        status, result = self.client.repos[owner][repo]["dependency-graph"].sbom.get()
        if status == 200:
            return result["sbom"]
        raise ValueError(f"Failed to get SBOM for {owner}/{repo}")
