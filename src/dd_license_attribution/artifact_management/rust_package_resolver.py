# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import json
import logging
import re

from dd_license_attribution.adaptors.os import (
    create_dirs,
    format_command_output,
    path_exists,
    path_join,
    run_command_with_check,
    write_file,
)

logger = logging.getLogger("dd_license_attribution")

SYNTHETIC_PACKAGE_NAME = "ddla-rust-resolve"


class RustPackageResolver:
    """Resolves a Rust crate specifier into a local Cargo project directory."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = working_dir

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

    def resolve_package(self, rust_package_spec: str) -> str | None:
        """Resolve a Rust crate spec into a local directory with Cargo.lock."""
        name, version = self._parse_rust_spec(rust_package_spec)
        logger.info("Resolving Rust crate: %s@%s", name, version)

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
            f"{json.dumps(name)} = {json.dumps(version)}\n"
        )
        cargo_toml_path = path_join(resolve_dir, "Cargo.toml")
        src_dir = path_join(resolve_dir, "src")
        main_rs_path = path_join(src_dir, "main.rs")
        try:
            write_file(cargo_toml_path, cargo_toml_content)
            create_dirs(src_dir)
            write_file(main_rs_path, "fn main() {}\n")
        except OSError as e:
            logger.error(
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
                logger.error(
                    "cargo generate-lockfile failed for %s: %s",
                    rust_package_spec,
                    format_command_output(output, error_output),
                )
                return None
        except OSError as e:
            logger.error("Failed to resolve Rust crate %s: %s", rust_package_spec, e)
            return None

        cargo_lock_path = path_join(resolve_dir, "Cargo.lock")
        if not path_exists(cargo_lock_path):
            logger.error(
                "cargo generate-lockfile did not create Cargo.lock in %s",
                resolve_dir,
            )
            return None

        logger.info(
            "Successfully resolved Rust crate %s to %s",
            rust_package_spec,
            resolve_dir,
        )
        return resolve_dir
