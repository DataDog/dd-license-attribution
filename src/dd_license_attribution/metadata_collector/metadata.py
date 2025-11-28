# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from dataclasses import dataclass


# Keeping this class short initially, we should eventually getting it closer
# to the CycloneDX/SPDX standard as we grow the project.
@dataclass
class Metadata:
    """Metadata class to store metadata of a package."""

    name: str | None  # AKA component
    version: str | None  # package version or commit hash
    origin: str | None  # package manager purl or repository url
    local_src_path: str | None  # local path to the source code
    license: list[str]  # SPDX format license
    copyright: list[str]  # Copyright owners
