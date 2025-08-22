# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)

__all__ = ["GitHubSbomMetadataCollectionStrategy", "ProjectScope"]

from typing import Any
import json
import os

from agithub.GitHub import GitHub
from giturlparse import parse as parse_git_url
import requests

from dd_license_attribution.artifact_management.source_code_manager import (
    NonAccessibleRepository,
    UnauthorizedRepository,
)


class GitHubSbomMetadataCollectionStrategy(MetadataCollectionStrategy):
    # constructor
    def __init__(self, github_client: GitHub, project_scope: ProjectScope) -> None:
        self.client = github_client
        if project_scope == ProjectScope.ONLY_ROOT_PROJECT:
            self.with_root_project = True
            self.with_transitive_dependencies = False
        elif project_scope == ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES:
            self.with_root_project = False
            self.with_transitive_dependencies = True
        elif project_scope == ProjectScope.ALL:
            self.with_root_project = True
            self.with_transitive_dependencies = True

    # Exclude transitive dependencies of any excluded package, based on SBOM relationships.
    def __handle_transitive(
        self,
        packages_in_sbom: list[dict],
        depsToExclude: list[str],
        relationships: list[dict],
    ) -> list[dict]:
        # Build maps for graph traversal using SPDX IDs
        name_to_spdxids: dict[str, list[str]] = {}
        for pkg in packages_in_sbom:
            name = pkg.get("name")
            spdx_id = pkg.get("SPDXID")
            if not name or not spdx_id:
                continue
            name_to_spdxids.setdefault(name, []).append(spdx_id)

        # Build adjacency from relationships (subject DEPENDS_ON object)
        adjacency: dict[str, set[str]] = {}
        for rel in relationships or []:
            if rel.get("relationshipType") != "DEPENDS_ON":
                continue
            src = rel.get("spdxElementId")
            dst = rel.get("relatedSpdxElement")
            if not src or not dst:
                continue
            adjacency.setdefault(src, set()).add(dst)

        # Compute transitive closure of excluded SPDX IDs
        excluded_spdx_ids: set[str] = set()
        queue: list[str] = []
        for dep_name in depsToExclude:
            for sid in name_to_spdxids.get(dep_name, []):
                if sid not in excluded_spdx_ids:
                    excluded_spdx_ids.add(sid)
                    queue.append(sid)

        while queue:
            current = queue.pop(0)
            for neighbor in adjacency.get(current, set()):
                if neighbor not in excluded_spdx_ids:
                    excluded_spdx_ids.add(neighbor)
                    queue.append(neighbor)

        # Filter out any package whose SPDXID is in the excluded set
        filtered_packages = [
            pkg
            for pkg in packages_in_sbom
            if pkg.get("SPDXID") not in excluded_spdx_ids
            and pkg.get("name") not in depsToExclude
        ]

        return filtered_packages

    def __filter_packages_from_unwanted_files_out_of_SBOM(
        self,
        filenames_to_filter_out: list[str],
        packages_in_sbom: list[dict],
        owner: str,
        repo: str,
        relationships: list[dict],
    ) -> list[dict]:
        # Defensive coding for None inputs
        if not packages_in_sbom:
            return []
        if not filenames_to_filter_out:
            return packages_in_sbom
        relationships = relationships or []

        # Call the function to get file-to-dependencies mapping
        file_deps_map = self.__get_list_of_packages_mapped_to_filename(
            filenames_to_filter_out, owner, repo
        )

        # Collect dependency names to exclude from the specified files
        depsToExclude = []
        for filename in filenames_to_filter_out:
            if filename in file_deps_map:
                depsToExclude.extend(file_deps_map[filename])
        depsToExclude = list(set(depsToExclude))

        # Handle transitive dependencies and filter packages
        filtered_packages = self.__handle_transitive(
            packages_in_sbom, depsToExclude, relationships
        )

        print("HEEEEEEEEEERE")
        print(filtered_packages)
        print("--------------------------------HIIIIIIIIIIIII")
        return filtered_packages

    def __get_info_from_graphql(
        self, owner: str, repo: str
    ) -> dict[str, set[str]] | None:
        github_token = os.getenv("GITHUB_TOKEN")
        if not github_token:
            return None

        url = "https://api.github.com/graphql"
        headers = {
            "Authorization": f"Bearer {github_token}",
            "Content-Type": "application/json",
        }

        # Query to paginate manifests (and first page of each manifest's dependencies)
        manifests_query = """
        query($owner: String!, $repo: String!, $afterManifests: String) {
          repository(owner: $owner, name: $repo) {
            dependencyGraphManifests(first: 100, after: $afterManifests) {
              pageInfo { hasNextPage endCursor }
              nodes {
                id
                filename
                dependencies(first: 100) {
                  pageInfo { hasNextPage endCursor }
                  nodes { packageName requirements }
                }
              }
            }
          }
        }
        """

        # Secondary query to paginate dependencies of a single manifest by id
        deps_query = """
        query($manifestId: ID!, $afterDeps: String) {
          node(id: $manifestId) {
            ... on DependencyGraphManifest {
              dependencies(first: 100, after: $afterDeps) {
                pageInfo { hasNextPage endCursor }
                nodes { packageName requirements }
              }
            }
          }
        }
        """

        result: dict[str, set[str]] = {}
        after_manifests: str | None = None

        while True:
            payload = {
                "query": manifests_query,
                "variables": {
                    "owner": owner,
                    "repo": repo,
                    "afterManifests": after_manifests,
                },
            }
            response = requests.post(url, headers=headers, json=payload)
            if response.status_code != 200:
                # Return None on error instead of empty dict
                return None
            data = response.json()
            if "errors" in data:
                # Return None on GraphQL errors instead of empty dict
                return None
            repo_data = data.get("data", {}).get("repository")
            if not repo_data:
                break
            dg = repo_data.get("dependencyGraphManifests") or {}
            page_info = dg.get("pageInfo") or {}
            nodes = dg.get("nodes") or []

            for manifest in nodes:
                filename = manifest.get("filename")
                manifest_id = manifest.get("id")
                if not filename or not manifest_id:
                    continue

                # Collect first page of deps
                deps_conn = manifest.get("dependencies") or {}
                deps_nodes = deps_conn.get("nodes") or []
                for dep in deps_nodes:
                    pkg_name = dep.get("packageName")
                    if pkg_name:
                        result.setdefault(filename, set()).add(pkg_name)

                # Paginate dependencies per manifest if needed
                deps_page_info = deps_conn.get("pageInfo") or {}
                after_deps = (
                    deps_page_info.get("endCursor")
                    if deps_page_info.get("hasNextPage")
                    else None
                )
                while after_deps:
                    dep_payload = {
                        "query": deps_query,
                        "variables": {
                            "manifestId": manifest_id,
                            "afterDeps": after_deps,
                        },
                    }
                    dep_resp = requests.post(url, headers=headers, json=dep_payload)
                    if dep_resp.status_code != 200:
                        raise ValueError(
                            f"GraphQL request (deps) failed with status {dep_resp.status_code}: {dep_resp.text}"
                        )
                    dep_data = dep_resp.json()
                    if "errors" in dep_data:
                        raise ValueError(
                            f"GraphQL deps query error: {dep_data['errors']}"
                        )
                    node_data = dep_data.get("data", {}).get("node") or {}
                    dep_conn = node_data.get("dependencies") or {}
                    for dep in dep_conn.get("nodes") or []:
                        pkg_name = dep.get("packageName")
                        if pkg_name:
                            result.setdefault(filename, set()).add(pkg_name)
                    pi = dep_conn.get("pageInfo") or {}
                    after_deps = pi.get("endCursor") if pi.get("hasNextPage") else None

            after_manifests = (
                page_info.get("endCursor") if page_info.get("hasNextPage") else None
            )
            if not after_manifests:
                break

        return result

    def __get_list_of_packages_mapped_to_filename(
        self, filenames_to_filter: list[str], owner: str, repo: str
    ) -> dict[str, list[str]]:
        # Get all dependencies from GraphQL
        result = self.__get_info_from_graphql(owner, repo)
        if result is None:
            return {}

        # Filter by requested filenames if provided and convert sets to sorted lists
        if filenames_to_filter:
            return {
                fn: sorted(list(deps))
                for fn, deps in result.items()
                if fn in filenames_to_filter
            }

        return {fn: sorted(list(deps)) for fn, deps in result.items()}

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
            sbom = self.__get_github_generated_sbom(owner, repo)
            packages_in_sbom = sbom.get("packages", [])  # Default to empty list if None
            relationships = sbom.get("relationships", [])
            # filenames_tofilter_out = ["requirements.txt", "package.json", "go.mod"]  # example
            filenames_to_filter_out = [".generator/poetry.lock"]  # example

            packages_in_sbom = self.__filter_packages_from_unwanted_files_out_of_SBOM(
                filenames_to_filter_out, packages_in_sbom, owner, repo, relationships
            )
            if not self.with_root_project:
                # Exclude the root project from the metadata
                packages_in_sbom = [
                    pkg
                    for pkg in packages_in_sbom
                    if pkg.get("name") and package.name != pkg.get("name")
                ]
            if not self.with_transitive_dependencies:
                filtered_packages = [
                    pkg
                    for pkg in packages_in_sbom
                    if pkg.get("name")
                    and any(
                        m_pkg.name is not None
                        and pkg.get("name").lower().startswith(m_pkg.name.lower())
                        for m_pkg in metadata
                    )
                ]
                packages_in_sbom = filtered_packages
            for sbom_package in packages_in_sbom:
                # skipping CI dependencies declared as action
                if not sbom_package.get("name"):
                    continue
                if sbom_package.get("SPDXID", "").startswith("SPDXRef-githubactions-"):
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
                    # Initialize as empty lists if None
                    license = (
                        old_package_metadata.license
                        if old_package_metadata.license is not None
                        else []
                    )
                    copyright = (
                        old_package_metadata.copyright
                        if old_package_metadata.copyright is not None
                        else []
                    )
                # if there is a new package metadata copy it to the new metadata
                # we can ignore the old metadata as it was copied in previous iterations if existent
                if new_package_metadata:
                    version = new_package_metadata.version
                    origin = new_package_metadata.origin
                    # Initialize as empty lists if None
                    license = (
                        new_package_metadata.license
                        if new_package_metadata.license is not None
                        else []
                    )
                    copyright = (
                        new_package_metadata.copyright
                        if new_package_metadata.copyright is not None
                        else []
                    )
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
                        copyright = list(set(sbom_package["copyrightText"].split(",")))
                    else:
                        copyright = []

                if new_package_metadata:  # update with new information
                    new_package_metadata.version = version
                    new_package_metadata.origin = origin
                    # No need for None checks here since we initialize license and copyright as empty lists
                    new_package_metadata.license = license
                    new_package_metadata.copyright = copyright
                else:  # create a new metadata and append it to the updated_metadata
                    updated_package = Metadata(
                        name=sbom_package["name"],
                        version=version,
                        origin=origin,
                        local_src_path=None,
                        license=license,
                        copyright=copyright,
                    )
                    updated_metadata.append(updated_package)
        return updated_metadata

    def __get_github_generated_sbom(self, owner: str, repo: str) -> Any:
        status, result = self.client.repos[owner][repo]["dependency-graph"].sbom.get()
        if status == 200:
            return result["sbom"]
        if status == 404:
            error_message = (
                f"Non-existent repository or private repository and not enough permissions in the GitHub token.\n"
                f"If {owner}/{repo} is a valid repository, check if the token has the content-read and metadata-read required permissions."
            )
            raise NonAccessibleRepository(error_message)
        if status == 401:
            error_message = (
                f"The GitHub token doesn't have enough permissions to access the {owner}/{repo} repository.\n"
                f"Check if the token has the content-read and metadata-read required permissions."
            )
            raise UnauthorizedRepository(error_message)
        raise ValueError(f"Failed to get SBOM for {owner}/{repo}")
