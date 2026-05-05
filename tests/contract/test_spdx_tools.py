# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import io
import json
from datetime import datetime

import pytz
from license_expression import get_spdx_licensing
from spdx_tools.spdx.model.actor import Actor, ActorType
from spdx_tools.spdx.model.document import CreationInfo, Document
from spdx_tools.spdx.model.package import Package
from spdx_tools.spdx.model.relationship import Relationship, RelationshipType
from spdx_tools.spdx.model.spdx_no_assertion import SpdxNoAssertion
from spdx_tools.spdx.writer.json.json_writer import write_document_to_stream


def test_spdx_tools_builds_document_package_and_serializes_json() -> None:
    creation_info = CreationInfo(
        spdx_version="SPDX-2.3",
        spdx_id="SPDXRef-DOCUMENT",
        name="contract",
        document_namespace="https://datadoghq.com/spdx/contract",
        creators=[Actor(ActorType.TOOL, "dd-license-attribution-0.5.0")],
        created=datetime(2026, 1, 2, 3, 4, 5, tzinfo=pytz.UTC),
    )
    package = Package(
        spdx_id="SPDXRef-Package-contract",
        name="contract-package",
        download_location="https://github.com/example/contract-package",
        version="1.0.0",
        files_analyzed=False,
        license_concluded=get_spdx_licensing().parse("MIT", validate=True),
        license_declared=SpdxNoAssertion(),
        copyright_text="Copyright contract",
    )
    document = Document(
        creation_info=creation_info,
        packages=[package],
        relationships=[
            Relationship(
                "SPDXRef-DOCUMENT",
                RelationshipType.DESCRIBES,
                "SPDXRef-Package-contract",
            )
        ],
    )

    stream = io.StringIO()
    write_document_to_stream(document, stream, validate=False)

    parsed = json.loads(stream.getvalue())
    assert parsed["spdxVersion"] == "SPDX-2.3"
    assert parsed["creationInfo"]["creators"] == ["Tool: dd-license-attribution-0.5.0"]
    assert parsed["packages"][0]["SPDXID"] == "SPDXRef-Package-contract"
    assert parsed["packages"][0]["licenseConcluded"] == "MIT"
    assert parsed["relationships"][0]["relationshipType"] == "DESCRIBES"
