# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from dd_license_attribution.adaptors.datetime import get_datetime_now
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.report_generator.writters.abstract_reporting_writter import (
    ReportingWritter,
)
from dd_license_attribution.report_generator.writters.metadata_combiner import (
    CombinedMetadata,
    combine_metadata,
)

_PYPI_SPEC_PATTERN = re.compile(
    r"^\s*([A-Za-z0-9][A-Za-z0-9._-]*)"
    r"(?:\[[A-Za-z0-9._,\-\s]+\])?"
    r"\s*(?:(==|!=|<=|>=|~=|<|>)\s*([^,;\s]+).*)?$"
)
_RUST_PARTIAL_VERSION_PATTERN = re.compile(
    r"^\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?((?:[-+].*)?)\s*$"
)


@dataclass
class _RootPackage:
    name: str
    version: str | None
    license: set[str]
    copyright: set[str]
    row: CombinedMetadata | None


class MarkdownReportingWritter(ReportingWritter):
    def __init__(
        self,
        document_name: str | None = None,
        ecosystem: str | None = None,
        created_at: Callable[[], datetime] = get_datetime_now,
    ) -> None:
        self.document_name = document_name
        self.ecosystem = ecosystem
        self.created_at = created_at

    def write(self, metadata: list[Metadata]) -> str:
        rows = combine_metadata(metadata)
        root_package = self._get_root_package(metadata, rows)
        dependency_rows = [
            row
            for row in rows
            if root_package.row is None or row is not root_package.row
        ]
        lines = [
            f"# License Compliance Report: {root_package.name}",
            "",
            "| Field | Value |",
            "| --- | --- |",
            f"| Package | {_markdown_code_cell(root_package.name)} |",
            f"| Version | {_markdown_cell(root_package.version)} |",
            f"| Ecosystem | {_markdown_cell(self.ecosystem or 'N/A')} |",
            f"| Date | {self.created_at().strftime('%Y-%m-%d')} |",
            f"| Dependencies | {len(dependency_rows)} |",
            f"| License | {_markdown_cell(str(sorted(root_package.license)))} |",
            f"| Copyright | {_markdown_cell(str(sorted(root_package.copyright)))} |",
            "",
            "## Third-Party Dependencies",
            "",
            "| Component | Origin | License | Copyright |",
            "| --- | --- | --- | --- |",
        ]

        for row_data in dependency_rows:
            lines.append(
                "| "
                f"{_markdown_cell(row_data.component)} | "
                f"{_markdown_cell(row_data.origin)} | "
                f"{_markdown_cell(str(sorted(row_data.license)))} | "
                f"{_markdown_cell(str(sorted(row_data.copyright)))} |"
            )

        return "\n".join(lines) + "\n"

    def _get_root_package(
        self, metadata: list[Metadata], rows: list[CombinedMetadata]
    ) -> _RootPackage:
        default_name = self.document_name
        if default_name is None and metadata and metadata[0].name:
            default_name = metadata[0].name
        if default_name is None:
            default_name = "sbom"

        package_name, package_version = _split_package_spec(
            default_name, self.ecosystem
        )
        if self.ecosystem == "rust":
            package_version = _normalize_rust_package_version(package_version)
        root_row = _find_root_row(rows, package_name, package_version, self.ecosystem)
        if (
            root_row is None
            and self.ecosystem == "rust"
            and package_version is not None
        ):
            root_row = _find_unique_root_row_by_name(rows, package_name, self.ecosystem)

        if root_row is not None:
            return _RootPackage(
                name=root_row.component or package_name,
                version=root_row.version or package_version,
                license=root_row.license,
                copyright=root_row.copyright,
                row=root_row,
            )

        return _RootPackage(
            name=package_name,
            version=package_version,
            license=set(),
            copyright=set(),
            row=None,
        )


def _markdown_cell(value: str | None) -> str:
    if value is None:
        return ""
    return value.replace("|", "\\|").replace("_", "\\_")


def _markdown_code_cell(value: str | None) -> str:
    if value is None:
        return ""
    escaped_value = value.replace("|", "\\|")
    return f"`{escaped_value}`"


def _find_root_row(
    rows: list[CombinedMetadata],
    package_name: str,
    package_version: str | None,
    ecosystem: str | None = None,
) -> CombinedMetadata | None:
    for row in rows:
        if _package_name_matches(row.component, package_name, ecosystem) and (
            package_version is None or row.version == package_version
        ):
            return row
    return None


def _find_unique_root_row_by_name(
    rows: list[CombinedMetadata],
    package_name: str,
    ecosystem: str | None = None,
) -> CombinedMetadata | None:
    matching_rows = [
        row
        for row in rows
        if _package_name_matches(row.component, package_name, ecosystem)
    ]
    if len(matching_rows) == 1:
        return matching_rows[0]
    return None


def _package_name_matches(
    row_component: str | None, package_name: str, ecosystem: str | None
) -> bool:
    if row_component is None:
        return False
    if ecosystem == "pypi":
        return _normalize_pypi_name(row_component) == _normalize_pypi_name(package_name)
    return row_component == package_name


def _split_package_spec(
    value: str, ecosystem: str | None = None
) -> tuple[str, str | None]:
    if value.startswith("git@") or "://" in value:
        return value, None

    if ecosystem == "pypi":
        pypi_package_spec = _split_pypi_package_spec(value)
        if pypi_package_spec is not None:
            return pypi_package_spec

    if value.startswith("@"):
        version_separator = value.rfind("@", 1)
    else:
        version_separator = value.rfind("@")

    if version_separator <= 0:
        return value, None

    name = value[:version_separator]
    version = value[version_separator + 1 :]
    if not name or not version:
        return value, None
    return name, version


def _normalize_rust_package_version(package_version: str | None) -> str | None:
    if package_version is None:
        return None

    match = _RUST_PARTIAL_VERSION_PATTERN.match(package_version)
    if match is None:
        return package_version

    major, minor, patch, suffix = match.groups()
    return f"{major}.{minor or '0'}.{patch or '0'}{suffix}"


def _split_pypi_package_spec(value: str) -> tuple[str, str | None] | None:
    match = _PYPI_SPEC_PATTERN.match(value)
    if match is None:
        return None

    name = match.group(1)
    operator = match.group(2)
    version = match.group(3)
    if operator == "==" and version:
        return name, version
    return name, None


def _normalize_pypi_name(value: str) -> str:
    return re.sub(r"[-_.]+", "-", value).lower()
