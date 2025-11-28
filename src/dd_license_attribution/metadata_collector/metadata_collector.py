# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

"""Metadata collector class uses passed strategies to collect metadata from
a package and its dependencies."""

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


class MetadataCollector:
    # constructor
    def __init__(self, strategies: list[MetadataCollectionStrategy]):
        self.strategies = strategies

    # method to collect metadata
    def collect_metadata(self, package: str) -> list[Metadata]:
        # for each strategy in the list of strategies collect metadata and
        # pass it to next strategy
        initial_package_metadata = Metadata(
            name=package.replace("https://", "").replace("http://", ""),
            version=None,
            origin=package,
            local_src_path=None,
            license=[],
            copyright=[],
        )
        metadata = [initial_package_metadata]
        for strategy in self.strategies:
            metadata = strategy.augment_metadata(metadata)
        return metadata
