# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import csv
import io
import logging
import tomllib

from dd_license_attribution.adaptors.os import (
    format_command_output,
    open_file,
    path_exists,
    path_join,
    run_command_with_check,
    walk_directory,
)
from dd_license_attribution.artifact_management.rust_package_resolver import (
    SYNTHETIC_PACKAGE_NAME,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    SourceCodeManager,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)

logger = logging.getLogger("dd_license_attribution")

RUST_LICENSE_TOOL_COMMAND = "dd-rust-license-tool"
RUST_LICENSE_TOOL_INSTALL_HINT = (
    "dd-rust-license-tool is required for Rust dependency analysis. "
    "Install it with `cargo install dd-rust-license-tool` and see the README "
    "Requirements section."
)


class RustLicenseToolNotInstalledError(RuntimeError):
    """Raised when dd-rust-license-tool is required but not available."""


def ensure_rust_license_tool_installed() -> None:
    try:
        exit_code, output, error_output = run_command_with_check(
            [RUST_LICENSE_TOOL_COMMAND, "--version"]
        )
    except FileNotFoundError as e:
        raise RustLicenseToolNotInstalledError(RUST_LICENSE_TOOL_INSTALL_HINT) from e
    except OSError as e:
        raise RustLicenseToolNotInstalledError(RUST_LICENSE_TOOL_INSTALL_HINT) from e

    if exit_code != 0:
        command_output = format_command_output(output, error_output)
        raise RustLicenseToolNotInstalledError(
            f"{RUST_LICENSE_TOOL_INSTALL_HINT} "
            f"`{RUST_LICENSE_TOOL_COMMAND} --version` failed: {command_output}"
        )


def _looks_like_missing_binary(error_text: str) -> bool:
    normalized_error = error_text.lower()
    return RUST_LICENSE_TOOL_COMMAND in normalized_error and (
        "not found" in normalized_error
        or "no such file" in normalized_error
        or "could not execute" in normalized_error
    )


class RustMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(
        self,
        top_package: str,
        source_code_manager: SourceCodeManager,
        project_scope: ProjectScope,
        local_project_path: str | None = None,
    ) -> None:
        self.local_project_path = local_project_path
        self.source_code_manager = source_code_manager
        self.only_root_project = project_scope == ProjectScope.ONLY_ROOT_PROJECT
        self.only_transitive = (
            project_scope == ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES
        )

        if local_project_path is not None:
            self.top_package = top_package
        else:
            canonical_url, _ = source_code_manager.get_canonical_urls(top_package)
            self.top_package = canonical_url if canonical_url else top_package

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = metadata.copy()

        if self.local_project_path is not None:
            return self._augment_metadata_from_local_path(updated_metadata)

        source_code_ref = self.source_code_manager.get_code(self.top_package)
        if not source_code_ref:
            return updated_metadata

        cargo_project_roots = self._find_cargo_project_roots(
            source_code_ref.local_full_path
        )
        for project_path in cargo_project_roots:
            root_package_names = self._get_root_package_names(project_path)
            rows = self._collect_rows_from_project(project_path)
            self._ingest_rows(updated_metadata, rows, root_package_names)

        return updated_metadata

    def _augment_metadata_from_local_path(
        self, metadata: list[Metadata]
    ) -> list[Metadata]:
        root_package_names = {self._parse_crate_name(self.top_package)}
        metadata = [
            m
            for m in metadata
            if m.name
            not in {self.top_package, self._parse_crate_name(self.top_package)}
        ]

        project_path = self.local_project_path
        if project_path is None:
            raise ValueError(
                "local_project_path must be set before calling this method"
            )

        rows = self._collect_rows_from_project(project_path)
        self._ingest_rows(metadata, rows, root_package_names)
        return metadata

    def _find_cargo_project_roots(self, source_root: str) -> list[str]:
        cargo_project_roots: list[str] = []
        for root, dirs, files in walk_directory(source_root):
            dirs[:] = [d for d in dirs if d not in {".git", "target"}]
            if "Cargo.toml" in files:
                cargo_project_roots.append(root)
                dirs[:] = []
        return cargo_project_roots

    def _collect_rows_from_project(self, project_path: str) -> list[dict[str, str]]:
        try:
            exit_code, output, error_output = run_command_with_check(
                [RUST_LICENSE_TOOL_COMMAND, "dump"],
                cwd=project_path,
            )
        except FileNotFoundError as e:
            raise RustLicenseToolNotInstalledError(
                RUST_LICENSE_TOOL_INSTALL_HINT
            ) from e
        except OSError as e:
            if _looks_like_missing_binary(str(e)):
                raise RustLicenseToolNotInstalledError(
                    RUST_LICENSE_TOOL_INSTALL_HINT
                ) from e
            logger.warning(  # pragma: no mutate
                "Failed to run dd-rust-license-tool in %s: %s",
                project_path,
                e,
            )
            return []

        command_output = format_command_output(output, error_output)
        if exit_code != 0:
            if _looks_like_missing_binary(command_output):
                raise RustLicenseToolNotInstalledError(RUST_LICENSE_TOOL_INSTALL_HINT)
            logger.warning(  # pragma: no mutate
                "dd-rust-license-tool failed in %s: %s",
                project_path,
                command_output,
            )
            return []

        if not output.strip():
            logger.warning(  # pragma: no mutate
                "dd-rust-license-tool produced no CSV output in %s: %s",
                project_path,
                command_output or "no stdout or stderr",
            )
            return []

        return self._parse_csv(output)

    def _parse_csv(self, content: str) -> list[dict[str, str]]:
        reader = csv.DictReader(io.StringIO(content))
        required_columns = {"Component", "Origin", "License", "Copyright"}
        if reader.fieldnames is None or not required_columns.issubset(
            set(reader.fieldnames)
        ):
            logger.warning(  # pragma: no mutate
                "dd-rust-license-tool CSV did not contain expected columns: %s",
                reader.fieldnames,
            )
            return []

        rows: list[dict[str, str]] = []
        for row in reader:
            rows.append(
                {
                    "Component": row.get("Component") or "",
                    "Origin": row.get("Origin") or "",
                    "License": row.get("License") or "",
                    "Copyright": row.get("Copyright") or "",
                }
            )
        return rows

    def _ingest_rows(
        self,
        metadata: list[Metadata],
        rows: list[dict[str, str]],
        root_package_names: set[str],
    ) -> None:
        for row in rows:
            component = row["Component"]
            if component == SYNTHETIC_PACKAGE_NAME:
                continue
            if self.only_root_project and component not in root_package_names:
                continue
            if self.only_transitive and component in root_package_names:
                continue

            row_metadata = Metadata(
                name=component,
                origin=row["Origin"],
                local_src_path=None,
                license=[row["License"]] if row["License"] else [],
                version=None,
                copyright=[row["Copyright"]] if row["Copyright"] else [],
            )
            self._upsert_metadata(metadata, row_metadata)

    def _upsert_metadata(
        self, metadata: list[Metadata], new_metadata: Metadata
    ) -> None:
        for existing in metadata:
            if existing.name != new_metadata.name:
                continue

            if new_metadata.origin:
                existing.origin = new_metadata.origin
            if existing.local_src_path is None:
                existing.local_src_path = new_metadata.local_src_path
            if existing.version is None:
                existing.version = new_metadata.version
            if not existing.license:
                existing.license = new_metadata.license
            if not existing.copyright:
                existing.copyright = new_metadata.copyright
            return

        metadata.append(new_metadata)

    def _get_root_package_names(self, project_path: str) -> set[str]:
        package_name = self._read_cargo_package_name(project_path)
        if package_name is None:
            return set()
        return {package_name}

    def _read_cargo_package_name(self, project_path: str) -> str | None:
        cargo_toml_path = path_join(project_path, "Cargo.toml")
        if not path_exists(cargo_toml_path):
            return None

        try:
            cargo_toml = tomllib.loads(open_file(cargo_toml_path))
        except tomllib.TOMLDecodeError as e:
            logger.warning(  # pragma: no mutate
                "Failed to parse Cargo.toml at %s: %s", cargo_toml_path, e
            )
            return None

        package_data = cargo_toml.get("package")
        if not isinstance(package_data, dict):
            return None

        name = package_data.get("name")
        if isinstance(name, str):
            return name
        return None

    def _parse_crate_name(self, spec: str) -> str:
        return spec.split("@", 1)[0]
