import scancode.api
from ospo_tools.adaptors.os import list_dir, walk_directory

from ospo_tools.artifact_management.source_code_manager import (
    SourceCodeManager,
    SourceCodeReference,
)
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


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
            if package.local_src_path is not None:
                # if we have a local source path from package manager, we use that
                source_code_reference = SourceCodeReference(
                    repo_url=package.origin,
                    branch="",
                    local_root_path=package.local_src_path,
                    local_full_path=package.local_src_path,
                )
            # otherwise we make a shallow clone of the repository or read a cache of it
            else:
                source_code_reference_or_none = self.source_code_manager.get_code(
                    package.origin, force_update=False
                )
                if not source_code_reference_or_none:
                    updated_metadata.append(package)
                    continue
                else:
                    source_code_reference = source_code_reference_or_none

            if not package.license:
                # get list of files at the base directory of the repository to attempt to find licenses
                # filter files to be only the ones that are in the license source files list (non case sensitive)
                files = self._get_candidate_files(
                    source_code_reference, self.license_source_files, False
                )
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
                files = self._get_candidate_files(
                    source_code_reference, self.copyright_source_files, True
                )
                for file in files:
                    copyright = scancode.api.get_copyrights(file)
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

    def _filter_candidate_files(
        self, root: str, all_files: list[str], filter_files: list[str] | None
    ) -> list[str]:
        return [
            f"{root}/{file}"
            for file in all_files
            if filter_files is None or file.lower() in filter_files
        ]

    def _get_candidate_files(
        self,
        source_code_reference: SourceCodeReference,
        filter_files: list[str] | None,
        recurse: bool,
    ) -> list[str]:
        # we always explore non recursively the root, and may take the full_path recursively if enabled
        candidates = []
        if recurse:
            for root, _, all_files in walk_directory(
                source_code_reference.local_full_path
            ):
                if ".git" in root.split("/"):
                    continue
                candidates.extend(
                    self._filter_candidate_files(root, all_files, filter_files)
                )
        else:
            candidates = self._filter_candidate_files(
                source_code_reference.local_full_path,
                list_dir(source_code_reference.local_full_path),
                filter_files,
            )
        if (
            source_code_reference.local_root_path
            != source_code_reference.local_full_path
        ):
            # we need to add the root, non recursive, list of files to the candidates
            candidates.extend(
                self._filter_candidate_files(
                    source_code_reference.local_root_path,
                    list_dir(source_code_reference.local_root_path),
                    filter_files,
                )
            )
        return candidates

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
