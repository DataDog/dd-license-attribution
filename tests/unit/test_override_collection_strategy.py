# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.override_strategy import (
    OverrideCollectionStrategy,
    OverrideRule,
    OverrideTargetField,
    OverrideType,
)


def test_override_collection_strategy_json_to_rules() -> None:
    # Test input JSON
    test_json = """[
        {
            "override_type": "add",
            "target": {"origin": "example.com", "component": "test-component"},
            "replacement": {
                "name": "test-replacement",
                "origin": "test-replacement.com",
                "version": "1.0.0",
                "license": ["MIT"],
                "copyright": ["copyright holder"]
            }
        },
        {
            "override_type": "remove",
            "target": {"origin": "test-remove.com"}
        },
        {
            "override_type": "replace",
            "target": {"origin": "test-replace.com"},
            "replacement": {
                "name": "test-replace",
                "origin": "test-replace.com",
                "version": "2.0.0"
            }
        }
    ]"""
    json_obj = json.loads(test_json)

    # Expected output
    expected_rules = [
        OverrideRule(
            override_type=OverrideType.ADD,
            target={
                OverrideTargetField.ORIGIN: "example.com",
                OverrideTargetField.COMPONENT: "test-component",
            },
            replacement=Metadata(
                name="test-replacement",
                origin="test-replacement.com",
                version="1.0.0",
                license=["MIT"],
                copyright=["copyright holder"],
                local_src_path=None,
            ),
        ),
        OverrideRule(
            override_type=OverrideType.REMOVE,
            target={OverrideTargetField.ORIGIN: "test-remove.com"},
            replacement=None,
        ),
        OverrideRule(
            override_type=OverrideType.REPLACE,
            target={OverrideTargetField.ORIGIN: "test-replace.com"},
            replacement=Metadata(
                name="test-replace",
                origin="test-replace.com",
                version="2.0.0",
                license=[],
                copyright=[],
                local_src_path=None,
            ),
        ),
    ]

    # Convert JSON to rules
    rules = OverrideCollectionStrategy.json_to_override_rules(json_obj)

    # Assert the conversion
    assert rules == expected_rules


def test_override_collection_strategy_adds_on_target_match() -> None:
    rules = [
        OverrideRule(
            override_type=OverrideType.ADD,
            target={
                OverrideTargetField.ORIGIN: "example.com",
            },
            replacement=Metadata(
                name="test-addition",
                origin="test-addition.com",
                version="1.0.0",
                license=["MIT"],
                copyright=["copyright holder"],
                local_src_path=None,
            ),
        )
    ]

    strategy = OverrideCollectionStrategy(rules)

    metadata = [
        Metadata(
            name="test-package",
            origin="example.com",
            version="1.0.0",
            local_src_path="/path/to/package",
            license=["MIT"],
            copyright=["copyright holder"],
        )
    ]
    updated_metadata = strategy.augment_metadata(metadata)
    assert len(updated_metadata) == 2
    assert updated_metadata[1].name == "test-addition"
    assert updated_metadata[1].origin == "test-addition.com"
    assert updated_metadata[1].version == "1.0.0"
    assert updated_metadata[1].license == ["MIT"]
    assert updated_metadata[1].copyright == ["copyright holder"]
    assert updated_metadata[1].local_src_path is None
    assert updated_metadata[0] == metadata[0]
    assert len(strategy.unused_targets()) == 0


def test_override_collection_strategy_replaces_on_target_match() -> None:
    expected_replacement = Metadata(
        name="test-replace",
        origin="test-replace.com",
        version="1.0.0",
        license=["MIT"],
        copyright=["copyright holder"],
        local_src_path=None,
    )
    rules = [
        OverrideRule(
            override_type=OverrideType.REPLACE,
            target={
                OverrideTargetField.ORIGIN: "test-replace.com",
            },
            replacement=expected_replacement,
        )
    ]
    strategy = OverrideCollectionStrategy(rules)

    metadata = [
        Metadata(
            name="test-package",
            origin="test-replace.com",
            version="1.0.0",
            local_src_path="/path/to/package",
            license=["MIT"],
            copyright=["copyright holder"],
        )
    ]
    updated_metadata = strategy.augment_metadata(metadata)
    assert updated_metadata == [expected_replacement]
    assert len(strategy.unused_targets()) == 0


def test_override_collection_strategy_removes_on_target_match() -> None:
    rules = [
        OverrideRule(
            override_type=OverrideType.REMOVE,
            target={
                OverrideTargetField.ORIGIN: "example.com",
            },
            replacement=None,
        )
    ]
    strategy = OverrideCollectionStrategy(rules)

    metadata = [
        Metadata(
            name="test-package",
            origin="example.com",
            version="1.0.0",
            local_src_path="/path/to/package",
            license=["MIT"],
            copyright=["copyright holder"],
        )
    ]
    updated_metadata = strategy.augment_metadata(metadata)
    assert len(updated_metadata) == 0
    assert len(strategy.unused_targets()) == 0


def test_override_collection_strategy_does_not_target_match_notifies_failure() -> None:
    rules = [
        OverrideRule(
            override_type=OverrideType.REMOVE,
            target={
                OverrideTargetField.ORIGIN: "example.com",
            },
            replacement=None,
        )
    ]
    strategy = OverrideCollectionStrategy(rules)

    metadata = [
        Metadata(
            name="test-package",
            origin="not-example.com",
            version="1.0.0",
            local_src_path="/path/to/package",
            license=["MIT"],
            copyright=["copyright holder"],
        )
    ]
    updated_metadata = strategy.augment_metadata(metadata)
    assert updated_metadata == metadata
    assert len(strategy.unused_targets()) == 1
    assert strategy.unused_targets()[0] == rules[0].target
