# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import json
import logging
import tomllib

import semver

from dd_license_attribution.adaptors.os import (
    normalize_path,
    open_file,
    path_exists,
    path_join,
    walk_directory,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    SourceCodeManager,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.rust_collection_strategy import (
    is_rust_metadata,
)
from dd_license_attribution.utils.bounded_download import (
    DDLA_USER_AGENT,
    download_bounded,
)
from dd_license_attribution.utils.tar_archive import read_tar_gz_text_file

logger = logging.getLogger("dd_license_attribution")

CRATES_IO_API_BASE_URL = "https://crates.io/api/v1/crates"
CRATES_IO_REGISTRY_SOURCE = "registry+https://github.com/rust-lang/crates.io-index"
DEPENDENCY_TABLE_NAMES = {
    "dependencies",
    "dev-dependencies",
    "build-dependencies",
}

CrateMetadata = tuple[str | None, str | None, list[str]]


class RustCratesIoMetadataCollectionStrategy(MetadataCollectionStrategy):
    """Fill missing Rust metadata from exact packages published on crates.io."""

    def __init__(
        self,
        top_package: str,
        source_code_manager: SourceCodeManager,
        local_project_path: str | None = None,
    ) -> None:
        self.top_package = top_package
        self.source_code_manager = source_code_manager
        self.local_project_path = local_project_path

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = metadata.copy()
        project_paths = self._get_project_paths()
        locked_crate_versions: dict[str, set[str]] = {}
        manifest_crate_versions: dict[str, set[str]] = {}
        for project_path in project_paths:
            self._merge_crate_versions(
                locked_crate_versions,
                self._get_locked_crate_versions(project_path),
            )
            self._merge_crate_versions(
                manifest_crate_versions,
                self._get_manifest_crate_versions(
                    project_path,
                    include_package_version=self.local_project_path is not None,
                ),
            )

        metadata_cache: dict[tuple[str, str | None, bool], CrateMetadata | None] = {}
        for package in updated_metadata:
            if package.name is None or (
                package.name not in locked_crate_versions
                and package.name not in manifest_crate_versions
            ):
                continue
            if not self._should_enrich_package(package):
                continue

            requested_version = self._choose_requested_version(
                package.version,
                locked_crate_versions.get(package.name, set()),
                manifest_crate_versions.get(package.name, set()),
            )
            if package.version is None:
                package.version = requested_version
            if requested_version is None:
                continue
            if (
                package.license
                and package.copyright
                and self._has_usable_origin(package)
            ):
                continue

            include_authors = not package.copyright
            cache_key = (package.name, requested_version, include_authors)
            if cache_key not in metadata_cache:
                metadata_cache[cache_key] = self._get_crates_io_metadata(
                    package.name,
                    requested_version,
                    include_authors=include_authors,
                )
            crate_metadata = metadata_cache[cache_key]
            if crate_metadata is None:
                continue

            license_expression, repository, authors = crate_metadata
            if not package.license and license_expression:
                package.license = [license_expression]
            if not package.copyright and authors:
                package.copyright = [", ".join(authors)]
            if repository and (not package.origin or package.origin == package.name):
                package.origin = repository

        return updated_metadata

    def _should_enrich_package(self, package: Metadata) -> bool:
        if self.local_project_path is not None:
            return True
        return is_rust_metadata(package)

    def _has_usable_origin(self, package: Metadata) -> bool:
        return bool(package.origin and package.origin != package.name)

    def _get_project_paths(self) -> list[str]:
        if self.local_project_path is not None:
            return [self.local_project_path]

        source_code_ref = self.source_code_manager.get_code(self.top_package)
        if source_code_ref is None:
            return []

        project_paths: list[str] = []
        for root, dirs, files in walk_directory(source_code_ref.local_full_path):
            dirs[:] = [
                directory for directory in dirs if directory not in {".git", "target"}
            ]
            if "Cargo.toml" in files:
                project_paths.append(root)
                dirs[:] = []
        return project_paths

    def _get_locked_crate_versions(self, project_path: str) -> dict[str, set[str]]:
        cargo_lock_path = path_join(project_path, "Cargo.lock")
        if not path_exists(cargo_lock_path):
            return {}
        try:
            cargo_lock = tomllib.loads(open_file(cargo_lock_path))
        except (OSError, tomllib.TOMLDecodeError) as e:
            logger.warning(  # pragma: no mutate
                "Failed to parse Cargo.lock at %s: %s",
                cargo_lock_path,
                e,
            )
            return {}

        crate_versions: dict[str, set[str]] = {}
        packages = cargo_lock.get("package")
        if not isinstance(packages, list):
            return crate_versions
        for package in packages:
            if not isinstance(package, dict):
                continue
            name = package.get("name")
            version = package.get("version")
            source = package.get("source")
            if (
                isinstance(name, str)
                and isinstance(version, str)
                and source == CRATES_IO_REGISTRY_SOURCE
            ):
                crate_versions.setdefault(name, set()).add(version)
        return crate_versions

    def _get_manifest_crate_versions(
        self,
        project_path: str,
        visited_projects: set[str] | None = None,
        include_package_version: bool = False,
    ) -> dict[str, set[str]]:
        if visited_projects is None:
            visited_projects = set()
        project_path = normalize_path(project_path)
        if project_path in visited_projects:
            return {}
        visited_projects.add(project_path)

        cargo_toml_path = path_join(project_path, "Cargo.toml")
        if not path_exists(cargo_toml_path):
            return {}
        try:
            cargo_toml = tomllib.loads(open_file(cargo_toml_path))
        except (OSError, tomllib.TOMLDecodeError) as e:
            logger.warning(  # pragma: no mutate
                "Failed to parse Cargo.toml at %s: %s",
                cargo_toml_path,
                e,
            )
            return {}

        dependency_tables = self._get_dependency_tables(cargo_toml)
        crate_versions: dict[str, set[str]] = {}
        if include_package_version:
            self._merge_crate_versions(
                crate_versions,
                self._get_package_crate_version(cargo_toml),
            )
        for dependency_table in dependency_tables:
            for dependency_name, dependency_config in dependency_table.items():
                crate_name = dependency_name
                version: str | None = None
                if isinstance(dependency_config, str):
                    version = self._exact_manifest_version(dependency_config)
                elif isinstance(dependency_config, dict):
                    is_crates_io_dependency = True
                    package_name = dependency_config.get("package")
                    if isinstance(package_name, str):
                        crate_name = package_name
                    configured_version = dependency_config.get("version")
                    if isinstance(configured_version, str):
                        version = self._exact_manifest_version(configured_version)
                    dependency_path = dependency_config.get("path")
                    if isinstance(dependency_path, str):
                        is_crates_io_dependency = False
                        self._merge_crate_versions(
                            crate_versions,
                            self._get_manifest_crate_versions(
                                path_join(project_path, dependency_path),
                                visited_projects,
                            ),
                        )
                    if "git" in dependency_config:
                        is_crates_io_dependency = False
                    registry = dependency_config.get("registry")
                    if isinstance(registry, str) and registry != "crates-io":
                        is_crates_io_dependency = False
                    if not is_crates_io_dependency:
                        version = None
                if version is not None:
                    crate_versions.setdefault(crate_name, set()).add(version)
        return crate_versions

    def _get_package_crate_version(
        self,
        cargo_toml: dict[str, object],
    ) -> dict[str, set[str]]:
        package = cargo_toml.get("package")
        if not isinstance(package, dict):
            return {}

        package_name = package.get("name")
        package_version = package.get("version")
        if not isinstance(package_name, str) or not isinstance(package_version, str):
            return {}

        try:
            return {package_name: {str(semver.Version.parse(package_version))}}
        except ValueError:
            return {}

    def _exact_manifest_version(self, version_requirement: str) -> str | None:
        normalized_requirement = version_requirement.strip()
        if not normalized_requirement.startswith("="):
            return None

        requested_version = normalized_requirement[1:].strip()
        try:
            return str(semver.Version.parse(requested_version))
        except ValueError:
            return None

    def _get_dependency_tables(
        self, cargo_toml: dict[str, object]
    ) -> list[dict[str, object]]:
        dependency_tables: list[dict[str, object]] = []
        for table_name in DEPENDENCY_TABLE_NAMES:
            table = cargo_toml.get(table_name)
            if isinstance(table, dict):
                dependency_tables.append(table)

        workspace = cargo_toml.get("workspace")
        if isinstance(workspace, dict):
            workspace_dependencies = workspace.get("dependencies")
            if isinstance(workspace_dependencies, dict):
                dependency_tables.append(workspace_dependencies)

        targets = cargo_toml.get("target")
        if isinstance(targets, dict):
            for target in targets.values():
                if not isinstance(target, dict):
                    continue
                for table_name in DEPENDENCY_TABLE_NAMES:
                    table = target.get(table_name)
                    if isinstance(table, dict):
                        dependency_tables.append(table)
        return dependency_tables

    def _merge_crate_versions(
        self,
        destination: dict[str, set[str]],
        source: dict[str, set[str]],
    ) -> None:
        for crate_name, versions in source.items():
            destination.setdefault(crate_name, set()).update(versions)

    def _choose_requested_version(
        self,
        metadata_version: str | None,
        locked_candidate_versions: set[str],
        manifest_candidate_versions: set[str],
    ) -> str | None:
        locked_version = self._single_exact_version(locked_candidate_versions)
        if locked_version is not None:
            return locked_version
        if len(self._exact_versions(locked_candidate_versions)) > 1:
            return None

        if metadata_version is not None and ">=" not in metadata_version:
            preferred_version = self._preferred_crate_version(metadata_version)
            if preferred_version is not None:
                return preferred_version

        return self._single_exact_version(manifest_candidate_versions)

    def _single_exact_version(self, candidate_versions: set[str]) -> str | None:
        exact_versions = self._exact_versions(candidate_versions)
        if len(exact_versions) == 1:
            return str(max(exact_versions))
        return None

    def _exact_versions(self, candidate_versions: set[str]) -> list[semver.Version]:
        exact_versions: list[semver.Version] = []
        for version in candidate_versions:
            try:
                exact_versions.append(semver.Version.parse(version))
            except ValueError:
                continue
        return exact_versions

    def _get_crates_io_metadata(
        self,
        crate_name: str,
        requested_version: str | None,
        include_authors: bool,
    ) -> CrateMetadata | None:
        metadata_url = f"{CRATES_IO_API_BASE_URL}/{crate_name}"
        try:
            response = json.loads(
                download_bounded(
                    metadata_url,
                    user_agent=DDLA_USER_AGENT,
                ).decode("utf-8")
            )
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
            logger.warning(  # pragma: no mutate
                "Could not retrieve crates.io metadata for %s: %s",
                crate_name,
                e,
            )
            return None

        if not isinstance(response, dict):
            return None
        crate_data = response.get("crate")
        versions = response.get("versions")
        if not isinstance(crate_data, dict) or not isinstance(versions, list):
            return None

        selected_version = self._select_crate_version(
            versions,
            requested_version,
            crate_data.get("default_version"),
        )
        if selected_version is None:
            return None

        license_expression = selected_version.get("license")
        if not isinstance(license_expression, str):
            license_expression = None
        repository = selected_version.get("repository") or crate_data.get("repository")
        if not isinstance(repository, str):
            repository = None

        authors: list[str] = []
        version_number = selected_version.get("num")
        if include_authors and isinstance(version_number, str):
            authors = self._get_crate_authors(crate_name, version_number)
        return license_expression, repository, authors

    def _select_crate_version(
        self,
        versions: list[object],
        requested_version: str | None,
        _default_version: object,
    ) -> dict[str, object] | None:
        preferred_version = self._preferred_crate_version(requested_version)
        if preferred_version is None:
            return None

        for version in versions:
            if isinstance(version, dict) and version.get("num") == preferred_version:
                return version
        return None

    def _preferred_crate_version(self, requested_version: str | None) -> str | None:
        if requested_version is None:
            return None
        normalized_version = requested_version.strip()
        try:
            return str(semver.Version.parse(normalized_version))
        except ValueError:
            return None

    def _get_crate_authors(self, crate_name: str, version: str) -> list[str]:
        download_endpoint = f"{CRATES_IO_API_BASE_URL}/{crate_name}/{version}/download"
        try:
            archive_content = download_bounded(
                download_endpoint,
                user_agent=DDLA_USER_AGENT,
            )
            cargo_toml_content = read_tar_gz_text_file(
                archive_content,
                "/Cargo.toml",
            )
            if cargo_toml_content is None:
                return []
            cargo_toml = tomllib.loads(cargo_toml_content)
        except (OSError, UnicodeDecodeError, ValueError, tomllib.TOMLDecodeError) as e:
            logger.warning(  # pragma: no mutate
                "Could not retrieve crates.io authors for %s@%s: %s",
                crate_name,
                version,
                e,
            )
            return []

        package_data = cargo_toml.get("package")
        if not isinstance(package_data, dict):
            return []
        authors = package_data.get("authors")
        if not isinstance(authors, list):
            return []
        return [author for author in authors if isinstance(author, str) and author]
