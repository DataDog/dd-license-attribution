from dataclasses import dataclass
import tempfile
import os
from shlex import quote
import scancode


from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.purl_parser import PurlParser
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


def list_dir(dest_path):
    return os.listdir(dest_path)


def walk_directory(dest_path):
    return os.walk(dest_path)


class ScanCodeToolkitMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(self) -> None:
        self.purl_parser = PurlParser()
        # create a temporary directory for github shallow clones
        self.temp_dir = tempfile.TemporaryDirectory()
        # in the temporary directory make a shallow clone of the repository
        self.temp_dir_name = self.temp_dir.name

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
            owner, repo = self.purl_parser.get_github_owner_and_repo(package.origin)
            # if not github repository available, we skip for now
            if owner is None or repo is None:
                updated_metadata.append(package)
                continue
            # make the shallow clone in a temporary directory
            repository_url = f"https://github.com/{owner}/{repo}"
            # some repositories provide more than one package, if already cloned, we skip
            if not os.path.exists(f"{self.temp_dir_name}/{owner}-{repo}"):
                dest_path = f"{self.temp_dir_name}/{owner}-{repo}"
                result = os.system(
                    "git clone --depth 1 {} {}".format(
                        quote(repository_url), quote(dest_path)
                    )
                )
                if result != 0:
                    raise ValueError(f"Failed to clone repository: {repository_url}")
            if not package.license:
                # get list of files at the base directory of the repository to attempt to find licenses
                files = list_dir(dest_path)
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
                    clean_licenses = self.cleanup_licenses(licenses)
                    package.license = ", ".join(clean_licenses)
            # copyright
            if not package.copyright:
                copyrights = {
                    "holders": [],
                    "authors": [],
                    "copyrights": [],
                }
                # get list of all files to attempt to find copyright information
                for root, _, files in walk_directory(dest_path):
                    for file in files:
                        file_abs_path = f"{root}/{file}"
                        copyright = scancode.api.get_copyrights(file_abs_path)
                        if copyright["holders"]:
                            [
                                copyrights["holders"].append(c["holder"])
                                for c in copyright["holders"]
                            ]
                        elif copyright["authors"]:
                            [
                                copyrights["authors"].append(c["author"])
                                for c in copyright["authors"]
                            ]
                        elif copyright["copyrights"]:
                            # map all copyrights field to a list
                            [
                                copyrights["copyrights"].append(c["copyright"])
                                for c in copyright["copyrights"]
                            ]
                # If we find a declaration of copyright holders, we use that.
                if copyrights["holders"]:
                    # remove duplicates
                    copyrights = list(set(copyrights["holders"]))
                # If we do not find a declaration of holders, we use the authors.
                elif copyrights["authors"]:
                    # remove duplicates
                    copyrights = list(set(copyrights["authors"]))
                # If we do not find a declaration of holders or authors, we use the copyrights disclaimers in raw.
                elif copyrights["copyrights"]:
                    # remove duplicates
                    copyrights = list(set(copyrights["copyrights"]))
                package.copyright = ", ".join(copyrights)
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
