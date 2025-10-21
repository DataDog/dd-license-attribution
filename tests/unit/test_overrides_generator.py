# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import pytest_mock

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.override_strategy import (
    OverrideRule,
    OverrideTargetField,
    OverrideType,
)
from dd_license_attribution.overrides_generator.overrides_generator import (
    OverridesGenerator,
)
from dd_license_attribution.overrides_generator.writters.abstract_overrides_writter import (  # noqa: E501
    OverridesWritter,
)


def test_overrides_generator_saves_writer_and_calls_it_when_rules_are_passed(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that OverridesGenerator delegates to the writer."""
    overrides_writer_mock = mocker.Mock(spec_set=OverridesWritter)
    override_rules = [
        OverrideRule(
            override_type=OverrideType.REPLACE,
            target={
                OverrideTargetField.COMPONENT: "test-component",
                OverrideTargetField.ORIGIN: "test-origin",
            },
            replacement=Metadata(
                name="test-component",
                version="1.0.0",
                origin="test-origin",
                local_src_path=None,
                license=["MIT"],
                copyright=["Test Author"],
            ),
        )
    ]

    overrides_generator = OverridesGenerator(overrides_writer_mock)
    overrides_generator.generate_overrides(override_rules)

    overrides_writer_mock.write.assert_called_once_with(override_rules)
