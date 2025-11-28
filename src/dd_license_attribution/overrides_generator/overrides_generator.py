# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

from dd_license_attribution.metadata_collector.strategies.override_strategy import (  # noqa: E501
    OverrideRule,
)
from dd_license_attribution.overrides_generator.writers.abstract_overrides_writer import (  # noqa: E501
    OverridesWriter,
)


class OverridesGenerator:
    """
    Generator for override files that delegates to a writer implementation.
    """

    def __init__(self, overrides_writer: OverridesWriter):
        self.overrides_writer = overrides_writer

    def generate_overrides(self, override_rules: list[OverrideRule]) -> str:
        return self.overrides_writer.write(override_rules)
