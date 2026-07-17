# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import json
import logging
import re
import tomllib
from typing import Any
from urllib.parse import quote

from dd_license_attribution.adaptors.os import (
    create_dirs,
    download_url,
    extract_tar_gz,
    format_command_output,
    open_file,
    path_exists,
    path_join,
    run_command_with_check,
    write_file,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    NonAccessibleRepository,
    SourceCodeManager,
    UnauthorizedRepository,
)

logger = logging.getLogger("dd_license_attribution")

SYNTHETIC_PACKAGE_NAME = "ddla-rust-resolve"
LICENSE_TOOL_CONFIG_NAME = "license-tool.toml"
CRATES_IO_USER_AGENT = (
    "dd-license-attribution (https://github.com/DataDog/dd-license-attribution)"
)
EXACT_VERSION_PATTERN = re.compile(
    r"\d+(?:\.\d+){0,2}(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
)


class RustPackageResolver:
    """Resolves a Rust crate specifier into a local Cargo project directory."""

    def __init__(
        self,
        working_dir: str,
        source_code_manager: SourceCodeManager | None = None,
    ) -> None:
        self.working_dir = working_dir
        self.source_code_manager = source_code_manager

    def _parse_rust_spec(self, spec: str) -> tuple[str, str]:
        """Parse a Rust crate specifier into (name, version).

        Handles:
          - serde -> ("serde", "*")
          - serde@1.0 -> ("serde", "1.0")
          - tokio@^1.37 -> ("tokio", "^1.37")
        """
        parts = spec.split("@", 1)
        name = parts[0]
        version = parts[1] if len(parts) == 2 and parts[1] else "*"
        return name, version

    def _cargo_version_requirement(self, version: str) -> str:
        """Convert an unadorned crate version into an exact Cargo requirement."""
        if EXACT_VERSION_PATTERN.fullmatch(version):
            return f"={version}"
        return version

    def resolve_package(self, rust_package_spec: str) -> str | None:
        """Resolve a Rust crate spec into a local directory with Cargo.lock."""
        name, version = self._parse_rust_spec(rust_package_spec)
        version_requirement = self._cargo_version_requirement(version)
        logger.info("Resolving Rust crate: %s@%s", name, version)  # pragma: no mutate

        sanitized_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        resolve_dir = path_join(self.working_dir, sanitized_name)
        create_dirs(resolve_dir)

        cargo_toml_content = (
            "[package]\n"
            f"name = {json.dumps(SYNTHETIC_PACKAGE_NAME)}\n"
            'version = "0.0.0"\n'
            'edition = "2021"\n'
            "publish = false\n"
            "\n"
            "[dependencies]\n"
            f"{json.dumps(name)} = {json.dumps(version_requirement)}\n"
        )
        cargo_toml_path = path_join(resolve_dir, "Cargo.toml")
        src_dir = path_join(resolve_dir, "src")
        main_rs_path = path_join(src_dir, "main.rs")
        try:
            write_file(cargo_toml_path, cargo_toml_content)
            create_dirs(src_dir)
            write_file(main_rs_path, "fn main() {}\n")
        except OSError as e:
            logger.error(  # pragma: no mutate
                "Failed to write synthetic Cargo project for %s: %s",
                rust_package_spec,
                e,
            )
            return None

        try:
            exit_code, output, error_output = run_command_with_check(
                ["cargo", "generate-lockfile"],
                cwd=resolve_dir,
            )
            if exit_code != 0:
                logger.error(  # pragma: no mutate
                    "cargo generate-lockfile failed for %s: %s",
                    rust_package_spec,
                    format_command_output(output, error_output),
                )
                return None
        except OSError as e:
            logger.error(  # pragma: no mutate
                "Failed to resolve Rust crate %s: %s", rust_package_spec, e
            )
            return None

        cargo_lock_path = path_join(resolve_dir, "Cargo.lock")
        if not path_exists(cargo_lock_path):
            logger.error(  # pragma: no mutate
                "cargo generate-lockfile did not create Cargo.lock in %s",
                resolve_dir,
            )
            return None

        try:
            exit_code, output, error_output = run_command_with_check(
                ["cargo", "metadata", "--format-version", "1"],
                cwd=resolve_dir,
            )
            if exit_code != 0:
                logger.error(  # pragma: no mutate
                    "cargo metadata failed for %s: %s",
                    rust_package_spec,
                    format_command_output(output, error_output),
                )
                return None
        except OSError as e:
            logger.error(  # pragma: no mutate
                "Failed to inspect resolved Rust crate %s: %s",
                rust_package_spec,
                e,
            )
            return None

        metadata_contains_crate = self._metadata_contains_crate(output, name)
        if metadata_contains_crate is None:
            return None

        if metadata_contains_crate:
            return self._resolve_crate_from_source(
                name,
                rust_package_spec,
                resolve_dir,
                cargo_lock_path,
                self._get_crate_repository(output, name),
            )

        if not self._metadata_reports_missing_lib_target(error_output, name):
            logger.error(  # pragma: no mutate
                "cargo metadata did not include Rust crate %s and did not report "
                "a missing lib target: %s",
                rust_package_spec,
                format_command_output(output, error_output) or "no output",
            )
            return None

        logger.info(  # pragma: no mutate
            "Rust crate %s has no lib target; falling back to crates.io source",
            rust_package_spec,
        )
        resolved_version = self._get_resolved_crate_version(
            cargo_lock_path,
            name,
        )
        if resolved_version is None:
            logger.error(  # pragma: no mutate
                "Could not find resolved version for Rust crate %s in %s",
                rust_package_spec,
                cargo_lock_path,
            )
            return None

        repository = (
            self._get_crates_io_repository(name, resolved_version)
            if self.source_code_manager is not None
            else None
        )
        return self._resolve_crate_from_source(
            name,
            rust_package_spec,
            resolve_dir,
            cargo_lock_path,
            repository,
            resolved_version,
        )

    def _metadata_contains_crate(
        self, metadata_output: str, crate_name: str
    ) -> bool | None:
        try:
            metadata: Any = json.loads(metadata_output)
        except json.JSONDecodeError as e:
            logger.error(  # pragma: no mutate
                "Failed to parse cargo metadata output: %s", e
            )
            return None

        if not isinstance(metadata, dict):
            logger.error(  # pragma: no mutate
                "cargo metadata output was not a JSON object"
            )
            return None

        packages = metadata.get("packages")
        if not isinstance(packages, list):
            logger.error(  # pragma: no mutate
                "cargo metadata output did not contain a packages list"
            )
            return None

        for package in packages:
            if isinstance(package, dict) and package.get("name") == crate_name:
                return True
        return False

    def _copy_license_tool_config(
        self,
        repository: str | None,
        crate_name: str,
        resolve_dir: str,
    ) -> None:
        if self.source_code_manager is None:
            return

        if repository is None:
            logger.debug(
                "Rust crate %s does not declare a repository; no %s to copy",
                crate_name,
                LICENSE_TOOL_CONFIG_NAME,
            )
            return

        try:
            source_code_ref = self.source_code_manager.get_code(repository)
        except (NonAccessibleRepository, UnauthorizedRepository) as e:
            logger.warning(  # pragma: no mutate
                "Could not retrieve repository configuration for Rust crate %s: %s",
                crate_name,
                e,
            )
            return

        if source_code_ref is None:
            logger.debug(
                "Could not retrieve repository %s for Rust crate %s",
                repository,
                crate_name,
            )
            return

        source_config_path = path_join(
            source_code_ref.local_full_path,
            LICENSE_TOOL_CONFIG_NAME,
        )
        if not path_exists(source_config_path):
            logger.debug(
                "Rust crate repository %s does not contain %s",
                repository,
                LICENSE_TOOL_CONFIG_NAME,
            )
            return

        destination_config_path = path_join(resolve_dir, LICENSE_TOOL_CONFIG_NAME)
        try:
            write_file(destination_config_path, open_file(source_config_path))
        except OSError as e:
            logger.warning(  # pragma: no mutate
                "Could not copy %s for Rust crate %s: %s",
                LICENSE_TOOL_CONFIG_NAME,
                crate_name,
                e,
            )
            return

        logger.info(  # pragma: no mutate
            "Using %s from %s for Rust crate %s",
            LICENSE_TOOL_CONFIG_NAME,
            repository,
            crate_name,
        )

    def _get_crate_repository(
        self,
        metadata_output: str,
        crate_name: str,
    ) -> str | None:
        metadata: Any = json.loads(metadata_output)
        packages = metadata["packages"]
        for package in packages:
            if not isinstance(package, dict) or package.get("name") != crate_name:
                continue
            repository = package.get("repository")
            if isinstance(repository, str) and repository:
                return repository
            return None
        return None

    def _get_crates_io_repository(
        self, crate_name: str, crate_version: str
    ) -> str | None:
        metadata_endpoint = (
            "https://crates.io/api/v1/crates/"
            f"{quote(crate_name, safe='')}/{quote(crate_version, safe='')}"
        )
        try:
            crates_io_metadata: Any = json.loads(
                download_url(
                    metadata_endpoint,
                    user_agent=CRATES_IO_USER_AGENT,
                )
            )
        except (json.JSONDecodeError, OSError, UnicodeDecodeError) as e:
            logger.warning(  # pragma: no mutate
                "Could not retrieve crates.io metadata for Rust crate %s: %s",
                crate_name,
                e,
            )
            return None

        if not isinstance(crates_io_metadata, dict):
            return None

        version_metadata = crates_io_metadata.get("version")
        if not isinstance(version_metadata, dict):
            return None

        repository = version_metadata.get("repository")
        if isinstance(repository, str) and repository:
            return repository
        return None

    def _metadata_reports_missing_lib_target(
        self, error_output: str, crate_name: str
    ) -> bool:
        normalized_error = error_output.lower()
        normalized_crate_name = crate_name.lower()
        return (
            normalized_crate_name in normalized_error
            and "missing a lib target" in normalized_error
            and "ignoring invalid dependency" in normalized_error
        )

    def _resolve_crate_from_source(
        self,
        crate_name: str,
        rust_package_spec: str,
        resolve_dir: str,
        cargo_lock_path: str,
        repository: str | None,
        resolved_version: str | None = None,
    ) -> str | None:
        if resolved_version is None:
            resolved_version = self._get_resolved_crate_version(
                cargo_lock_path,
                crate_name,
            )
        if resolved_version is None:
            logger.error(  # pragma: no mutate
                "Could not find resolved version for Rust crate %s in %s",
                rust_package_spec,
                cargo_lock_path,
            )
            return None

        download_endpoint = self._crates_io_download_url(crate_name, resolved_version)
        source_parent_dir = path_join(resolve_dir, "crate-source")
        create_dirs(source_parent_dir)

        try:
            archive_content = download_url(
                download_endpoint,
                user_agent=CRATES_IO_USER_AGENT,
            )
            extracted_members = extract_tar_gz(archive_content, source_parent_dir)
        except (OSError, ValueError) as e:
            logger.error(  # pragma: no mutate
                "Failed to download or extract Rust crate source for %s: %s",
                rust_package_spec,
                e,
            )
            return None

        source_root = self._get_extracted_crate_root(
            source_parent_dir,
            extracted_members,
            crate_name,
            resolved_version,
        )
        if source_root is None:
            logger.error(  # pragma: no mutate
                "Could not identify extracted source root for Rust crate %s",
                rust_package_spec,
            )
            return None

        cargo_toml_path = path_join(source_root, "Cargo.toml")
        if not path_exists(cargo_toml_path):
            logger.error(  # pragma: no mutate
                "Extracted Rust crate source for %s did not contain Cargo.toml at %s",
                rust_package_spec,
                cargo_toml_path,
            )
            return None

        self._copy_license_tool_config(repository, crate_name, source_root)
        logger.info(  # pragma: no mutate
            "Successfully resolved Rust crate %s to published source at %s",
            rust_package_spec,
            source_root,
        )
        return source_root

    def _get_resolved_crate_version(
        self, cargo_lock_path: str, crate_name: str
    ) -> str | None:
        try:
            cargo_lock: Any = tomllib.loads(open_file(cargo_lock_path))
        except OSError as e:
            logger.error(  # pragma: no mutate
                "Failed to read Cargo.lock at %s: %s", cargo_lock_path, e
            )
            return None
        except tomllib.TOMLDecodeError as e:
            logger.error(  # pragma: no mutate
                "Failed to parse Cargo.lock at %s: %s", cargo_lock_path, e
            )
            return None

        if not isinstance(cargo_lock, dict):
            logger.error(  # pragma: no mutate
                "Cargo.lock at %s was not a TOML table", cargo_lock_path
            )
            return None

        packages = cargo_lock.get("package")
        if not isinstance(packages, list):
            logger.error(  # pragma: no mutate
                "Cargo.lock at %s did not contain packages", cargo_lock_path
            )
            return None

        for package in packages:
            if not isinstance(package, dict) or package.get("name") != crate_name:
                continue

            version = package.get("version")
            if isinstance(version, str):
                return version

        return None

    def _crates_io_download_url(self, crate_name: str, version: str) -> str:
        return (
            "https://crates.io/api/v1/crates/"
            f"{quote(crate_name, safe='')}/{quote(version, safe='')}/download"
        )

    def _get_extracted_crate_root(
        self,
        source_parent_dir: str,
        extracted_members: list[str],
        crate_name: str,
        version: str,
    ) -> str | None:
        expected_root = f"{crate_name}-{version}"
        if any(
            member == expected_root or member.startswith(f"{expected_root}/")
            for member in extracted_members
        ):
            return path_join(source_parent_dir, expected_root)

        top_level_names = {
            member.split("/", 1)[0]
            for member in extracted_members
            if member and member.split("/", 1)[0]
        }
        if len(top_level_names) == 1:
            return path_join(source_parent_dir, next(iter(top_level_names)))

        return None
