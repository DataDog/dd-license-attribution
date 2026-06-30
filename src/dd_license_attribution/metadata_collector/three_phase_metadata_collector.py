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


class ThreePhaseMetadataCollector:
    """Three-phase (pre-find / find / enrich) collector for the experimental strategy pipeline.

    Phase 0 runs pre_finders once on the root seed — for strategies that already
    perform full transitive closure themselves (e.g. GitHub SBOM) and must not be
    re-invoked on every discovered dependency.

    Phase 1 runs all finders in a fixpoint loop until the dependency set
    stabilises (or the iteration threshold is reached) — for strategies that
    discover one level of deps at a time and benefit from iteration.

    Phase 2 runs all enrichers once on the complete, stable dependency set.

    Override runs once after Phase 0, once after all finders per Phase 1 iteration
    (prevents add/remove oscillation), and once after each enricher in Phase 2
    (corrects enricher-introduced data).
    """

    def __init__(
        self,
        finders: list[MetadataCollectionStrategy],
        enrichers: list[MetadataCollectionStrategy],
        pre_finders: list[MetadataCollectionStrategy] | None = None,
        override_strategy: OverrideCollectionStrategy | None = None,
        max_finder_iterations: int = _FINDER_LOOP_MAX_ITERATIONS,
    ) -> None:
        self.pre_finders = pre_finders or []
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

        # Phase 0: run pre_finders once on the root seed only.
        # Used for strategies that already perform full transitive closure (e.g.
        # GitHub SBOM) — re-running them on each discovered dep causes an
        # explosion into unrelated dep trees.
        if self.pre_finders:
            for pre_finder in self.pre_finders:
                metadata = pre_finder.augment_metadata(metadata)
            if self.override_strategy is not None:
                metadata = self.override_strategy.augment_metadata(metadata)

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
