import os
from typing import Iterator
import scancode.api


from ospo_tools.artifact_management.source_code_manager import SourceCodeManager
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


def list_dir(path: str) -> list[str]:
    return os.listdir(path)


def walk_directory(path: str) -> Iterator[tuple[str, list[str], list[str]]]:
    return os.walk(path)


class ScanCodeToolkitMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(
        self,
        source_code_manager: SourceCodeManager,
        license_source_files: list[str] | None = None,
        copyright_source_files: list[str] | None = None,
    ) -> None:
        self.source_code_manager = source_code_manager
        # save the source files lists
        self.license_source_files: list[str] | None = None
        if license_source_files is not None:
            self.license_source_files = [file.lower() for file in license_source_files]
        self.copyright_source_files: list[str] | None = None
        if copyright_source_files is not None:
            self.copyright_source_files = [
                file.lower() for file in copyright_source_files
            ]

    # method to get the metadata
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = []
        for package in metadata:
            # if the package has a license and a copyright
            if not package.origin or (package.license and package.copyright):
                updated_metadata.append(package)
                continue
            # otherwise we make a shallow clone of the repository or read a cache of it
            source_code_reference = self.source_code_manager.get_code(
                package.origin, force_update=False
            )
            if not source_code_reference:
                updated_metadata.append(package)
                continue

            if not package.license:
                # get list of files at the base directory of the repository to attempt to find licenses
                # filter files to be only the ones that are in the license source files list (non case sensitive)
                if not self.license_source_files:
                    files = list_dir(source_code_reference.local_root_path)
                    if (
                        source_code_reference.local_full_path
                        != source_code_reference.local_root_path
                    ):
                        for file in list_dir(
                            source_code_reference.local_full_path
                        ):  # for projects in subdirectories
                            files.append(
                                source_code_reference.local_full_path + "/" + file
                            )
                else:
                    files = [
                        source_code_reference.local_root_path + "/" + file
                        for file in list_dir(source_code_reference.local_root_path)
                        if file.lower() in self.license_source_files
                    ]
                    if (
                        source_code_reference.local_full_path
                        != source_code_reference.local_root_path
                    ):
                        files_subdirectory = [
                            source_code_reference.local_full_path + "/" + file
                            for file in list_dir(source_code_reference.local_full_path)
                            if file.lower() in self.license_source_files
                        ]
                        files.extend(files_subdirectory)
                # get the license for each file
                licenses = []
                for file_abs_path in files:
                    license = scancode.api.get_licenses(file_abs_path)
                    if (
                        "detected_license_expression_spdx" in license
                        and license["detected_license_expression_spdx"]
                    ):
                        licenses.append(license["detected_license_expression_spdx"])
                # if we found a license, we update the package metadata
                if licenses:
                    package.license = self.cleanup_licenses(licenses)
            # copyright
            if not package.copyright:
                copyrights: dict[str, list[str]] = {
                    "holders": [],
                    "authors": [],
                    "copyrights": [],
                }
                # get list of all files to attempt to find copyright information
                for root, _, all_files in walk_directory(
                    source_code_reference.local_root_path
                ):
                    # filter the files to be only the ones that are in the copyright source files
                    files = []
                    if (
                        root == source_code_reference.local_root_path
                    ) or root.startswith(source_code_reference.local_full_path):
                        if not self.copyright_source_files:
                            files = all_files
                        else:
                            files = [
                                file
                                for file in all_files
                                if file.lower() in self.copyright_source_files
                            ]
                    for file in files:
                        file_abs_path = f"{root}/{file}"
                        copyright = scancode.api.get_copyrights(file_abs_path)
                        if copyright["holders"]:
                            for c in copyright["holders"]:
                                copyrights["holders"].append(c["holder"])
                        elif copyright["authors"]:
                            for c in copyright["authors"]:
                                copyrights["authors"].append(c["author"])
                        elif copyright["copyrights"]:
                            for c in copyright["copyrights"]:
                                copyrights["copyrights"].append(c["copyright"])
                # If we find a declaration of copyright holders, we use that.
                if copyrights["holders"]:
                    # remove duplicates
                    package.copyright = list(set(copyrights["holders"]))
                # If we do not find a declaration of holders, we use the authors.
                elif copyrights["authors"]:
                    # remove duplicates
                    package.copyright = list(set(copyrights["authors"]))
                # If we do not find a declaration of holders or authors, we use the copyrights disclaimers in raw.
                elif copyrights["copyrights"]:
                    # remove duplicates
                    package.copyright = list(set(copyrights["copyrights"]))
                else:
                    package.copyright = []
            updated_metadata.append(package)
        return updated_metadata

    @staticmethod
    def cleanup_licenses(licenses: list[str]) -> list[str]:
        # split the licenses by 'AND'
        ret_licenses = []
        for license in licenses:
            ret_licenses.extend(license.split(" AND "))
        # remove duplicates
        ret_licenses = list(set(ret_licenses))
        # remove the unknown licenses
        unknown_license = "LicenseRef-scancode-unknown-license-reference"
        ret_licenses = [
            license for license in ret_licenses if license != unknown_license
        ]
        # remove generic clas
        generic_cla = "LicenseRef-scancode-generic-cla"
        ret_licenses = [license for license in ret_licenses if license != generic_cla]
        return ret_licenses
