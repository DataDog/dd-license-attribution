# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import inspect

from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    DependencyFinderStrategy,
    MetadataCollectionStrategy,
    MetadataEnricherStrategy,
)


class TestStrategyHierarchy:
    def test_dependency_finder_strategy_is_subclass_of_metadata_collection_strategy(
        self,
    ) -> None:
        assert issubclass(DependencyFinderStrategy, MetadataCollectionStrategy)

    def test_metadata_enricher_strategy_is_subclass_of_metadata_collection_strategy(
        self,
    ) -> None:
        assert issubclass(MetadataEnricherStrategy, MetadataCollectionStrategy)

    def test_dependency_finder_strategy_is_abstract(self) -> None:
        assert inspect.isabstract(DependencyFinderStrategy)

    def test_metadata_enricher_strategy_is_abstract(self) -> None:
        assert inspect.isabstract(MetadataEnricherStrategy)

    def test_dependency_finder_and_enricher_are_distinct(self) -> None:
        assert not issubclass(DependencyFinderStrategy, MetadataEnricherStrategy)
        assert not issubclass(MetadataEnricherStrategy, DependencyFinderStrategy)
