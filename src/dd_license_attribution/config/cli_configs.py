# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from dataclasses import dataclass


@dataclass
class Config:
    preset_license_file_locations: list[str]
    preset_copyright_file_locations: list[str]
    preset_cautionary_licenses: list[str]


default_config = Config(
    preset_license_file_locations=[
        "LICENSE",
        "LICENSE.code",
        "LICENSE.txt",
        "LICENSE.md",
        "COPYING",
        "LICENCE",  # I know it is misspelled, but it is common in the wild
        "LICENCE.md",  # I know it is misspelled, but it is common in the wild
        "license/LICENSE.txt",
    ],
    preset_copyright_file_locations=[
        "NOTICE",
        "NOTICE.md",
        "NOTICE.txt",
        "AUTHORS",
        "AUTHORS.md",
        "AUTHORS.txt",
        "CONTRIBUTORS",
        "CONTRIBUTORS.md",
        "CONTRIBUTORS.txt",
        # Some licenses include the copyright in their license file
        "LICENSE",
        "LICENSE.code",
        "LICENSE.txt",
        "LICENSE.md",
        "COPYING",
        "LICENCE",  # I know it is misspelled, but it is common in the wild
        "LICENCE.md",  # I know it is misspelled, but it is common in the wild
        "license/LICENSE.txt",
    ],
    preset_cautionary_licenses=[
        "GPL",
        "EUPL",
        "AGPL",
    ],
)
