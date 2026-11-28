# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import logging
import re
from typing import Any

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")
import warnings

# Suppress the libmagic warning from typecode
warnings.filterwarnings("ignore", category=UserWarning, module="typecode.magic2")

import scancode.api
from license_expression import AND, ExpressionError, Licensing

from dd_license_attribution.adaptors.os import (
    list_dir,
    open_file,
    path_exists,
    walk_directory,
)
from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    SourceCodeManager,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)

_licensing = Licensing()


def _collect_and_operands(node: Any) -> list[str]:
    if isinstance(node, AND):
        operands: list[str] = []
        for arg in node.args:
            operands.extend(_collect_and_operands(arg))
        return operands
    return [str(node)]


def _split_top_level_and(license_expression_str: str) -> list[str]:
    try:
        parsed = _licensing.parse(license_expression_str)
    except ExpressionError:
        return [license_expression_str]
    if parsed is None:
        return []
    return _collect_and_operands(parsed)


_GO_MAJOR_VERSION_SUFFIX_RE = re.compile(r"^v([2-9]|[1-9]\d+)$")
_GO_MOD_MODULE_RE = re.compile(
    r'^module\s+(?:"([^"]+)"|([^\s"`/]+(?:/[^\s"`/]+)*))\s*(?://.*)?$'
)


def _parse_go_mod_module(go_mod_content: str) -> str | None:
    """Return the declared module path from go.mod content, or None if absent or malformed."""
    for line in go_mod_content.splitlines():
        match = _GO_MOD_MODULE_RE.match(line.strip())
        if match:
            declared: str = match.group(1) or match.group(2)
            return declared
    return None


def _is_go_major_version_module_name(
    package_name: str | None, version_suffix: str
) -> bool:
    """Return True if package_name looks like a Go module path ending with /<version_suffix>."""
    if not package_name or not package_name.endswith(f"/{version_suffix}"):
        return False
    host = package_name.partition("/")[0]
    return "." in host and not host.startswith("@")


def _strip_missing_go_major_version_suffix(
    package_name: str | None,
    source_code_reference: SourceCodeReference,
) -> SourceCodeReference | None:
    """Strip a trailing Go v2+ semantic import version segment from local_full_path
    when package_name is a Go module path, the vN/ subdirectory does not exist in
    the cloned repo, and the parent directory's go.mod declares package_name.
    """
    root = source_code_reference.local_root_path.rstrip("/")
    full = source_code_reference.local_full_path.rstrip("/")
    if not full.startswith(root + "/"):
        return None
    rel_parts = full[len(root) + 1 :].split("/")
    version_suffix = rel_parts[-1]
    if not _GO_MAJOR_VERSION_SUFFIX_RE.match(version_suffix):
        return None
    if not _is_go_major_version_module_name(package_name, version_suffix):
        return None
    stripped_rel = "/".join(rel_parts[:-1])
    if stripped_rel:
        fallback_full_path = f"{root}/{stripped_rel}"
        if not path_exists(fallback_full_path):
            return None
    else:
        fallback_full_path = source_code_reference.local_root_path
    go_mod_path = f"{fallback_full_path.rstrip('/')}/go.mod"
    if not path_exists(go_mod_path):
        return None
    try:
        go_mod_content = open_file(go_mod_path)
    except (OSError, UnicodeError):
        return None
    if _parse_go_mod_module(go_mod_content) != package_name:
        return None
    return SourceCodeReference(
        repo_url=source_code_reference.repo_url,
        branch=source_code_reference.branch,
        local_root_path=source_code_reference.local_root_path,
        local_full_path=fallback_full_path,
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
        skipped_dependencies = 0
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
                if not package.license:
                    package.license = self._get_license(source_code_reference)
                if not package.copyright:
                    package.copyright = self._get_copyright(source_code_reference)

            # otherwise we make a shallow clone of the repository or read a cache of it
            if not package.license or not package.copyright:
                source_code_reference_or_none = self.source_code_manager.get_code(
                    package.origin, force_update=False
                )
                if not source_code_reference_or_none:
                    skipped_dependencies += 1
                    logger.warning(
                        "Skipping source scan for %s: could not resolve or clone %s",
                        package.name,
                        package.origin,
                    )
                    updated_metadata.append(package)
                    continue
                else:
                    source_code_reference = source_code_reference_or_none
                # if the repository location was obtained as a inference from the package manager it may be incorrect
                # We need to check existance of the path and skip with a warning if not found
                if source_code_reference.local_full_path:
                    full_exists = path_exists(source_code_reference.local_full_path)
                    root_exists = path_exists(source_code_reference.local_root_path)
                    if not full_exists and root_exists:
                        fallback_ref = _strip_missing_go_major_version_suffix(
                            package.name, source_code_reference
                        )
                        if fallback_ref is not None:
                            source_code_reference = fallback_ref
                            full_exists = True
                    if not full_exists or not root_exists:
                        logger.warning(
                            f"{source_code_reference.local_full_path} does not exist, skipping. "
                            f"This may be due to the package manager not providing the correct source code location on {package.local_src_path}."
                        )
                        updated_metadata.append(package)
                        continue
                if not package.license:
                    package.license = self._get_license(source_code_reference)
                if not package.copyright:
                    package.copyright = self._get_copyright(source_code_reference)
            updated_metadata.append(package)
        if skipped_dependencies > 0:
            logger.warning(
                "Enrichment skipped for %d of %d dependencies",
                skipped_dependencies,
                len(metadata),
            )
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

    def _get_license(self, source_code_reference: SourceCodeReference) -> list[str]:
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
            return self.cleanup_licenses(licenses)
        return []

    def _get_copyright(self, source_code_reference: SourceCodeReference) -> list[str]:
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
            return list(set(copyrights["holders"]))
        # If we do not find a declaration of holders, we use the authors.
        if copyrights["authors"]:
            # remove duplicates
            return list(set(copyrights["authors"]))
        # If we do not find a declaration of holders or authors, we use the copyrights disclaimers in raw.
        if copyrights["copyrights"]:
            # remove duplicates
            return list(set(copyrights["copyrights"]))
        return []

    @staticmethod
    def cleanup_licenses(licenses: list[str]) -> list[str]:
        # Split top-level 'AND' conjuncts without breaking parenthesized groups
        ret_licenses: list[str] = []
        for license_expr in licenses:
            ret_licenses.extend(_split_top_level_and(license_expr))
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
