# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

from dataclasses import dataclass


@dataclass
class StringFormattingConfig:
    preset_company_suffixes: list[str]


default_config = StringFormattingConfig(
    preset_company_suffixes=["inc", "inc.", "llc", "llc."]
)
