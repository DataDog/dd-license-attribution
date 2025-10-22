# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import json

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.override_strategy import (
    OverrideRule,
    OverrideTargetField,
    OverrideType,
)
from dd_license_attribution.overrides_generator.writers.json_overrides_writer import (  # noqa: E501
    JSONOverridesWriter,
)


def test_json_overrides_writer_writes_replace_rule_to_file() -> None:
    """Test writing a REPLACE override rule returns JSON string."""
    override_rules = [
        OverrideRule(
            override_type=OverrideType.REPLACE,
            target={
                OverrideTargetField.COMPONENT: "test-component",
                OverrideTargetField.ORIGIN: "https://github.com/test/repo",
            },
            replacement=Metadata(
                name="test-component",
                version="1.0.0",
                origin="https://github.com/test/repo",
                local_src_path="/path/to/src",
                license=["MIT"],
                copyright=["Test Author"],
            ),
        )
    ]

    json_writer = JSONOverridesWriter()
    result = json_writer.write(override_rules)

    assert isinstance(result, str)
    json_content = json.loads(result)

    assert len(json_content) == 1
    assert json_content[0]["override_type"] == "replace"
    assert json_content[0]["target"]["component"] == "test-component"
    assert json_content[0]["target"]["origin"] == "https://github.com/test/repo"
    assert json_content[0]["replacement"]["name"] == "test-component"
    assert json_content[0]["replacement"]["origin"] == "https://github.com/test/repo"
    assert json_content[0]["replacement"]["license"] == ["MIT"]
    assert json_content[0]["replacement"]["copyright"] == ["Test Author"]
    # Verify internal fields are not included
    assert "version" not in json_content[0]["replacement"]
    assert "local_src_path" not in json_content[0]["replacement"]


def test_json_overrides_writer_writes_multiple_rules() -> None:
    """Test writing multiple override rules returns JSON string."""
    override_rules = [
        OverrideRule(
            override_type=OverrideType.REPLACE,
            target={
                OverrideTargetField.COMPONENT: "component-1",
                OverrideTargetField.ORIGIN: "origin-1",
            },
            replacement=Metadata(
                name="component-1",
                version=None,
                origin="origin-1",
                local_src_path=None,
                license=["MIT"],
                copyright=["Author 1"],
            ),
        ),
        OverrideRule(
            override_type=OverrideType.REPLACE,
            target={
                OverrideTargetField.COMPONENT: "component-2",
                OverrideTargetField.ORIGIN: "origin-2",
            },
            replacement=Metadata(
                name="component-2",
                version=None,
                origin="origin-2",
                local_src_path=None,
                license=["Apache-2.0"],
                copyright=["Author 2", "Co-Author 2"],
            ),
        ),
    ]

    json_writer = JSONOverridesWriter()
    result = json_writer.write(override_rules)

    assert isinstance(result, str)
    json_content = json.loads(result)

    assert len(json_content) == 2
    assert json_content[0]["target"]["component"] == "component-1"
    assert json_content[0]["replacement"]["license"] == ["MIT"]
    assert json_content[1]["target"]["component"] == "component-2"
    assert json_content[1]["replacement"]["copyright"] == [
        "Author 2",
        "Co-Author 2",
    ]


def test_json_overrides_writer_writes_remove_rule_with_no_replacement() -> None:
    """Test writing a REMOVE override rule returns JSON string."""
    override_rules = [
        OverrideRule(
            override_type=OverrideType.REMOVE,
            target={OverrideTargetField.ORIGIN: ("https://github.com/test/remove")},
            replacement=None,
        )
    ]

    json_writer = JSONOverridesWriter()
    result = json_writer.write(override_rules)

    assert isinstance(result, str)
    json_content = json.loads(result)

    assert len(json_content) == 1
    assert json_content[0]["override_type"] == "remove"
    assert json_content[0]["target"]["origin"] == "https://github.com/test/remove"
    assert json_content[0]["replacement"] is None


def test_json_overrides_writer_writes_add_rule() -> None:
    """Test writing an ADD override rule returns JSON string."""
    override_rules = [
        OverrideRule(
            override_type=OverrideType.ADD,
            target={OverrideTargetField.COMPONENT: "new-component"},
            replacement=Metadata(
                name="new-component",
                version=None,
                origin="https://github.com/new/component",  # noqa: E501
                local_src_path=None,
                license=["BSD-3-Clause"],
                copyright=["New Author"],
            ),
        )
    ]

    json_writer = JSONOverridesWriter()
    result = json_writer.write(override_rules)

    assert isinstance(result, str)
    json_content = json.loads(result)

    assert len(json_content) == 1
    assert json_content[0]["override_type"] == "add"
    assert json_content[0]["target"]["component"] == "new-component"
    assert json_content[0]["replacement"]["name"] == "new-component"
    assert json_content[0]["replacement"]["license"] == ["BSD-3-Clause"]
