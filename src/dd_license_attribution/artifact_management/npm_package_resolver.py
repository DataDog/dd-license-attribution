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
    output_from_command,
    path_join,
    write_file,
)

logger = logging.getLogger("dd_license_attribution")


class NpmPackageResolver:
    """Resolves an npm package specifier into a local project directory
    containing a package-lock.json with the full dependency tree."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = working_dir

    def _parse_npm_spec(self, spec: str) -> tuple[str, str]:
        """Parse an npm package specifier into (name, version).

        Handles:
          - express -> ("express", "latest")
          - express@4.18.2 -> ("express", "4.18.2")
          - @scope/pkg -> ("@scope/pkg", "latest")
          - @scope/pkg@1.0.0 -> ("@scope/pkg", "1.0.0")
        """
        if spec.startswith("@"):
            # Scoped package: @scope/pkg or @scope/pkg@version
            match = re.match(r"^(@[^/]+/[^@]+)(?:@(.+))?$", spec)
            if match:
                name = match.group(1)
                version = match.group(2) or "latest"
                return name, version
            return spec, "latest"
        else:
            # Unscoped package: pkg or pkg@version
            parts = spec.split("@", 1)
            if len(parts) == 2 and parts[1]:
                return parts[0], parts[1]
            return parts[0], "latest"

    def resolve_package(self, npm_package_spec: str) -> str | None:
        """Resolve an npm package spec into a local directory with package-lock.json.

        Creates a minimal project, runs npm install --package-lock-only, and returns
        the project directory path. Returns None on failure.
        """
        name, version = self._parse_npm_spec(npm_package_spec)
        logger.info("Resolving npm package: %s@%s", name, version)

        # Create a sanitized directory name
        sanitized_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        resolve_dir = path_join(self.working_dir, sanitized_name)
        create_dirs(resolve_dir)

        # Write a minimal package.json
        package_json = json.dumps(
            {
                "name": "ddla-npm-resolve",
                "private": True,
                "dependencies": {name: version},
            }
        )
        package_json_path = path_join(resolve_dir, "package.json")
        write_file(package_json_path, package_json)

        # Run npm install --package-lock-only to resolve the dependency tree
        try:
            output_from_command(
                f"CWD=`pwd`; cd {resolve_dir} && "
                "npm install --package-lock-only --force; cd $CWD"
            )
        except Exception as e:
            logger.error(
                "Failed to resolve npm package %s: %s", npm_package_spec, e
            )
            return None

        logger.info("Successfully resolved npm package %s to %s", npm_package_spec, resolve_dir)
        return resolve_dir
