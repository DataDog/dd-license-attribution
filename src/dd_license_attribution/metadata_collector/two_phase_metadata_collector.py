# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import logging

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.override_strategy import (
    OverrideCollectionStrategy,
)

logger = logging.getLogger(__name__)

_FINDER_LOOP_MAX_ITERATIONS: int = 5


class TwoPhaseMetadataCollector:
    """Two-phase collector for the experimental strategy pipeline.

    Phase 1 runs all finders in a fixpoint loop until the dependency set
    stabilises (or the iteration threshold is reached).  Phase 2 runs all
    enrichers once on the complete, stable dependency set.

    The split between finders and enrichers is by convention: finders should
    only add new Metadata entries; enrichers should only update existing ones.
    Once per-ecosystem experimental strategy classes exist (subclassing
    DependencyFinderStrategy / MetadataEnricherStrategy), static typing will
    enforce this contract.  Until then, existing MetadataCollectionStrategy
    subclasses may be placed in either list.

    Override runs once after all finders per iteration (prevents add/remove
    oscillation) and once after each enricher (corrects enricher-introduced
    data).
    """

    def __init__(
        self,
        finders: list[MetadataCollectionStrategy],
        enrichers: list[MetadataCollectionStrategy],
        override_strategy: OverrideCollectionStrategy | None = None,
        max_finder_iterations: int = _FINDER_LOOP_MAX_ITERATIONS,
    ) -> None:
        self.finders = finders
        self.enrichers = enrichers
        self.override_strategy = override_strategy
        self.max_finder_iterations = max_finder_iterations

    def collect_metadata(self, package: str) -> list[Metadata]:
        metadata: list[Metadata] = [
            Metadata(
                name=package.replace("https://", "").replace("http://", ""),
                version=None,
                origin=package,
                local_src_path=None,
                license=[],
                copyright=[],
            )
        ]

        # Phase 1: run all finders in a fixpoint loop.
        # Override runs once per iteration AFTER all finders — applying removals
        # before the stability check prevents an infinite loop where a finder
        # re-adds a dep that the override removes every iteration.
        # Skip entirely when no finders are configured.
        if self.finders:
            for _ in range(self.max_finder_iterations):
                previous_names = frozenset(
                    m.name for m in metadata if m.name is not None
                )
                for finder in self.finders:
                    metadata = finder.augment_metadata(metadata)
                if self.override_strategy is not None:
                    metadata = self.override_strategy.augment_metadata(metadata)
                current_names = frozenset(
                    m.name for m in metadata if m.name is not None
                )
                if current_names == previous_names:
                    break
            else:
                logger.warning(
                    "Finder loop did not stabilise after %d iterations; "
                    "proceeding with partial dependency closure.",
                    self.max_finder_iterations,
                )

        # Phase 2: run all enrichers once on the stable dependency set.
        # Override runs AFTER each enricher so it can correct data the enricher
        # introduced (e.g. wrong license inferred from source scan).
        for enricher in self.enrichers:
            metadata = enricher.augment_metadata(metadata)
            if self.override_strategy is not None:
                metadata = self.override_strategy.augment_metadata(metadata)

        return metadata
