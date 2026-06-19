# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import logging

import pytest
import pytest_mock

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    DependencyFinderStrategy,
    MetadataEnricherStrategy,
)
from dd_license_attribution.metadata_collector.strategies.override_strategy import (
    OverrideCollectionStrategy,
)
from dd_license_attribution.metadata_collector.two_phase_metadata_collector import (
    TwoPhaseMetadataCollector,
)

_SEED = Metadata(
    name="pkg",
    version=None,
    origin="https://pkg",
    local_src_path=None,
    license=[],
    copyright=[],
)

_DEP = Metadata(
    name="dep-a",
    version="1.0",
    origin="https://dep-a",
    local_src_path=None,
    license=[],
    copyright=[],
)

_DEP_WITH_LICENSE = Metadata(
    name="dep-a",
    version="1.0",
    origin="https://dep-a",
    local_src_path=None,
    license=["MIT"],
    copyright=["Author"],
)


class TestTwoPhaseMetadataCollectorNoStrategies:
    def test_no_finders_no_enrichers_returns_seed(self) -> None:
        collector = TwoPhaseMetadataCollector(finders=[], enrichers=[])
        result = collector.collect_metadata("https://pkg")
        assert result == [_SEED]

    def test_seed_strips_https_prefix_from_name(self) -> None:
        collector = TwoPhaseMetadataCollector(finders=[], enrichers=[])
        result = collector.collect_metadata("https://github.com/owner/repo")
        assert result[0].name == "github.com/owner/repo"
        assert result[0].origin == "https://github.com/owner/repo"


class TestTwoPhaseMetadataCollectorFinderPhase:
    def test_finder_receives_seed_on_first_call_and_its_output_is_used(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        # finder adds _DEP on first call, so the loop runs a second iteration —
        # check the first call received the seed and that _DEP appears in the result
        finder = mocker.Mock(spec=DependencyFinderStrategy)
        finder.augment_metadata.side_effect = [
            [_SEED, _DEP],  # iteration 1: adds dep
            [_SEED, _DEP],  # iteration 2: stabilises
        ]

        collector = TwoPhaseMetadataCollector(finders=[finder], enrichers=[])
        result = collector.collect_metadata("https://pkg")

        assert finder.augment_metadata.call_args_list[0].args[0] == [_SEED]
        assert _DEP in result

    def test_finder_that_adds_dep_causes_second_iteration(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        call_count = 0

        def add_dep_once(metadata: list[Metadata]) -> list[Metadata]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [*metadata, _DEP]
            return metadata

        finder = mocker.Mock(spec=DependencyFinderStrategy)
        finder.augment_metadata.side_effect = add_dep_once

        collector = TwoPhaseMetadataCollector(finders=[finder], enrichers=[])
        collector.collect_metadata("https://pkg")

        assert finder.augment_metadata.call_count == 2

    def test_finder_that_adds_dep_stabilises_before_threshold(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        call_count = 0

        def add_dep_once(metadata: list[Metadata]) -> list[Metadata]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [*metadata, _DEP]
            return metadata

        finder = mocker.Mock(spec=DependencyFinderStrategy)
        finder.augment_metadata.side_effect = add_dep_once

        collector = TwoPhaseMetadataCollector(finders=[finder], enrichers=[])
        collector.collect_metadata("https://pkg")

        assert finder.augment_metadata.call_count == 2

    def test_enrichers_receive_deps_discovered_in_later_finder_iterations(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        call_count = 0

        def add_dep_once(metadata: list[Metadata]) -> list[Metadata]:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return [*metadata, _DEP]
            return metadata

        finder = mocker.Mock(spec=DependencyFinderStrategy)
        finder.augment_metadata.side_effect = add_dep_once

        enricher = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher.augment_metadata.return_value = [_SEED, _DEP_WITH_LICENSE]

        collector = TwoPhaseMetadataCollector(finders=[finder], enrichers=[enricher])
        collector.collect_metadata("https://pkg")

        enricher.augment_metadata.assert_called_once_with([_SEED, _DEP])

    def test_finder_never_stabilises_logs_warning_and_proceeds(
        self, mocker: pytest_mock.MockFixture, caplog: pytest.LogCaptureFixture
    ) -> None:
        counter = 0

        def always_add(metadata: list[Metadata]) -> list[Metadata]:
            nonlocal counter
            counter += 1
            return [
                *metadata,
                Metadata(
                    name=f"dep-{counter}",
                    version=None,
                    origin=f"https://dep-{counter}",
                    local_src_path=None,
                    license=[],
                    copyright=[],
                ),
            ]

        finder = mocker.Mock(spec=DependencyFinderStrategy)
        finder.augment_metadata.side_effect = always_add

        enricher = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher.augment_metadata.side_effect = lambda m: m

        collector = TwoPhaseMetadataCollector(
            finders=[finder], enrichers=[enricher], max_finder_iterations=3
        )

        with caplog.at_level(logging.WARNING):
            collector.collect_metadata("https://pkg")

        assert finder.augment_metadata.call_count == 3
        assert any("stabilise" in record.message for record in caplog.records)
        enricher.augment_metadata.assert_called_once()

    def test_multiple_finders_all_run_each_iteration(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        finder_a = mocker.Mock(spec=DependencyFinderStrategy)
        finder_a.augment_metadata.side_effect = lambda m: m

        finder_b = mocker.Mock(spec=DependencyFinderStrategy)
        finder_b.augment_metadata.side_effect = lambda m: m

        collector = TwoPhaseMetadataCollector(
            finders=[finder_a, finder_b], enrichers=[]
        )
        collector.collect_metadata("https://pkg")

        finder_a.augment_metadata.assert_called_once()
        finder_b.augment_metadata.assert_called_once()


class TestTwoPhaseMetadataCollectorEnricherPhase:
    def test_enricher_runs_after_finders(self, mocker: pytest_mock.MockFixture) -> None:
        call_order: list[str] = []

        def track_finder(m: list[Metadata]) -> list[Metadata]:
            call_order.append("finder")
            return m

        def track_enricher(m: list[Metadata]) -> list[Metadata]:
            call_order.append("enricher")
            return m

        finder = mocker.Mock(spec=DependencyFinderStrategy)
        finder.augment_metadata.side_effect = track_finder

        enricher = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher.augment_metadata.side_effect = track_enricher

        collector = TwoPhaseMetadataCollector(finders=[finder], enrichers=[enricher])
        collector.collect_metadata("https://pkg")

        assert call_order == ["finder", "enricher"]

    def test_multiple_enrichers_run_in_sequence(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        call_order: list[str] = []

        def track_a(m: list[Metadata]) -> list[Metadata]:
            call_order.append("a")
            return m

        def track_b(m: list[Metadata]) -> list[Metadata]:
            call_order.append("b")
            return m

        enricher_a = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher_a.augment_metadata.side_effect = track_a

        enricher_b = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher_b.augment_metadata.side_effect = track_b

        collector = TwoPhaseMetadataCollector(
            finders=[], enrichers=[enricher_a, enricher_b]
        )
        collector.collect_metadata("https://pkg")

        assert call_order == ["a", "b"]

    def test_enricher_receives_output_of_previous_enricher(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        enricher_a = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher_a.augment_metadata.return_value = [_DEP_WITH_LICENSE]

        enricher_b = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher_b.augment_metadata.return_value = [_DEP_WITH_LICENSE]

        collector = TwoPhaseMetadataCollector(
            finders=[], enrichers=[enricher_a, enricher_b]
        )
        collector.collect_metadata("https://pkg")

        enricher_b.augment_metadata.assert_called_once_with([_DEP_WITH_LICENSE])


class TestTwoPhaseMetadataCollectorOverride:
    def test_override_runs_after_all_finders_in_each_iteration(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        # Override must run AFTER all finders in Phase 1 so that a REMOVE rule
        # targeting a dep a finder keeps adding stabilises in one iteration rather
        # than oscillating forever.
        call_order: list[str] = []

        def track_finder(m: list[Metadata]) -> list[Metadata]:
            call_order.append("finder")
            return m

        def track_override(m: list[Metadata]) -> list[Metadata]:
            call_order.append("override")
            return m

        finder = mocker.Mock(spec=DependencyFinderStrategy)
        finder.augment_metadata.side_effect = track_finder

        override = mocker.Mock(spec=OverrideCollectionStrategy)
        override.augment_metadata.side_effect = track_override

        collector = TwoPhaseMetadataCollector(
            finders=[finder], enrichers=[], override_strategy=override
        )
        collector.collect_metadata("https://pkg")

        assert call_order == ["finder", "override"]

    def test_override_runs_after_each_enricher(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        # Override runs AFTER each enricher so it can correct data the enricher
        # introduced (e.g. a wrong license inferred from a source scan).
        call_order: list[str] = []

        def track_enricher(m: list[Metadata]) -> list[Metadata]:
            call_order.append("enricher")
            return m

        def track_override(m: list[Metadata]) -> list[Metadata]:
            call_order.append("override")
            return m

        enricher = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher.augment_metadata.side_effect = track_enricher

        override = mocker.Mock(spec=OverrideCollectionStrategy)
        override.augment_metadata.side_effect = track_override

        collector = TwoPhaseMetadataCollector(
            finders=[], enrichers=[enricher], override_strategy=override
        )
        collector.collect_metadata("https://pkg")

        assert call_order == ["enricher", "override"]

    def test_full_override_order_finder_then_enricher(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        call_order: list[str] = []

        def track_finder(m: list[Metadata]) -> list[Metadata]:
            call_order.append("finder")
            return m

        def track_enricher(m: list[Metadata]) -> list[Metadata]:
            call_order.append("enricher")
            return m

        def track_override(m: list[Metadata]) -> list[Metadata]:
            call_order.append("override")
            return m

        finder = mocker.Mock(spec=DependencyFinderStrategy)
        finder.augment_metadata.side_effect = track_finder

        enricher = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher.augment_metadata.side_effect = track_enricher

        override = mocker.Mock(spec=OverrideCollectionStrategy)
        override.augment_metadata.side_effect = track_override

        collector = TwoPhaseMetadataCollector(
            finders=[finder], enrichers=[enricher], override_strategy=override
        )
        collector.collect_metadata("https://pkg")

        # Phase 1: all finders, then override once (prevents add/remove oscillation)
        # Phase 2: each enricher runs, then override corrects what it introduced
        assert call_order == ["finder", "override", "enricher", "override"]

    def test_no_override_does_not_fail(self, mocker: pytest_mock.MockFixture) -> None:
        finder = mocker.Mock(spec=DependencyFinderStrategy)
        finder.augment_metadata.side_effect = lambda m: m

        enricher = mocker.Mock(spec=MetadataEnricherStrategy)
        enricher.augment_metadata.side_effect = lambda m: m

        collector = TwoPhaseMetadataCollector(
            finders=[finder], enrichers=[enricher], override_strategy=None
        )
        result = collector.collect_metadata("https://pkg")
        assert result == [_SEED]
