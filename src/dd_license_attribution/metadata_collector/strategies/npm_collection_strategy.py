# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
#
# This product includes software developed at Datadog \
# (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import json
import logging
import re
from typing import Any

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

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")


class NpmMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(
        self,
        top_package: str,
        source_code_manager: SourceCodeManager,
        project_scope: ProjectScope,
        yarn_subdirs: list[str] | None = None,
        local_project_path: str | None = None,
    ) -> None:
        # Store original top_package for matching
        self.original_top_package = top_package
        self.local_project_path = local_project_path

        if local_project_path is not None:
            # In npm-package mode, top_package is a package name, not a URL
            self.top_package = top_package
        else:
            # Resolve canonical URL if this is a GitHub repository
            # This ensures we can match packages that were canonicalized by earlier strategies
            canonical_url, _ = source_code_manager.get_canonical_urls(top_package)
            self.top_package = canonical_url if canonical_url else top_package

        self.source_code_manager = source_code_manager
        self.only_root_project = project_scope == ProjectScope.ONLY_ROOT_PROJECT
        self.only_transitive = (
            project_scope == ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES
        )
        self.yarn_subdirs = yarn_subdirs or []

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
        self, trees: list[dict[str, Any]]
    ) -> dict[str, str]:
        """
        Extract Yarn aliases from the tree structure.
        Aliases appear in 'children' arrays with syntax: "alias@npm:real-package@version"

        Example:
          "children": [
            {"name": "string-width-cjs@npm:string-width@^4.2.0"}
          ]

        Returns mapping: {"string-width-cjs": "string-width"}
        """

        aliases: dict[str, str] = {}

        # Recursively scan all trees and their children for alias patterns
        def scan_tree(tree: dict[str, Any]) -> None:
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
                                    "Detected Yarn alias: %s -> %s",
                                    alias_name,
                                    real_name,
                                )

                    # Recursively scan this child's children
                    scan_tree(child)

        for tree in trees:
            scan_tree(tree)

        return aliases

    def _extract_aliases_from_yarn_lock(self, project_path: str) -> dict[str, str]:
        """
        Extract Yarn aliases from yarn.lock file.

        Aliases in yarn.lock appear as entries like:
          "@datadog/source-map@npm:source-map@^0.6.0":
            version "0.6.1"
            resolved "..."

        Args:
            project_path: Path to the project root containing yarn.lock

        Returns:
            Dictionary mapping alias names to real package names
            Example: {"@datadog/source-map": "source-map"}
        """
        aliases: dict[str, str] = {}
        yarn_lock_path = path_join(project_path, "yarn.lock")

        yarn_lock_content = open_file(yarn_lock_path)

        # Match patterns like: "@datadog/source-map@npm:source-map@^0.6.0":
        # This regex handles both scoped and unscoped packages
        # Group 1: alias name (may include @scope/)
        # Group 2: real package name (@scope/package or package)
        alias_pattern = re.compile(
            r'^"([^"]+)@npm:(@[^@]+|[^@]+)@[^"]+":$', re.MULTILINE
        )

        for match in alias_pattern.finditer(yarn_lock_content):
            alias_name = match.group(1)
            real_name = match.group(2)

            if alias_name not in aliases:
                aliases[alias_name] = real_name
                logger.debug(
                    "Detected Yarn alias from yarn.lock: %s -> %s",
                    alias_name,
                    real_name,
                )

        logger.debug("Extracted %d aliases from yarn.lock", len(aliases))

        return aliases

    def _get_yarn_dependencies(self, project_path: str) -> dict[str, str]:
        """Get dependencies from a Yarn project.

        Args:
            project_path: Path to the project root

        Returns:
            Dictionary mapping package names to versions
        """
        all_deps: dict[str, str] = {}
        all_trees: list[dict[str, Any]] = []

        try:
            # Use yarn list to get all dependencies (excluding dev dependencies)
            logger.debug("Running yarn list in %s", project_path)
            output = output_from_command(
                f"cd {project_path} && yarn list --production --json --non-interactive 2>&1"
            )
            logger.debug("Yarn list output length: %d characters", len(output))

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
                    "Yarn list did not produce valid JSON output. Output: %s",
                    output[:500],
                )
                return all_deps

            # Extract aliases from yarn.lock file (authoritative source)
            lock_aliases = self._extract_aliases_from_yarn_lock(project_path)
            # Extract aliases from tree children (fallback/additional source)
            tree_aliases = self._extract_yarn_aliases_from_tree(all_trees)
            # Merge aliases - yarn.lock takes precedence
            aliases = {**tree_aliases, **lock_aliases}
            logger.debug(
                "Found %d Yarn aliases (%d from yarn.lock, %d from tree)",
                len(aliases),
                len(lock_aliases),
                len(tree_aliases),
            )

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
            logger.warning("Failed to run yarn list for %s: %s", project_path, e)

        return all_deps

    def _get_npm_list_dependencies(self, project_path: str) -> dict[str, str]:
        """Get dependencies from an npm project using npm list.

        This discovers all packages npm sees, including vendored dependencies
        that are require()'d but not in package-lock.json.

        Args:
            project_path: Path to the project root

        Returns:
            Dictionary mapping package names to versions
        """
        all_deps: dict[str, str] = {}

        try:
            # Use npm list to get all dependencies (excluding dev dependencies)
            logger.debug("Running npm list in %s", project_path)
            output = output_from_command(
                f"cd {project_path} && npm list --json --production --all 2>/dev/null"
            )
            logger.debug("npm list output length: %d characters", len(output))

            # Parse JSON output (single object, not JSON Lines like yarn)
            data = json.loads(output)

            # Recursively extract all dependencies from the tree
            if "dependencies" in data:
                self._extract_npm_list_deps_recursive(data["dependencies"], all_deps)

        except json.JSONDecodeError as e:
            logger.error("npm list did not produce valid JSON: %s", e)
            return all_deps
        except Exception as e:
            logger.warning("Failed to run npm list for %s: %s", project_path, e)

        return all_deps

    def _extract_npm_list_deps_recursive(
        self, deps: dict[str, Any], all_deps: dict[str, str]
    ) -> None:
        """Recursively extract package names and versions from npm list tree.

        Args:
            deps: Dependencies dict from npm list output
            all_deps: Accumulator dict to populate (modified in place)
        """
        for pkg_name, pkg_data in deps.items():
            if not isinstance(pkg_data, dict):
                continue

            # Get version from this entry
            version = pkg_data.get("version", "")

            # Keep first version encountered per package name
            if pkg_name not in all_deps and version:
                all_deps[pkg_name] = version

            # Recursively process nested dependencies
            if "dependencies" in pkg_data:
                self._extract_npm_list_deps_recursive(
                    pkg_data["dependencies"], all_deps
                )

    def _collect_yarn_deps_from_location(
        self, location_path: str, location_name: str = "root"
    ) -> dict[str, str]:
        """Collect yarn dependencies from a specific location.

        Args:
            location_path: Full path to the directory containing yarn.lock
            location_name: Descriptive name for logging (e.g., "root", "subdir/path")

        Returns:
            Dictionary mapping package names to versions, or empty dict if yarn.lock doesn't exist
        """
        yarn_lock_path = path_join(location_path, "yarn.lock")
        if not path_exists(yarn_lock_path):
            logger.debug("No yarn.lock found at %s (%s)", location_name, location_path)
            return {}

        logger.info("Collecting yarn dependencies from %s", location_name)

        # Check if yarn is installed
        try:
            yarn_version = output_from_command("yarn --version 2>/dev/null")
            logger.debug("Yarn version: %s", yarn_version.strip())
        except Exception as e:
            logger.error(
                "Yarn is not installed or not in PATH. Please install yarn to analyze this project. Error: %s",
                e,
            )
            return {}

        # Use existing _get_yarn_dependencies method
        deps = self._get_yarn_dependencies(location_path)
        logger.info("Found %d dependencies at %s", len(deps), location_name)
        return deps

    def _extract_license_from_pkg_data(self, pkg_data: dict[str, Any]) -> list[str]:
        if "license" in pkg_data and pkg_data["license"]:
            return [str(pkg_data["license"])]
        return []

    def _extract_copyright_from_pkg_data(self, pkg_data: dict[str, Any]) -> list[str]:
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
    ) -> tuple[list[str], list[str], dict[str, Any] | None]:
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
                logger.warning(
                    "Failed to fetch npm registry metadata for "
                    f"{dep_name}@{version}: {resp.status_code}, "
                    f"{resp.text}"
                )
        except Exception as e:
            logger.warning(
                "Failed to fetch npm registry metadata for "
                f"{dep_name}@{version}: {e}"
            )

        return license, copyright, pkg_data

    def _determine_origin(
        self,
        pkg_data: dict[str, Any] | None,
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
        self, package_json_data: dict[str, Any], metadata: list[Metadata]
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
                    "Enriched root package from package.json: name=%s, version=%s, license=%s, copyright=%s",
                    name,
                    version,
                    license,
                    copyright,
                )
                break

    def _enrich_metadata_with_npm_registry(
        self, metadata: list[Metadata], dependencies: dict[str, str]
    ) -> list[Metadata]:
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
                logger.info("Progress: %d/%d dependencies processed", idx, total_deps)

            license, copyright, pkg_data = self._fetch_npm_registry_metadata(
                dep_name, version
            )

            origin = self._determine_origin(pkg_data, dep_name)

            found = False
            for meta in updated_metadata:
                # Match by both name and version to support multiple versions of same package
                if meta.name == dep_name and meta.version == version:
                    found = True
                    if (
                        not meta.origin or not validate_git_url(meta.origin)
                    ) and origin:
                        meta.origin = origin
                    if not meta.license and license:
                        meta.license = license
                    if not meta.copyright and copyright:
                        meta.copyright = copyright
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

    def _extract_aliases_from_package_lock(self, project_path: str) -> dict[str, str]:
        """
        Extract npm aliases from package-lock.json file.

        In npm v7+, aliases appear in the packages section with entries like:
          "": {
            "dependencies": {
              "@datadog/source-map": "npm:source-map@^0.6.0"
            }
          },
          "node_modules/@datadog/source-map": {
            "version": "0.6.1",
            "resolved": "https://registry.npmjs.org/source-map/-/source-map-0.6.1.tgz",
            "name": "source-map"
          }

        Args:
            project_path: Path to the project root containing package-lock.json

        Returns:
            Dictionary mapping alias names to real package names
            Example: {"@datadog/source-map": "source-map"}
        """
        aliases: dict[str, str] = {}
        package_lock_path = path_join(project_path, "package-lock.json")

        package_lock_content = open_file(package_lock_path)
        lock_data = json.loads(package_lock_content)

        if "packages" not in lock_data:
            logger.debug("No 'packages' key in package-lock.json at %s", project_path)
            return aliases

        packages = lock_data["packages"]

        # Find the root package (npm v7+ uses "" as root key)
        if "" not in packages:
            logger.debug(
                "No root package found in package-lock.json at %s", project_path
            )
            return aliases

        root_pkg = packages[""]
        dependencies = root_pkg.get("dependencies", {})

        # Check each dependency for alias syntax (npm:actual-package@version)
        for dep_name, dep_spec in dependencies.items():
            if isinstance(dep_spec, str) and dep_spec.startswith("npm:"):
                # Parse "npm:real-package@version" format
                # Remove "npm:" prefix
                real_spec = dep_spec[4:]  # Remove "npm:" prefix

                # Extract real package name (handle scoped packages)
                # Format: real-package@version or @scope/real-package@version
                if real_spec.startswith("@"):
                    # Scoped package: @scope/package@version
                    # Split on @ but keep the first @ as part of scope
                    parts = real_spec.split("@")
                    if len(parts) >= 3:  # ['', 'scope/package', 'version', ...]
                        real_name = f"@{parts[1]}"
                    else:
                        continue
                else:
                    # Unscoped package: package@version
                    parts = real_spec.split("@")
                    if len(parts) >= 2:
                        real_name = parts[0]
                    else:
                        continue

                aliases[dep_name] = real_name
                logger.debug(
                    "Detected npm alias from package-lock.json: %s -> %s",
                    dep_name,
                    real_name,
                )

        # Also check node_modules entries for name mismatches
        for key, pkg_data in packages.items():
            if key.startswith("node_modules/") and isinstance(pkg_data, dict):
                # Extract the package name from the key
                package_path = key[len("node_modules/") :]

                # Check if the "name" field exists and differs from the path
                actual_name = pkg_data.get("name")
                if actual_name and actual_name != package_path:
                    # This is an alias - the path is the alias, name is real
                    aliases[package_path] = actual_name
                    logger.debug(
                        "Detected npm alias from node_modules entry: %s -> %s",
                        package_path,
                        actual_name,
                    )

        logger.debug("Extracted %d aliases from package-lock.json", len(aliases))

        return aliases

    def _get_npm_dependencies(
        self, lock_data: dict[str, Any], project_path: str
    ) -> dict[str, str]:
        all_deps: dict[str, str] = {}

        if "packages" not in lock_data:
            logger.warning("No 'packages' key found in package-lock.json.")
            return all_deps

        packages = lock_data["packages"]

        # Extract aliases from package-lock.json
        aliases = self._extract_aliases_from_package_lock(project_path)
        logger.debug("Found %d npm aliases in package-lock.json", len(aliases))

        # Iterate all entries in packages that start with "node_modules/"
        # This discovers all dependencies (direct, transitive, nested, optional, peer)
        # without requiring BFS tree-walking through the dependencies field.
        for key, pkg_data in packages.items():
            if not key.startswith("node_modules/"):
                continue
            if not isinstance(pkg_data, dict):
                continue

            # Skip entries without a resolved version
            if "version" not in pkg_data:
                continue

            # Skip dev-only dependencies
            if pkg_data.get("dev", False):
                continue

            # Extract package name from the key (handles nested and scoped packages)
            pkg_name = key.rsplit("node_modules/", 1)[-1]

            # Resolve alias to real package name
            real_name = aliases.get(pkg_name, pkg_name)

            # Keep first version encountered per package name
            if real_name not in all_deps:
                all_deps[real_name] = pkg_data["version"]

        return all_deps

    def _augment_metadata_from_local_path(
        self, metadata: list[Metadata]
    ) -> list[Metadata]:
        """Handle augment_metadata when local_project_path is set (npm-package mode).

        In this mode, the local_project_path contains a synthetic project with
        package-lock.json generated by NpmPackageResolver. We skip get_code() and
        root package.json enrichment since the package.json is synthetic.
        """
        # Remove the seed entry created by MetadataCollector for the target package.
        # The seed has version=None and origin set to the bare package name, which
        # would cause a duplicate once _enrich_metadata_with_npm_registry adds a
        # properly versioned entry from the npm registry.
        updated_metadata = [
            m
            for m in metadata
            if not (m.name == self.top_package and m.version is None)
        ]
        project_path = self.local_project_path
        assert project_path is not None

        if self.only_root_project:
            # For ONLY_ROOT_PROJECT, fetch root package metadata from npm registry
            name, version = self._resolve_root_package_version(project_path)
            if name is None:
                logger.warning(
                    "Could not resolve root package from lock file at %s",
                    project_path,
                )
                return updated_metadata

            license, copyright, pkg_data = self._fetch_npm_registry_metadata(
                name, version
            )
            origin = self._determine_origin(pkg_data, name)

            updated_metadata.append(
                Metadata(
                    name=name,
                    version=version,
                    origin=origin,
                    local_src_path=None,
                    license=license,
                    copyright=copyright,
                )
            )
            return updated_metadata

        # For ALL or ONLY_TRANSITIVE_DEPENDENCIES: use npm list to discover all dependencies
        try:
            # First ensure dependencies are installed
            logger.debug("Running npm install for %s", project_path)
            output_from_command(
                f"CWD=`pwd`; cd {project_path} && npm install --production; cd $CWD"
            )

            # Then use npm list to discover all packages
            all_deps = self._get_npm_list_dependencies(project_path)

        except Exception as e:
            logger.warning(
                "Failed to run npm install/list for %s: %s", self.top_package, e
            )
            return updated_metadata

        if not all_deps:
            logger.warning("No dependencies extracted from %s", project_path)
            return updated_metadata

        logger.info("Found %d unique packages", len(all_deps))

        updated_metadata = self._enrich_metadata_with_npm_registry(
            updated_metadata, all_deps
        )

        return updated_metadata

    def _resolve_root_package_version(
        self, project_path: str
    ) -> tuple[str | None, str]:
        """Resolve the target package name and version from the lock file.

        The synthetic package.json has the target package as the sole dependency.
        We look it up in the lock file to get the resolved version.
        """
        lock_path = path_join(project_path, "package-lock.json")
        if not path_exists(lock_path):
            return None, ""

        try:
            lock_data = json.loads(open_file(lock_path))
        except Exception:
            return None, ""

        packages = lock_data.get("packages", {})
        root_pkg = packages.get("", {})
        deps = root_pkg.get("dependencies", {})

        if not deps:
            return None, ""

        # The first (and only) dependency is the target package
        dep_name = next(iter(deps))
        node_modules_key = f"node_modules/{dep_name}"
        version = packages.get(node_modules_key, {}).get("version", "")
        return dep_name, version

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = metadata.copy()

        if self.local_project_path is not None:
            return self._augment_metadata_from_local_path(updated_metadata)

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
                "Node projects using workspaces are not supported yet by the NPM collection strategy."
            )
            return updated_metadata

        self._enrich_root_package_from_package_json(package_json_data, updated_metadata)

        # Early return for ONLY_ROOT_PROJECT - no need to run npm install
        if self.only_root_project:
            return updated_metadata

        # Detect package manager (npm or yarn)
        package_manager = self._detect_package_manager(project_path)
        logger.info("Detected package manager: %s", package_manager)

        all_deps: dict[str, str] = {}

        if package_manager == "yarn":
            # Collect dependencies from multiple locations (root + subdirs)
            # Use a set to keep all unique (package, version) combinations
            unique_deps: set[tuple[str, str]] = set()

            # Collect from root
            root_deps = self._collect_yarn_deps_from_location(project_path, "root")
            for pkg, ver in root_deps.items():
                unique_deps.add((pkg, ver))

            # Collect from subdirectories
            for subdir in self.yarn_subdirs:
                subdir_path = path_join(project_path, subdir)
                if not path_exists(subdir_path):
                    logger.warning(
                        "Subdirectory %s does not exist in %s", subdir, project_path
                    )
                    continue

                subdir_deps = self._collect_yarn_deps_from_location(subdir_path, subdir)
                for pkg, ver in subdir_deps.items():
                    unique_deps.add((pkg, ver))

            # Group dependencies by package name to identify multiple versions
            deps_by_package: dict[str, list[str]] = {}
            for pkg, ver in unique_deps:
                if pkg not in deps_by_package:
                    deps_by_package[pkg] = []
                if ver not in deps_by_package[pkg]:
                    deps_by_package[pkg].append(ver)

            # Log packages with multiple versions
            for pkg, versions in deps_by_package.items():
                if len(versions) > 1:
                    logger.info(
                        "Package %s has multiple versions: %s",
                        pkg,
                        ", ".join(sorted(versions)),
                    )

            # Flatten to dict - use first version for each package
            # We'll handle multiple versions by processing all combinations
            all_deps = {pkg: versions[0] for pkg, versions in deps_by_package.items()}

            if not all_deps:
                logger.warning(
                    "No dependencies found for Yarn project at %s and subdirectories",
                    project_path,
                )
        else:
            # For npm projects, use npm list to discover all dependencies
            # This includes vendored packages that are require()'d but not in package-lock.json
            try:
                # First ensure dependencies are installed
                logger.debug("Running npm install for %s", project_path)
                output_from_command(
                    f"CWD=`pwd`; cd {project_path} && npm install --production; cd $CWD"
                )

                # Then use npm list to discover all packages
                all_deps = self._get_npm_list_dependencies(project_path)

            except Exception as e:
                logger.warning(
                    "Failed to run npm install/list for %s: %s", self.top_package, e
                )
                return updated_metadata

        if not all_deps:
            logger.warning("No dependencies extracted from %s", project_path)
            return updated_metadata

        logger.info("Found %d unique packages", len(all_deps))

        # Use private method to enrich metadata with NPM registry data
        # Handles scope filtering, version cleaning, fetching, and enrichment
        updated_metadata = self._enrich_metadata_with_npm_registry(
            updated_metadata, all_deps
        )

        # For yarn, process additional versions of packages (if any)
        if package_manager == "yarn":
            # Process additional versions (versions beyond the first for each package)
            additional_deps: dict[str, str] = {}
            for pkg, versions in deps_by_package.items():
                for ver in versions[1:]:  # Skip first version (already processed)
                    additional_deps[pkg] = ver

            if additional_deps:
                logger.info(
                    "Processing %d additional package versions", len(additional_deps)
                )
                updated_metadata = self._enrich_metadata_with_npm_registry(
                    updated_metadata, additional_deps
                )

        return updated_metadata
