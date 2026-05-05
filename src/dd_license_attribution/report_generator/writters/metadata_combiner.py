# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from dataclasses import dataclass

from dd_license_attribution.metadata_collector.metadata import Metadata


@dataclass
class CombinedMetadata:
    component: str | None
    origin: str | None
    version: str | None
    license: set[str]
    copyright: set[str]


def combine_metadata(metadata: list[Metadata]) -> list[CombinedMetadata]:
    combined_metadata: dict[tuple[str | None, str | None], CombinedMetadata] = {}
    for md in metadata:
        key = (md.name, md.origin)
        if key not in combined_metadata:
            combined_metadata[key] = CombinedMetadata(
                component=md.name,
                origin=md.origin,
                version=md.version,
                license=set(md.license),
                copyright=set(md.copyright),
            )
        else:
            row_data = combined_metadata[key]
            if row_data.version is None:
                row_data.version = md.version
            row_data.license.update(md.license)
            row_data.copyright.update(md.copyright)

    return sorted(
        combined_metadata.values(),
        key=lambda row: (row.component or "", row.origin or ""),
    )
