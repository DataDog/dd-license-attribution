# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import json
import logging
from datetime import datetime
from importlib.metadata import PackageNotFoundError
from unittest.mock import patch

import pytest
import pytz

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.report_generator.writters.spdx_reporting_writter import (
    SPDXReportingWritter,
)


def test_spdx_reporting_writter_writes_spdx_2_3_json() -> None:
    metadata = [
        Metadata(
            name="root-project",
            version="1.0.0",
            origin="https://github.com/example/root-project",
            local_src_path=None,
            license=["MIT"],
            copyright=["Copyright root"],
        ),
        Metadata(
            name="dependency",
            version="2.0.0",
            origin="https://github.com/example/dependency",
            local_src_path=None,
            license=["Apache-2.0"],
            copyright=["Copyright dependency"],
        ),
    ]

    spdx_report_writter = SPDXReportingWritter(
        document_namespace="https://datadoghq.com/spdx/root-project-fixed",
        created_at=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=pytz.UTC),
        tool_version="0.5.0",
    )
    spdx_json = spdx_report_writter.write(metadata)

    parsed = json.loads(spdx_json)
    assert parsed["spdxVersion"] == "SPDX-2.3"
    assert parsed["dataLicense"] == "CC0-1.0"
    assert parsed["SPDXID"] == "SPDXRef-DOCUMENT"
    assert parsed["name"] == "root-project"
    assert (
        parsed["documentNamespace"] == "https://datadoghq.com/spdx/root-project-fixed"
    )
    assert parsed["creationInfo"] == {
        "created": "2026-01-02T03:04:05Z",
        "creators": ["Tool: dd-license-attribution-0.5.0"],
    }
    assert parsed["packages"] == [
        {
            "SPDXID": "SPDXRef-Package-dependency-1",
            "copyrightText": "Copyright dependency",
            "downloadLocation": "https://github.com/example/dependency",
            "filesAnalyzed": False,
            "licenseConcluded": "Apache-2.0",
            "licenseDeclared": "NOASSERTION",
            "name": "dependency",
            "versionInfo": "2.0.0",
        },
        {
            "SPDXID": "SPDXRef-Package-root-project-2",
            "copyrightText": "Copyright root",
            "downloadLocation": "https://github.com/example/root-project",
            "filesAnalyzed": False,
            "licenseConcluded": "MIT",
            "licenseDeclared": "NOASSERTION",
            "name": "root-project",
            "versionInfo": "1.0.0",
        },
    ]
    assert parsed["relationships"] == [
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package-dependency-1",
        },
        {
            "spdxElementId": "SPDXRef-DOCUMENT",
            "relationshipType": "DESCRIBES",
            "relatedSpdxElement": "SPDXRef-Package-root-project-2",
        },
    ]


def test_spdx_reporting_writter_combines_and_sorts_metadata() -> None:
    metadata = [
        Metadata(
            name="z-package",
            version="1.0.0",
            origin="https://github.com/example/z-package",
            local_src_path=None,
            license=["MIT"],
            copyright=["Copyright z"],
        ),
        Metadata(
            name="a-package",
            version=None,
            origin="https://github.com/example/a-package",
            local_src_path=None,
            license=["MIT", "Apache-2.0"],
            copyright=["Copyright a", "Copyright b"],
        ),
        Metadata(
            name="a-package",
            version="2.0.0",
            origin="https://github.com/example/a-package",
            local_src_path=None,
            license=["BSD-3-Clause"],
            copyright=["Copyright c"],
        ),
    ]

    spdx_report_writter = SPDXReportingWritter(
        document_namespace="https://datadoghq.com/spdx/fixed",
        created_at=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=pytz.UTC),
        tool_version="0.5.0",
    )
    spdx_json = spdx_report_writter.write(metadata)

    parsed = json.loads(spdx_json)
    packages = parsed["packages"]
    assert [package["name"] for package in packages] == ["a-package", "z-package"]
    assert packages[0]["SPDXID"] == "SPDXRef-Package-a-package-1"
    assert packages[0]["versionInfo"] == "2.0.0"
    assert packages[0]["licenseConcluded"] == ("Apache-2.0 AND BSD-3-Clause AND MIT")
    assert packages[0]["copyrightText"] == ("Copyright a\nCopyright b\nCopyright c")


def test_spdx_reporting_writter_outputs_stable_json() -> None:
    metadata = [
        Metadata(
            name="stable-package",
            version=None,
            origin=None,
            local_src_path=None,
            license=[],
            copyright=[],
        ),
    ]

    spdx_report_writter = SPDXReportingWritter(
        document_namespace="https://datadoghq.com/spdx/stable",
        created_at=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=pytz.UTC),
        tool_version="0.5.0",
    )

    first_json = spdx_report_writter.write(metadata)
    second_json = spdx_report_writter.write(metadata)

    assert first_json == second_json
    parsed = json.loads(first_json)
    assert parsed["packages"][0]["downloadLocation"] == "NOASSERTION"
    assert parsed["packages"][0]["licenseConcluded"] == "NOASSERTION"
    assert parsed["packages"][0]["licenseDeclared"] == "NOASSERTION"
    assert parsed["packages"][0]["copyrightText"] == "NOASSERTION"


def test_spdx_reporting_writter_generates_default_namespace_and_name() -> None:
    spdx_report_writter = SPDXReportingWritter(
        created_at=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=pytz.UTC),
        namespace_id_factory=lambda: "fixed-id",
    )

    spdx_json = spdx_report_writter.write([])

    parsed = json.loads(spdx_json)
    assert parsed["name"] == "sbom"
    assert parsed["documentNamespace"] == "https://datadoghq.com/spdx/sbom-fixed-id"
    assert parsed.get("packages", []) == []
    assert parsed.get("relationships", []) == []
    assert parsed["creationInfo"]["creators"][0].startswith(
        "Tool: dd-license-attribution-"
    )


def test_spdx_reporting_writter_sanitizes_ids_and_falls_back_for_bad_license(
    caplog: pytest.LogCaptureFixture,
) -> None:
    metadata = [
        Metadata(
            name=None,
            version=None,
            origin=None,
            local_src_path=None,
            license=["MIT AND"],
            copyright=[],
        ),
    ]

    spdx_report_writter = SPDXReportingWritter(
        document_name="!!!",
        created_at=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=pytz.UTC),
        namespace_id_factory=lambda: "fixed-id",
        tool_version="0.5.0",
    )
    with caplog.at_level(logging.WARNING, logger="dd_license_attribution"):
        spdx_json = spdx_report_writter.write(metadata)

    parsed = json.loads(spdx_json)
    assert parsed["name"] == "!!!"
    assert parsed["documentNamespace"] == "https://datadoghq.com/spdx/package-fixed-id"
    assert parsed["packages"][0]["SPDXID"] == "SPDXRef-Package-package-1"
    assert parsed["packages"][0]["name"] == "NOASSERTION"
    assert parsed["packages"][0]["licenseConcluded"] == "NOASSERTION"
    assert "Unable to parse license expression MIT AND" in caplog.text


def test_spdx_reporting_writter_uses_unknown_when_package_version_is_missing() -> None:
    with patch(
        "dd_license_attribution.report_generator.writters.spdx_reporting_writter.version"
    ) as mock_version:
        mock_version.side_effect = PackageNotFoundError

        spdx_report_writter = SPDXReportingWritter(
            document_namespace="https://datadoghq.com/spdx/fixed",
            created_at=lambda: datetime(2026, 1, 2, 3, 4, 5, tzinfo=pytz.UTC),
        )

    assert spdx_report_writter.tool_version == "unknown"
    mock_version.assert_called_once_with("datadog-license-attribution")
