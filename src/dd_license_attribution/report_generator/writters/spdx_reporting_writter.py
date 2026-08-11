# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import io
import logging
import re
from collections.abc import Callable
from datetime import datetime
from importlib.metadata import PackageNotFoundError, version
from typing import Any

from license_expression import ExpressionError, get_spdx_licensing
from spdx_tools.spdx.model.actor import Actor, ActorType
from spdx_tools.spdx.model.document import CreationInfo, Document
from spdx_tools.spdx.model.package import Package
from spdx_tools.spdx.model.relationship import Relationship, RelationshipType
from spdx_tools.spdx.model.spdx_no_assertion import SpdxNoAssertion
from spdx_tools.spdx.writer.json.json_writer import write_document_to_stream

from dd_license_attribution.adaptors.datetime import get_datetime_now
from dd_license_attribution.adaptors.uuid import get_uuid4
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.report_generator.writters.abstract_reporting_writter import (
    ReportingWritter,
)
from dd_license_attribution.report_generator.writters.metadata_combiner import (
    CombinedMetadata,
    combine_metadata,
)

logger = logging.getLogger("dd_license_attribution")
_spdx_licensing = get_spdx_licensing()


class SPDXReportingWritter(ReportingWritter):
    def __init__(
        self,
        document_name: str | None = None,
        document_namespace: str | None = None,
        created_at: Callable[[], datetime] = get_datetime_now,
        namespace_id_factory: Callable[[], str] = get_uuid4,
        tool_version: str | None = None,
    ) -> None:
        self.document_name = document_name
        self.document_namespace = document_namespace
        self.created_at = created_at
        self.namespace_id_factory = namespace_id_factory
        self.tool_version = tool_version or _get_tool_version()

    def write(self, metadata: list[Metadata]) -> str:
        document_name = self._get_document_name(metadata)
        package_rows = combine_metadata(metadata)
        packages = self._build_packages(package_rows)
        relationships = [
            Relationship(
                "SPDXRef-DOCUMENT",
                RelationshipType.DESCRIBES,
                package.spdx_id,
            )
            for package in packages
        ]
        creation_info = CreationInfo(
            spdx_version="SPDX-2.3",
            spdx_id="SPDXRef-DOCUMENT",
            name=document_name,
            document_namespace=self._get_document_namespace(document_name),
            creators=[
                Actor(
                    ActorType.TOOL,
                    f"dd-license-attribution-{self.tool_version}",
                )
            ],
            created=self.created_at(),
        )
        document = Document(
            creation_info=creation_info,
            packages=packages,
            relationships=relationships,
        )

        output = io.StringIO()
        write_document_to_stream(document, output, validate=False)
        spdx_json = output.getvalue()
        output.close()
        return spdx_json

    def _get_document_name(self, metadata: list[Metadata]) -> str:
        if self.document_name is not None:
            return self.document_name
        if metadata and metadata[0].name:
            return metadata[0].name
        return "sbom"

    def _get_document_namespace(self, document_name: str) -> str:
        if self.document_namespace is not None:
            return self.document_namespace
        return (
            "https://datadoghq.com/spdx/"
            f"{_sanitize_spdx_id_fragment(document_name)}-{self.namespace_id_factory()}"
        )

    def _build_packages(self, package_rows: list[CombinedMetadata]) -> list[Package]:
        packages = []
        for index, row_data in enumerate(package_rows, start=1):
            package_kwargs: dict[str, Any] = {
                "spdx_id": (
                    "SPDXRef-Package-"
                    f"{_sanitize_spdx_id_fragment(row_data.component)}-{index}"
                ),
                "name": row_data.component or "NOASSERTION",
                "download_location": row_data.origin or SpdxNoAssertion(),
                "files_analyzed": False,
                "license_concluded": _license_expression(row_data.license),
                "license_declared": SpdxNoAssertion(),
                "copyright_text": _copyright_text(row_data.copyright),
            }
            if row_data.version is not None:
                package_kwargs["version"] = row_data.version
            packages.append(Package(**package_kwargs))
        return packages


def _get_tool_version() -> str:
    try:
        return version("datadog-license-attribution")
    except PackageNotFoundError:
        return "unknown"


def _sanitize_spdx_id_fragment(value: str | None) -> str:
    if not value:
        return "package"
    sanitized = re.sub(r"[^A-Za-z0-9.-]+", "-", value).strip(".-")
    if not sanitized:
        return "package"
    return sanitized


def _license_expression(licenses: set[str]) -> Any:
    if not licenses:
        return SpdxNoAssertion()

    expression = " AND ".join(sorted(licenses))
    try:
        return _spdx_licensing.parse(expression, validate=False)
    except ExpressionError:
        logger.warning(
            "Unable to parse license expression %s for SPDX output; using NOASSERTION.",
            expression,
        )
        return SpdxNoAssertion()


def _copyright_text(copyrights: set[str]) -> str | SpdxNoAssertion:
    if not copyrights:
        return SpdxNoAssertion()
    return "\n".join(sorted(copyrights))
