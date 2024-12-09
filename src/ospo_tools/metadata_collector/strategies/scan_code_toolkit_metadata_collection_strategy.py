import tempfile
import os
from shlex import quote
from typing import Iterator
import scancode.api


from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from giturlparse import parse as parse_git_url


def list_dir(path: str) -> list[str]:
    return os.listdir(path)


def path_exists(file_path: str) -> bool:
    return os.path.exists(file_path)


def walk_directory(path: str) -> Iterator[tuple[str, list[str], list[str]]]:
    return os.walk(path)


class ScanCodeToolkitMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(
        self,
        license_source_files: list[str] | None = None,
        copyright_source_files: list[str] | None = None,
    ) -> None:
        # create a temporary directory for github shallow clones
        self.temp_dir = tempfile.TemporaryDirectory()
        # in the temporary directory make a shallow clone of the repository
        self.temp_dir_name = self.temp_dir.name
        # save the source files lists
        self.license_source_files: list[str] | None = None
        if license_source_files is not None:
            self.license_source_files = [file.lower() for file in license_source_files]
        self.copyright_source_files: list[str] | None = None
        if copyright_source_files is not None:
            self.copyright_source_files = [
                file.lower() for file in copyright_source_files
            ]

    def __del__(self) -> None:
        self.temp_dir.cleanup()

    # method to get the metadata
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = []
        for package in metadata:
            # if the package has a license and a copyright
            if package.license and package.copyright:
                updated_metadata.append(package)
                continue
            # otherwise we make a shallow clone of the repository
            if not package.origin and package.name is not None:
                package.origin = package.name
            parsed_url = parse_git_url(package.origin)
            if parsed_url.valid and parsed_url.platform == "github":
                owner = parsed_url.owner
                repo = parsed_url.repo
                repository_url = parsed_url.url2https()
                if parsed_url.branch and parsed_url.path:
                    path = parsed_url.path.strip(parsed_url.branch)
                elif parsed_url.path:
                    path = parsed_url.path
                else:
                    path = ""

            else:
                updated_metadata.append(package)
                continue
            # some repositories provide more than one package, if already cloned, we skip
            clone_path = f"{self.temp_dir_name}/{owner}-{repo}"
            if not path_exists(clone_path):
                result = os.system(
                    "git clone --depth 1 {} {}".format(
                        quote(repository_url), quote(clone_path)
                    )
                )
                if result != 0:
                    raise ValueError(f"Failed to clone repository: {repository_url}")
            if not package.license:
                # get list of files at the base directory of the repository to attempt to find licenses
                # filter files to be only the ones that are in the license source files list (non case sensitive)
                if not self.license_source_files:
                    files = list_dir(clone_path)
                    if (
                        path != ""
                        and path is not None
                        and os.path.isdir(clone_path + path)
                    ):
                        for file in list_dir(clone_path + path):
                            files.append(path + "/" + file)
                else:
                    files_root = [
                        file
                        for file in list_dir(clone_path)
                        if file.lower() in self.license_source_files
                    ]
                    files_path = []
                    if (
                        path != ""
                        and path is not None
                        and os.path.isdir(clone_path + path)
                    ):
                        files_path = [
                            path + "/" + file
                            for file in list_dir(clone_path + path)
                            if file.lower() in self.license_source_files
                        ]
                    files = files_root + files_path
                licenses = []
                for file in files:
                    file_abs_path = f"{clone_path}/{file}"
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
                for root, _, all_files in walk_directory(clone_path):
                    # filter the files to be only the ones that are in the copyright source files
                    files = []
                    if not self.copyright_source_files:
                        if path == "":
                            files = all_files
                        else:
                            if path is not None and (
                                (root == clone_path) or (root == clone_path + path)
                            ):
                                files = all_files
                    else:
                        if path == "":
                            files = [
                                file
                                for file in all_files
                                if file.lower() in self.copyright_source_files
                            ]
                        else:
                            if path is not None and (
                                (root == clone_path) or (root == clone_path + path)
                            ):
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

    def cleanup_licenses(self, licenses: list[str]) -> list[str]:
        # split the licenses by 'AND'
        ret_licenses = []
        for license in licenses:
            ret_licenses.extend(license.split(" AND "))
        # remove duplicates
        ret_licenses = list(set(ret_licenses))
        # remove thoase unknown licenses
        unknown_license = "LicenseRef-scancode-unknown-license-reference"
        ret_licenses = [
            license for license in ret_licenses if license != unknown_license
        ]
        # remove generic clas
        generic_cla = "LicenseRef-scancode-generic-cla"
        ret_licenses = [license for license in ret_licenses if license != generic_cla]
        return ret_licenses
