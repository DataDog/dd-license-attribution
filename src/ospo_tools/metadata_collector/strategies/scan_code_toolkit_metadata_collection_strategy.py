from dataclasses import dataclass
import tempfile
import os
from shlex import quote
from typing import Iterator
import scancode.api


from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.purl_parser import PurlParser
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


def list_dir(dest_path: str) -> list[str]:
    return os.listdir(dest_path)


def walk_directory(dest_path: str) -> Iterator[tuple[str, list[str], list[str]]]:
    return os.walk(dest_path)


class ScanCodeToolkitMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(
        self,
        license_source_files: list[str] | None = None,
        copyright_source_files: list[str] | None = None,
    ) -> None:
        self.purl_parser = PurlParser()
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
            owner, repo = self.purl_parser.get_github_owner_and_repo(package.origin)
            # if not github repository available, we skip for now
            if owner is None or repo is None:
                updated_metadata.append(package)
                continue
            # make the shallow clone in a temporary directory
            repository_url = f"https://github.com/{owner}/{repo}"
            # some repositories provide more than one package, if already cloned, we skip
            dest_path = f"{self.temp_dir_name}/{owner}-{repo}"
            if not os.path.exists(dest_path):
                result = os.system(
                    "git clone --depth 1 {} {}".format(
                        quote(repository_url), quote(dest_path)
                    )
                )
                if result != 0:
                    raise ValueError(f"Failed to clone repository: {repository_url}")
            if not package.license:
                # get list of files at the base directory of the repository to attempt to find licenses
                # filter files to be only the ones that are in the license source files list (non case sensitive)
                if not self.license_source_files:
                    files = list_dir(dest_path)
                else:
                    files = [
                        file
                        for file in list_dir(dest_path)
                        if file.lower() in self.license_source_files
                    ]
                licenses = []
                for file in files:
                    file_abs_path = f"{dest_path}/{file}"
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
                for root, _, all_files in walk_directory(dest_path):
                    # filter the files to be only the ones that are in the copyright source files
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
