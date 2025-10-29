# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
#
# This product includes software developed at Datadog \
# (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import json
import logging

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")
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

    def _clean_version_string(self, version: str) -> str:
        if isinstance(version, str) and version:
            if version.startswith(">="):
                return version[2:]
            elif version and version[0] in {"^", "~", ">"}:
                return version[1:]
        return version

    def _extract_license_from_pkg_data(self, pkg_data: Dict[str, Any]) -> List[str]:
        if "license" in pkg_data and pkg_data["license"]:
            return [str(pkg_data["license"])]
        return []

    def _extract_copyright_from_pkg_data(self, pkg_data: Dict[str, Any]) -> List[str]:
        if not pkg_data.get("author"):
            return []

        author = pkg_data["author"]
        if isinstance(author, dict) and "name" in author:
            return [str(author["name"])]
        elif isinstance(author, str):
            return [author]
        return []

    def _fetch_npm_registry_metadata(
        self, dep_name: str, version: str
    ) -> tuple[List[str], List[str], Dict[str, Any] | None]:
        license = []
        copyright = []
        pkg_data = None

        try:
            resp = requests.get(
                f"https://registry.npmjs.org/{dep_name}/{version}",
                timeout=5,
            )
            if resp.status_code == 200:
                pkg_data = resp.json()
                license = self._extract_license_from_pkg_data(pkg_data)
                copyright = self._extract_copyright_from_pkg_data(pkg_data)
            else:
                logging.warning(
                    "Failed to fetch npm registry metadata for "
                    f"{dep_name}@{version}: {resp.status_code}, "
                    f"{resp.text}"
                )
        except Exception as e:
            logging.warning(
                "Failed to fetch npm registry metadata for "
                f"{dep_name}@{version}: {e}"
            )

        return license, copyright, pkg_data

    def _determine_origin(
        self,
        pkg_data: Dict[str, Any] | None,
        dep_name: str,
    ) -> str:
        if not pkg_data:
            return f"npm:{dep_name}"

        # Extract repository URL
        repository_url = None
        if "repository" in pkg_data and pkg_data["repository"]:
            repo = pkg_data["repository"]
            if isinstance(repo, dict) and "url" in repo:
                repository_url = repo["url"]
            elif isinstance(repo, str):
                repository_url = repo

        if repository_url:
            return str(repository_url)

        # Extract homepage URL as fallback
        if "homepage" in pkg_data and pkg_data["homepage"]:
            return str(pkg_data["homepage"])

        return f"npm:{dep_name}"

    def _enrich_root_package_from_package_json(
        self, package_json_data: Dict[str, Any], metadata: List[Metadata]
    ) -> None:
        """Enrich root package metadata from package.json.

        This method extracts license, copyright, version, and name from package.json
        and updates the root package metadata. For Node.js projects, package.json is
        the authoritative source for package metadata.

        Args:
            package_json_data: The parsed package.json data
            metadata: The list of metadata to update (modified in place)
        """
        # Extract metadata from package.json
        license = self._extract_license_from_pkg_data(package_json_data)
        copyright = self._extract_copyright_from_pkg_data(package_json_data)

        # Extract version
        version = package_json_data.get("version", None)

        # Extract name
        name = package_json_data.get("name", None)

        # Find the root package in metadata
        # The root package is identified by having an origin that matches self.top_package
        for meta in metadata:
            if meta.origin and self.top_package in meta.origin:
                # Update metadata with package.json data
                if license:
                    meta.license = license
                if copyright:
                    meta.copyright = copyright
                if version:
                    meta.version = version
                if name:
                    meta.name = name

                logger.debug(
                    f"Enriched root package from package.json: "
                    f"name={name}, version={version}, license={license}, copyright={copyright}"
                )
                break

    def _enrich_metadata_with_npm_registry(
        self, metadata: List[Metadata], dependencies: Dict[str, str]
    ) -> List[Metadata]:
        updated_metadata = metadata.copy()

        # Apply project scope filters - filter transitive-only if needed
        if self.only_transitive:
            updated_metadata = [
                m for m in updated_metadata if m.name != self.top_package
            ]

        for dep_name, version in dependencies.items():
            clean_version = self._clean_version_string(version)

            license, copyright, pkg_data = self._fetch_npm_registry_metadata(
                dep_name, clean_version
            )

            origin = self._determine_origin(pkg_data, dep_name)

            found = False
            for meta in updated_metadata:
                if meta.name == dep_name:
                    found = True
                    if (
                        not meta.origin or not validate_git_url(meta.origin)
                    ) and origin:
                        meta.origin = origin
                    if not meta.license and license:
                        meta.license = license
                    if not meta.copyright and copyright:
                        meta.copyright = copyright
                    if not meta.version and clean_version:
                        meta.version = clean_version
                    break

            if not found:
                updated_metadata.append(
                    Metadata(
                        name=dep_name,
                        version=clean_version,
                        origin=origin,
                        local_src_path=None,
                        license=license,
                        copyright=copyright,
                    )
                )

        return updated_metadata

    def _extract_all_dependencies(self, lock_data: Dict[str, Any]) -> Dict[str, str]:
        all_deps: Dict[str, str] = {}

        if "packages" not in lock_data:
            logger.warning("No 'packages' key found in package-lock.json.")
            return all_deps

        packages = lock_data["packages"]
        # Find the root package key
        root_key = "" if "" in packages else "./" if "./" in packages else None
        if root_key is None:
            logger.warning(
                "A root package wasn't found. Collecting NodeJS dependencies from none NodeJS projects is not supported yet."
            )
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

        package_json_path = path_join(project_path, "package.json")
        if not path_exists(package_json_path):
            return updated_metadata

        package_json_data = json.loads(open_file(package_json_path))
        if "workspaces" in package_json_data:
            logger.warning(
                f"Node projects using workspaces are not supported yet by the NPM collection strategy."
            )
            return updated_metadata

        # Always enrich root package from package.json for Node.js projects
        # package.json is the authoritative source for package metadata
        self._enrich_root_package_from_package_json(package_json_data, updated_metadata)

        # Early return for ONLY_ROOT_PROJECT - no need to run npm install
        if self.only_root_project:
            return updated_metadata

        # Run npm install --package-lock-only to generate package-lock.json
        try:
            output_from_command(
                f"CWD=`pwd`; cd {project_path} && "
                "npm install --package-lock-only --force; cd $CWD"
            )
        except Exception as e:
            logger.warning(f"Failed to run npm install for {self.top_package}: {e}")
            return updated_metadata
        lock_path = path_join(project_path, "package-lock.json")
        lock_data = {}
        if not path_exists(lock_path):
            logger.warning(f"No package-lock.json found in {project_path}")
            return updated_metadata
        try:
            lock_data = json.loads(open_file(lock_path))
        except Exception as e:
            logger.warning(f"Failed to read package-lock.json: {e}")
            return updated_metadata

        all_deps = self._extract_all_dependencies(lock_data)

        # Use private method to enrich metadata with NPM registry data
        # Handles scope filtering, version cleaning, fetching, and enrichment
        return self._enrich_metadata_with_npm_registry(updated_metadata, all_deps)
