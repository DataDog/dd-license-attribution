# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
#
# This product includes software developed at Datadog \
# (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import json
import logging
from typing import Any, Dict, List

import requests
from giturlparse import validate as validate_git_url

from dd_license_attribution.adaptors.os import (
    open_file,
    output_from_command,
    path_exists,
    path_join,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    SourceCodeManager,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import (
    ProjectScope,
)
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


class NpmMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(
        self,
        top_package: str,
        source_code_manager: SourceCodeManager,
        project_scope: ProjectScope,
    ) -> None:
        self.top_package = top_package
        self.source_code_manager = source_code_manager
        self.only_root_project = project_scope == ProjectScope.ONLY_ROOT_PROJECT
        self.only_transitive = (
            project_scope == ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES
        )

    def _extract_all_dependencies(self, lock_data: Dict[str, Any]) -> Dict[str, str]:
        all_deps: Dict[str, str] = {}

        if "packages" not in lock_data:
            logging.warning("No 'packages' key found in package-lock.json.")
            return all_deps

        packages = lock_data["packages"]
        # Find the root package key
        root_key = "" if "" in packages else "./" if "./" in packages else None
        if root_key is None:
            logging.warning("Root package not found in lockfile 'packages'.")
            return all_deps

        root_pkg = packages[root_key]
        if "dependencies" in root_pkg:
            all_deps.update(root_pkg["dependencies"])

        self._extract_transitive_dependencies(packages, all_deps)
        return all_deps

    def _extract_transitive_dependencies(
        self, packages: Dict[str, Any], all_deps: Dict[str, str]
    ) -> None:

        processed_packages = set()

        new_deps_found = True
        while new_deps_found:
            new_deps_found = False
            current_deps = list(all_deps.items())

            for pkg_name, _ in current_deps:
                if pkg_name in processed_packages:
                    continue

                node_modules_key = f"node_modules/{pkg_name}"
                if node_modules_key in packages:
                    pkg_data = packages[node_modules_key]
                    if "dependencies" in pkg_data:
                        for dep_name, dep_version in pkg_data["dependencies"].items():
                            if dep_name not in all_deps:
                                all_deps[dep_name] = dep_version
                                new_deps_found = True

                processed_packages.add(pkg_name)

    def augment_metadata(self, metadata: List[Metadata]) -> List[Metadata]:
        updated_metadata = metadata.copy()
        source_code_ref = self.source_code_manager.get_code(self.top_package)
        if not source_code_ref:
            return updated_metadata
        project_path = source_code_ref.local_full_path
        # Run npm install --package-lock-only to generate package-lock.json
        try:
            output_from_command(
                f"CWD=`pwd`; cd {project_path} && "
                "npm install --package-lock-only --force; cd $CWD"
            )
        except Exception as e:
            logging.warning(f"Failed to run npm install for {self.top_package}: {e}")
            return updated_metadata
        lock_path = path_join(project_path, "package-lock.json")
        lock_data = {}
        if not path_exists(lock_path):
            logging.warning(f"No package-lock.json found in {project_path}")
            return updated_metadata
        try:
            lock_data = json.loads(open_file(lock_path))
        except Exception as e:
            logging.warning(f"Failed to read package-lock.json: {e}")
            return updated_metadata

        all_deps = self._extract_all_dependencies(lock_data)

        if self.only_root_project:
            return updated_metadata
        if self.only_transitive:
            updated_metadata = [
                m for m in updated_metadata if m.name != self.top_package
            ]
        for dep_name, version in all_deps.items():
            # Remove ^, ~, >, or >= from version if present
            if isinstance(version, str) and version:
                if version.startswith(">="):
                    version = version[2:]
                elif version[0] in {"^", "~", ">"}:
                    version = version[1:]
            # Fetch metadata from npmjs registry API
            license = []
            copyright = []
            repository_url = None
            homepage_url = None
            try:
                resp = requests.get(
                    f"https://registry.npmjs.org/{dep_name}/{version}", timeout=5
                )
                if resp.status_code == 200:
                    pkg_data = resp.json()
                    if "license" in pkg_data and pkg_data["license"]:
                        license = [str(pkg_data["license"])]
                    if "author" in pkg_data and pkg_data["author"]:
                        if (
                            isinstance(pkg_data["author"], dict)
                            and "name" in pkg_data["author"]
                        ):
                            copyright = [str(pkg_data["author"]["name"])]
                        elif isinstance(pkg_data["author"], str):
                            copyright = [pkg_data["author"]]
                    if "repository" in pkg_data and pkg_data["repository"]:
                        repo = pkg_data["repository"]
                        if isinstance(repo, dict) and "url" in repo:
                            repository_url = repo["url"]
                        elif isinstance(repo, str):
                            repository_url = repo
                    if (
                        not repository_url
                        and "homepage" in pkg_data
                        and pkg_data["homepage"]
                    ):
                        homepage_url = pkg_data["homepage"]
            except Exception as e:
                logging.warning(
                    f"Failed to fetch npm registry metadata for "
                    f"{dep_name}@{version}: {e}"
                )
            # Set origin: prefer repository, then homepage, then npm:{name}
            if repository_url:
                origin = repository_url
            elif homepage_url:
                origin = homepage_url
            else:
                origin = f"npm:{dep_name}"
            found = False
            for meta in updated_metadata:
                if meta.name == dep_name:
                    found = True
                    # Update origin if not a valid git url or missing
                    if (
                        not meta.origin or not validate_git_url(meta.origin)
                    ) and origin:
                        meta.origin = origin
                    if not meta.license and license:
                        meta.license = license
                    if not meta.copyright and copyright:
                        meta.copyright = copyright
                    if not meta.version and version:
                        meta.version = version
                    break
            if not found:
                updated_metadata.append(
                    Metadata(
                        name=dep_name,
                        version=version,
                        origin=origin,
                        local_src_path=None,
                        license=license,
                        copyright=copyright,
                    )
                )
        return updated_metadata
