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
    format_command_output,
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

# Marker in `go mod tidy` stderr that identifies the case where the import
# path resolved to a module whose root directory has no importable Go package
# (e.g. github.com/DataDog/package-blast-radius, whose code lives in cmd/ and
# internal/ only).
_MODULE_WITHOUT_ROOT_PACKAGE_ERROR_MARKER = "does not contain package"

# Captures the package path token in a `go mod tidy` "does not contain
# package <path>" failure (the path ends at the following whitespace or
# punctuation). Used to require the missing package to be the requested
# import path itself rather than a subpackage under it.
_MISSING_PACKAGE_PATTERN = re.compile(
    rf"but {_MODULE_WITHOUT_ROOT_PACKAGE_ERROR_MARKER} (\S+)"
)


def _is_rootless_module_tidy_failure(error_output: str, import_path: str) -> bool:
    """Check whether a `go mod tidy` failure is the rootless-module case.

    The failure specific to a module whose root has no importable package
    names the requested import path as both the module (``module
    <import_path>@<version>``) and the missing package (``but does not contain
    package <import_path>``). Requiring the module anchor and an exact match
    of the missing-package token prevents misclassifying other ``does not
    contain package`` failures as this case: a missing subpackage under a
    valid root module (``but does not contain package <import_path>/sub``)
    or a missing transitive import inside a dependency module would otherwise
    let resolution succeed with an incomplete SBOM.
    """
    return f"module {import_path}@" in error_output and any(
        match.group(1) == import_path
        for match in _MISSING_PACKAGE_PATTERN.finditer(error_output)
    )


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
            raw = output_from_command(["go", "env", "GOVERSION"]).strip()
            # raw is like "go1.22.5" — extract "1.22"
            match = re.match(r"go(\d+\.\d+)", raw)
            if match:
                return match.group(1)
        except OSError:
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

    def _resolve_module_graph(
        self, resolve_dir: str, main_go_path: str, go_package_spec: str
    ) -> str | None:
        """Resolve a module that has no importable root package.

        ``go get`` has already added the module requirement to the synthetic
        go.mod. This removes the unresolvable blank import (so that module
        enumeration commands do not fail on it) and verifies the module graph
        with ``go list -m all``. The transitive dependency closure is then
        enumerated at the module level by the collection strategy using
        ``go list -m -json all``.

        Returns the resolve directory on success, None on failure.
        """
        write_file(main_go_path, "package main\n\nfunc main() {}\n")
        try:
            exit_code, output, error_output = run_command_with_check(
                ["go", "list", "-m", "all"],
                cwd=resolve_dir,
                env={"GOTOOLCHAIN": "auto"},
            )
        except OSError as e:
            logger.error("Failed to resolve Go package %s: %s", go_package_spec, e)
            return None
        if exit_code != 0:
            logger.error(
                "go list -m all failed for %s: %s",
                go_package_spec,
                format_command_output(output, error_output),
            )
            return None
        module_paths = [line.split()[0] for line in output.splitlines() if line.strip()]
        if not any(path != SYNTHETIC_MODULE_NAME for path in module_paths):
            logger.error(
                "go list -m all found no dependency modules for %s", go_package_spec
            )
            return None
        logger.info(
            "Import path %s resolved as a module without a root package; "
            "enumerating its dependencies from the module graph instead",
            go_package_spec,
        )
        return resolve_dir

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
            f'package main\n\nimport _ "{import_path}"\n\nfunc main() {{}}\n'
        )
        main_go_path = path_join(resolve_dir, "main.go")
        write_file(main_go_path, main_go_content)

        # Use go get to add the dependency. This correctly resolves the module
        # from a package path (e.g. testify/assert -> testify module) and pins
        # the version. Without a version, go get fetches the latest.
        try:
            get_arg = f"{import_path}@{version}" if version else import_path
            exit_code, output, error_output = run_command_with_check(
                ["go", "get", get_arg],
                cwd=resolve_dir,
                env={"GOTOOLCHAIN": "auto"},
            )
            if exit_code != 0:
                logger.error(
                    "go get failed for %s: %s",
                    go_package_spec,
                    format_command_output(output, error_output),
                )
                return None
        except OSError as e:
            logger.error("Failed to resolve Go package %s: %s", go_package_spec, e)
            return None

        # Run go mod tidy to resolve transitive dependencies and download modules
        try:
            exit_code, output, error_output = run_command_with_check(
                ["go", "mod", "tidy"],
                cwd=resolve_dir,
                env={"GOTOOLCHAIN": "auto"},
            )
            if exit_code != 0:
                if _is_rootless_module_tidy_failure(error_output, import_path):
                    # The import path resolved to a module whose root has no
                    # importable package. Fall back to module-graph resolution,
                    # which keeps the requirement added by `go get` and lets
                    # the collector enumerate modules with `go list -m all`.
                    return self._resolve_module_graph(
                        resolve_dir, main_go_path, go_package_spec
                    )
                logger.error(
                    "go mod tidy failed for %s: %s",
                    go_package_spec,
                    format_command_output(output, error_output),
                )
                return None
        except OSError as e:
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
