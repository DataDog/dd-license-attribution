# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import json

from dd_license_attribution.metadata_collector.strategies.override_strategy import (  # noqa: E501
    OverrideRule,
)
from dd_license_attribution.overrides_generator.writters.abstract_overrides_writter import (  # noqa: E501
    OverridesWritter,
)


class JSONOverridesWritter(OverridesWritter):
    """
    Writes override rules to a JSON file in the format expected by
    the dd-license-attribution tool.
    """

    def __init__(self, output_file: str):
        self.output_file = output_file

    def write(self, override_rules: list[OverrideRule]) -> str:
        # Convert OverrideRule objects to dictionaries for JSON output
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

        with open(self.output_file, "w", encoding="utf-8") as f:
            json.dump(json_rules, f, indent=2)

        return self.output_file
