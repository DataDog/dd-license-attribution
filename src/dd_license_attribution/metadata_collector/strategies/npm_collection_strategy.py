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
        # Store original top_package for matching
        self.original_top_package = top_package
        # Resolve canonical URL if this is a GitHub repository
        # This ensures we can match packages that were canonicalized by earlier strategies
        canonical_url, _ = source_code_manager.get_canonical_urls(top_package)
        self.top_package = canonical_url if canonical_url else top_package
        self.source_code_manager = source_code_manager
        self.only_root_project = project_scope == ProjectScope.ONLY_ROOT_PROJECT
        self.only_transitive = (
            project_scope == ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES
        )

    def _detect_package_manager(self, project_path: str) -> str:
        """Detect whether the project uses npm or yarn.

        Args:
            project_path: Path to the project root

        Returns:
            "yarn" if yarn.lock exists, "npm" otherwise
        """
        yarn_lock_path = path_join(project_path, "yarn.lock")
        if path_exists(yarn_lock_path):
            return "yarn"
        return "npm"

    def _extract_yarn_aliases_from_tree(
        self, trees: List[Dict[str, Any]]
    ) -> Dict[str, str]:
        """
        Extract Yarn aliases from the tree structure.
        Aliases appear in 'children' arrays with syntax: "alias@npm:real-package@version"

        Example:
          "children": [
            {"name": "string-width-cjs@npm:string-width@^4.2.0"}
          ]

        Returns mapping: {"string-width-cjs": "string-width"}
        """
        import re

        aliases: Dict[str, str] = {}

        # Recursively scan all trees and their children for alias patterns
        def scan_tree(tree: Dict[str, Any]) -> None:
            # Check children for alias patterns
            children = tree.get("children", [])
            for child in children:
                if isinstance(child, dict):
                    child_name = child.get("name", "")
                    if child_name:
                        # Match alias pattern: "alias@npm:real-package@version"
                        alias_match = re.match(
                            r"^([^@]+)@npm:([^@]+)@(.+)$", child_name
                        )
                        if alias_match:
                            alias_name = alias_match.group(1)
                            real_name = alias_match.group(2)
                            if alias_name not in aliases:
                                aliases[alias_name] = real_name
                                logger.debug(
                                    f"Detected Yarn alias: {alias_name} -> {real_name}"
                                )

                    # Recursively scan this child's children
                    scan_tree(child)

        for tree in trees:
            scan_tree(tree)

        return aliases

    def _get_yarn_dependencies(self, project_path: str) -> Dict[str, str]:
        """Get dependencies from a Yarn project.

        Args:
            project_path: Path to the project root

        Returns:
            Dictionary mapping package names to versions
        """
        all_deps: Dict[str, str] = {}
        all_trees: List[Dict[str, Any]] = []

        try:
            # Use yarn list to get all dependencies (excluding dev dependencies)
            logger.debug(f"Running yarn list in {project_path}")
            output = output_from_command(
                f"cd {project_path} && yarn list --production --json --non-interactive 2>&1"
            )
            logger.debug(f"Yarn list output length: {len(output)} characters")

            # Check if yarn command failed
            if not output or len(output.strip()) == 0:
                logger.error("Yarn list produced no output")
                return all_deps

            # First pass: collect all trees
            for line in output.strip().split("\n"):
                if not line or not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    if data.get("type") == "tree":
                        trees = data.get("data", {}).get("trees", [])
                        all_trees.extend(trees)
                except json.JSONDecodeError:
                    continue

            # Check if we got any valid tree data
            if not all_trees:
                logger.error(
                    f"Yarn list did not produce valid JSON output. Output: {output[:500]}"
                )
                return all_deps

            # Extract aliases from all trees (they appear in children arrays)
            aliases = self._extract_yarn_aliases_from_tree(all_trees)
            logger.debug(f"Found {len(aliases)} Yarn aliases")

            # Second pass: process packages and resolve aliases
            for tree in all_trees:
                name = tree.get("name", "")
                if not name:
                    continue

                # Parse "package@version" format
                # Handle scoped packages like "@datadog/libdatadog@1.0.0"
                if name.startswith("@"):
                    # Scoped package: @scope/package@version
                    parts = name.rsplit("@", 1)
                    if len(parts) == 2:
                        pkg_name, version = parts
                        # Resolve alias if present
                        resolved_name = aliases.get(pkg_name, pkg_name)
                        all_deps[resolved_name] = version
                elif "@" in name:
                    # Regular package: package@version
                    parts = name.rsplit("@", 1)
                    if len(parts) == 2:
                        pkg_name, version = parts
                        # Resolve alias if present
                        resolved_name = aliases.get(pkg_name, pkg_name)
                        all_deps[resolved_name] = version
                else:
                    # No version in name (shouldn't happen but handle it)
                    resolved_name = aliases.get(name, name)
                    all_deps[resolved_name] = ""

        except Exception as e:
            logger.warning(f"Failed to run yarn list for {project_path}: {e}")

        return all_deps

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
        # The root package is typically the first entry, or one whose origin matches our top_package URLs
        for idx, meta in enumerate(metadata):
            # Match if it's the first entry, or if origin contains either canonical or original top_package
            is_root = meta.origin and (
                self.top_package in meta.origin
                or self.original_top_package in meta.origin
            )

            if is_root:
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

        total_deps = len(dependencies)
        logger.info(
            f"Fetching metadata from npm registry for {total_deps} dependencies..."
        )

        for idx, (dep_name, version) in enumerate(dependencies.items(), 1):
            if idx % 50 == 0 or idx == total_deps:
                logger.info(f"Progress: {idx}/{total_deps} dependencies processed")
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

    def _get_npm_dependencies(self, lock_data: Dict[str, Any]) -> Dict[str, str]:
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

        # Early return for ONLY_ROOT_PROJECT - no need to run npm install
        if self.only_root_project:
            return updated_metadata

        # Detect package manager (npm or yarn)
        package_manager = self._detect_package_manager(project_path)
        logger.info(f"Detected package manager: {package_manager}")

        all_deps: Dict[str, str] = {}

        if package_manager == "yarn":
            # Check if yarn is installed
            try:
                yarn_version = output_from_command("yarn --version 2>/dev/null")
                logger.debug(f"Yarn version: {yarn_version.strip()}")
            except Exception as e:
                logger.error(
                    f"Yarn is not installed or not in PATH. Please install yarn to analyze this project. Error: {e}"
                )
                return updated_metadata

            # For Yarn projects, use yarn list to get dependencies
            all_deps = self._get_yarn_dependencies(project_path)
            if not all_deps:
                logger.warning(
                    f"No dependencies found for Yarn project at {project_path}"
                )
        else:
            # For npm projects, use the existing npm logic
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
            if not path_exists(lock_path):
                logger.warning(f"No package-lock.json found in {project_path}")
                return updated_metadata

            try:
                lock_data = json.loads(open_file(lock_path))
                all_deps = self._get_npm_dependencies(lock_data)
            except Exception as e:
                logger.warning(f"Failed to read package-lock.json: {e}")
                return updated_metadata

        if not all_deps:
            logger.warning(f"No dependencies extracted from {project_path}")
            return updated_metadata

        logger.info(f"Found {len(all_deps)} dependencies")

        # Use private method to enrich metadata with NPM registry data
        # Handles scope filtering, version cleaning, fetching, and enrichment
        return self._enrich_metadata_with_npm_registry(updated_metadata, all_deps)
