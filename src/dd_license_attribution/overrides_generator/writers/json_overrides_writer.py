# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import io
import json

from dd_license_attribution.metadata_collector.strategies.override_strategy import (  # noqa: E501
    OverrideRule,
)
from dd_license_attribution.overrides_generator.writers.abstract_overrides_writer import (  # noqa: E501
    OverridesWriter,
)


class JSONOverridesWriter(OverridesWriter):
    """
    Writes override rules to JSON format in the format expected by
    the dd-license-attribution tool.
    """

    def write(self, override_rules: list[OverrideRule]) -> str:
        # Convert OverrideRule objects to dictionaries for JSON output

        output = io.StringIO()
        json_rules = [
            {
                "override_type": rule.override_type.value,
                "target": {field.value: value for field, value in rule.target.items()},
                "replacement": (
                    {
                        "name": rule.replacement.name,
                        "origin": rule.replacement.origin,
                        "license": rule.replacement.license,
                        "copyright": rule.replacement.copyright,
                    }
                    if rule.replacement is not None
                    else None
                ),
            }
            for rule in override_rules
        ]

        json.dump(json_rules, output, indent=2)
        json_string = output.getvalue()
        output.close()

        return json_string
