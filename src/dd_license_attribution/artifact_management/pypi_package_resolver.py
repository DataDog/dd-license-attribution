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
    path_exists,
    path_join,
    write_file,
)

logger = logging.getLogger("dd_license_attribution")

# Name of the synthetic wrapper project created by PypiPackageResolver.
# Used by PypiMetadataCollectionStrategy to filter it from pip list output.
SYNTHETIC_PROJECT_NAME = "ddla-pypi-resolve"


class PypiPackageResolver:
    """Resolves a PyPI package specifier into a local project directory
    containing a minimal pyproject.toml with the package as a dependency."""

    def __init__(self, working_dir: str) -> None:
        self.working_dir = working_dir

    def _parse_pypi_spec(self, spec: str) -> tuple[str, str]:
        """Parse a PyPI package specifier into (name, version_constraint).

        Handles:
          - requests -> ("requests", "")
          - requests==2.31.0 -> ("requests", "==2.31.0")
          - requests>=2.0 -> ("requests", ">=2.0")
          - Flask[async]==2.0.0 -> ("Flask[async]", "==2.0.0")
          - package~=1.0 -> ("package", "~=1.0")
        """
        match = re.match(r"^([A-Za-z0-9._\-\[\]]+)((?:==|>=|<=|!=|~=|>|<).+)?$", spec)
        if match:
            name = match.group(1)
            version = match.group(2) or ""
            return name, version
        return spec, ""

    def resolve_package(self, pypi_package_spec: str) -> str | None:
        """Resolve a PyPI package spec into a local directory with a minimal pyproject.toml.

        Creates a minimal installable project so PythonEnvManager can process it.
        Returns the project directory path, or None on failure.
        """
        name, version = self._parse_pypi_spec(pypi_package_spec)
        logger.info("Resolving PyPI package: %s%s", name, version)

        sanitized_name = re.sub(r"[^a-zA-Z0-9_-]", "_", name)
        resolve_dir = path_join(self.working_dir, sanitized_name)
        create_dirs(resolve_dir)

        install_requires_entry = f"{name}{version}"
        pyproject_toml_content = (
            "[build-system]\n"
            'requires = ["setuptools"]\n'
            'build-backend = "setuptools.build_meta"\n'
            "\n"
            "[project]\n"
            f'name = "{SYNTHETIC_PROJECT_NAME}"\n'
            'version = "0.0.1"\n'
            f"dependencies = [{install_requires_entry!r}]\n"
        )

        pyproject_toml_path = path_join(resolve_dir, "pyproject.toml")
        try:
            write_file(pyproject_toml_path, pyproject_toml_content)
        except OSError as e:
            logger.error(
                "Failed to write pyproject.toml for %s: %s", pypi_package_spec, e
            )
            return None

        if not path_exists(pyproject_toml_path):
            logger.error("pyproject.toml was not created in %s", resolve_dir)
            return None

        logger.info(
            "Successfully resolved PyPI package %s to %s",
            pypi_package_spec,
            resolve_dir,
        )
        return resolve_dir
