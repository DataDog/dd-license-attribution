# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json
import logging
import re

from dd_license_attribution.adaptors.os import (
    open_file,
    output_from_command,
    walk_directory,
)
from dd_license_attribution.artifact_management.go_package_resolver import (
    SYNTHETIC_MODULE_NAME,
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


class GoPkgMetadataCollectionStrategy(MetadataCollectionStrategy):
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
        self._head_branch_cache: dict[str, str] = {}

        if local_project_path is not None:
            # In go-package mode, top_package is a Go import path, not a URL
            self.top_package = top_package
        else:
            # Resolve canonical URL if this is a GitHub repository
            canonical_url, _ = source_code_manager.get_canonical_urls(top_package)
            self.top_package = canonical_url if canonical_url else top_package

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = metadata.copy()

        if self.local_project_path is not None:
            return self._augment_metadata_from_local_path(updated_metadata)

        # Get the source code directory
        source_code_ref = self.source_code_manager.get_code(self.top_package)

        # Walk through the directory to find go.mod files
        if not source_code_ref:
            return metadata
        for root, _, files in walk_directory(source_code_ref.local_full_path):
            if "go.mod" in files:
                if self._is_example_package(root):
                    continue
                # Run the go list command to get the package details
                output = output_from_command(
                    f"CWD=`pwd`; cd {root} && go list -json all; cd $CWD"
                )
                corrected_output = "[{}]".format(output.replace("}\n{", "},\n{"))
                package_data_list = json.loads(corrected_output)

                for package_data in package_data_list:
                    if "Module" not in package_data:
                        continue
                    if self.only_root_project:
                        if not any(
                            meta.name == package_data["Module"]["Path"]
                            for meta in metadata
                        ):
                            continue
                    version = None
                    if "Version" in package_data["Module"]:
                        version = package_data["Module"]["Version"]
                    # Extract metadata from the package data
                    package_metadata = Metadata(
                        name=package_data["Module"]["Path"],
                        origin=self._translate_github_path(
                            package_data["Module"]["Path"]
                        ),
                        local_src_path=package_data["Module"]["Dir"],
                        license=[],
                        version=version,
                        copyright=[],
                    )

                    # Add or update the metadata list
                    saved = False
                    for i, meta in enumerate(metadata):
                        if meta.name == package_metadata.name:
                            metadata[i].origin = package_metadata.origin
                            metadata[i].local_src_path = package_metadata.local_src_path
                            metadata[i].version = (
                                package_metadata.version
                                if package_metadata.version is not None
                                else metadata[i].version
                            )
                            saved = True
                            break
                    if not saved:
                        metadata.append(package_metadata)

        return metadata

    def _augment_metadata_from_local_path(
        self, metadata: list[Metadata]
    ) -> list[Metadata]:
        """Handle augment_metadata when local_project_path is set (go-package mode).

        In this mode, the local_project_path contains a synthetic Go project with
        go.mod generated by GoPackageResolver. We skip get_code() and run
        go list -json all directly in the local project directory.
        """
        # Remove the seed entry created by MetadataCollector
        metadata = [
            m
            for m in metadata
            if not (m.name == self.top_package and m.version is None)
        ]
        project_path = self.local_project_path
        assert project_path is not None

        output = output_from_command(
            f"CWD=`pwd`; cd {project_path} && go list -json all; cd $CWD"
        )
        if not output.strip():
            logger.warning("go list produced no output in %s", project_path)
            return metadata

        corrected_output = "[{}]".format(output.replace("}\n{", "},\n{"))
        package_data_list = json.loads(corrected_output)

        for package_data in package_data_list:
            if "Module" not in package_data:
                continue
            module_path = package_data["Module"]["Path"]

            # Filter out the synthetic module
            if module_path == SYNTHETIC_MODULE_NAME:
                continue

            if self.only_root_project:
                if not any(meta.name == module_path for meta in metadata):
                    continue

            version = None
            if "Version" in package_data["Module"]:
                version = package_data["Module"]["Version"]

            package_metadata = Metadata(
                name=module_path,
                origin=self._translate_github_path(module_path),
                local_src_path=package_data["Module"]["Dir"],
                license=[],
                version=version,
                copyright=[],
            )

            # Add or update the metadata list
            saved = False
            for i, meta in enumerate(metadata):
                if meta.name == package_metadata.name:
                    metadata[i].origin = package_metadata.origin
                    metadata[i].local_src_path = package_metadata.local_src_path
                    metadata[i].version = (
                        package_metadata.version
                        if package_metadata.version is not None
                        else metadata[i].version
                    )
                    saved = True
                    break
            if not saved:
                metadata.append(package_metadata)

        return metadata

    def _translate_github_path(self, path: str) -> str:
        if not path.startswith("github.com"):
            return f"https://{path}"
        parts = path.split("/", 3)
        if len(parts) > 3:
            # GoPkg has no info about what branch was used, assuming the HEAD.
            # Use branch cache initialized in constructor
            repo_url = f"https://{parts[0]}/{parts[1]}/{parts[2]}"
            if repo_url not in self._head_branch_cache:
                self._head_branch_cache[repo_url] = (
                    output_from_command(f"git ls-remote --symref {repo_url} HEAD")
                    .split()[1]
                    .removeprefix("refs/heads/")
                )
            branch = self._head_branch_cache[repo_url]
            return f"{repo_url}/tree/{branch}/{parts[3]}"
        return f"https://{path}"

    def _is_example_package(self, go_mod_path: str) -> bool:
        # a module is an example, if the name ends with /examples and requires the main module
        module_name = None
        requires_main_module = False

        file = open_file(f"{go_mod_path}/go.mod")

        if not file:
            return False
        for line in file.splitlines():
            line = line.strip()
            module_match = re.match(r"^module\s+(\S+)", line)
            if module_match:
                module_name = module_match.group(1)
            require_match = re.match(r"^require\s+(\S+)\s+v[\d\.]+", line)
            if require_match:
                required_module = require_match.group(1)
                # Check if required module is a parent module
                if module_name and required_module in module_name:
                    requires_main_module = True

        # The module name should end with /examples and require the main module
        return bool(
            module_name and module_name.endswith("/examples") and requires_main_module
        )
