# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

from abc import ABC, abstractmethod

from dd_license_attribution.metadata_collector.strategies.override_strategy import (  # noqa: E501
    OverrideRule,
)


class OverridesWritter(ABC):
    @abstractmethod
    def write(self, override_rules: list[OverrideRule]) -> str:
        raise NotImplementedError
