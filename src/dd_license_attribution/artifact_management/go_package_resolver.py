# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import logging
import re

from dd_license_attribution.adaptors.os import (
    create_dirs,
    output_from_command,
    path_exists,
    path_join,
    run_command_with_check,
    write_file,
)

logger = logging.getLogger("dd_license_attribution")

# Name of the synthetic wrapper module created by GoPackageResolver.
# Used by GoPkgMetadataCollectionStrategy to filter it from go list output.
SYNTHETIC_MODULE_NAME = "ddla-go-resolve"


class GoPackageResolver:
    """Resolves a Go package/module specifier into a local project directory
    containing a synthetic go.mod with resolved dependencies."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = working_dir

    def _detect_go_version(self) -> str:
        """Detect the installed Go version for use in the synthetic go.mod.

        Falls back to "1.22" if detection fails.
        """
        try:
            raw = output_from_command("go env GOVERSION").strip()
            # raw is like "go1.22.5" — extract "1.22"
            match = re.match(r"go(\d+\.\d+)", raw)
            if match:
                return match.group(1)
        except Exception:
            pass
        return "1.22"

    def _parse_go_spec(self, spec: str) -> tuple[str, str]:
        """Parse a Go package specifier into (import_path, version).

        Handles:
          - github.com/stretchr/testify -> ("github.com/stretchr/testify", "")
          - github.com/stretchr/testify@v1.9.0 -> ("github.com/stretchr/testify", "v1.9.0")
          - github.com/DataDog/dd-trace-go/v2/ddtrace/tracer -> ("github.com/DataDog/dd-trace-go/v2/ddtrace/tracer", "")
          - github.com/DataDog/dd-trace-go/v2@v2.0.0 -> ("github.com/DataDog/dd-trace-go/v2", "v2.0.0")
        """
        parts = spec.split("@", 1)
        import_path = parts[0]
        version = parts[1] if len(parts) == 2 and parts[1] else ""

        # Normalize version: Go versions must start with 'v'
        if version and not version.startswith("v"):
            version = "v" + version

        return import_path, version

    def resolve_package(self, go_package_spec: str) -> str | None:
        """Resolve a Go package spec into a local directory with a synthetic go.mod.

        Creates a minimal Go module that imports the target package, runs
        `go mod tidy` to resolve the dependency tree, and returns the
        project directory path. Returns None on failure.
        """
        import_path, version = self._parse_go_spec(go_package_spec)

        # Validate to prevent command injection before interpolating into shell commands
        if not re.fullmatch(r"[a-zA-Z0-9.\-_/]+", import_path):
            logger.error("Invalid Go import path rejected: %s", import_path)
            return None
        if version and not re.fullmatch(r"v[0-9a-zA-Z.\-+]+", version):
            logger.error("Invalid Go version string rejected: %s", version)
            return None

        logger.info(
            "Resolving Go package: %s (version: %s)", import_path, version or "latest"
        )

        # Create a sanitized directory name
        sanitized_name = re.sub(r"[^a-zA-Z0-9_-]", "_", import_path)
        resolve_dir = path_join(self.working_dir, sanitized_name)
        create_dirs(resolve_dir)

        # Write a synthetic go.mod using the installed Go version
        go_version = self._detect_go_version()
        go_mod_content = f"module {SYNTHETIC_MODULE_NAME}\n\ngo {go_version}\n"
        go_mod_path = path_join(resolve_dir, "go.mod")
        write_file(go_mod_path, go_mod_content)

        # Write a synthetic main.go that imports the package.
        # The blank import ensures go mod tidy resolves the package's module
        # and all its transitive dependencies via GOPROXY.
        main_go_content = (
            "package main\n" "\n" f'import _ "{import_path}"\n' "\n" "func main() {}\n"
        )
        main_go_path = path_join(resolve_dir, "main.go")
        write_file(main_go_path, main_go_content)

        # Use go get to add the dependency. This correctly resolves the module
        # from a package path (e.g. testify/assert -> testify module) and pins
        # the version. Without a version, go get fetches the latest.
        try:
            get_arg = f"{import_path}@{version}" if version else import_path
            exit_code, output = run_command_with_check(
                f"GOTOOLCHAIN=auto go get {get_arg}",
                cwd=resolve_dir,
            )
            if exit_code != 0:
                logger.error("go get failed for %s: %s", go_package_spec, output)
                return None
        except Exception as e:
            logger.error("Failed to resolve Go package %s: %s", go_package_spec, e)
            return None

        # Run go mod tidy to resolve transitive dependencies and download modules
        try:
            exit_code, output = run_command_with_check(
                "GOTOOLCHAIN=auto go mod tidy",
                cwd=resolve_dir,
            )
            if exit_code != 0:
                logger.error("go mod tidy failed for %s: %s", go_package_spec, output)
                return None
        except Exception as e:
            logger.error("Failed to resolve Go package %s: %s", go_package_spec, e)
            return None

        # Verify that go.sum was created (confirms dependency resolution succeeded)
        go_sum_path = path_join(resolve_dir, "go.sum")
        if not path_exists(go_sum_path):
            logger.error("go mod tidy did not create go.sum in %s", resolve_dir)
            return None

        logger.info(
            "Successfully resolved Go package %s to %s",
            go_package_spec,
            resolve_dir,
        )
        return resolve_dir
