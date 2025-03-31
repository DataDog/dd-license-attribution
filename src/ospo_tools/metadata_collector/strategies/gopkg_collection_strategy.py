# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json
import re
from ospo_tools.artifact_management.source_code_manager import SourceCodeManager
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.project_scope import ProjectScope
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from ospo_tools.adaptors.os import output_from_command, walk_directory, open_file


class GoPkgMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(
        self,
        top_package: str,
        source_code_manager: SourceCodeManager,
        project_scope: ProjectScope,
    ) -> None:
        self.top_package = top_package
        self.source_code_manager = source_code_manager
        self.only_root_project = project_scope == ProjectScope.ONLY_ROOT_PROJECT

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
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
                corrected_output = (
                    "[" + output.replace("}\n{", "},\n{") + "]"
                )  # Correct the output to be a valid JSON array
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

    def _translate_github_path(self, path: str) -> str:
        if not path.startswith("github.com"):
            return f"https://{path}"
        parts = path.split("/", 3)
        if len(parts) > 3:
            # GoPkg has no info about what branch was used, assuming the HEAD.
            branch = (
                output_from_command(
                    f"git ls-remote --symref https://{parts[0]}/{parts[1]}/{parts[2]} HEAD"
                )
                .split()[1]
                .removeprefix("refs/heads/")
            )
            return f"https://{parts[0]}/{parts[1]}/{parts[2]}/tree/{branch}/{parts[3]}"
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
