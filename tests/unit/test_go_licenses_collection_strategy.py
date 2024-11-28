import os
from unittest.mock import Mock, call, mock_open, patch

import pytest
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy import (
    GoLicensesMetadataCollectionStrategy,
)


def test_go_licenses_with_non_properly_formatted_go_licenses_report_hint_raises_exception():
    strategy = GoLicensesMetadataCollectionStrategy("test_purl")

    initial_metadata = [
        Metadata(
            name="go:test_package", origin=None, license=[], version=None, copyright=[]
        )
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == initial_metadata


def test_go_licenses_collection_strategy_parses_the_hint_and_uses_its_licenses(mocker):
    go_hints = "package1,http://test_license_url1,license1\npackage2,http://test_license_url2,license2\n"
    strategy = GoLicensesMetadataCollectionStrategy(go_hints)

    initial_metadata = [
        Metadata(
            name="go:package1",
            origin=None,
            license=[],
            version=[],
            copyright=[],
        ),
        Metadata(
            name="go:package2",
            origin=None,
            license=[],
            version=[],
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)
    expected_metadata = [
        Metadata(
            name="go:package1",
            origin=None,
            license=["license1"],
            version=[],
            copyright=[],
        ),
        Metadata(
            name="go:package2",
            origin=None,
            license=["license2"],
            version=[],
            copyright=[],
        ),
    ]

    assert result == expected_metadata


def test_go_licenses_collection_strategy_do_not_add_hints_not_in_the_received_closure():
    go_hints = "package1,http://test_license_url1,license1\npackage2,http://test_license_url2,license2\n"
    strategy = GoLicensesMetadataCollectionStrategy(go_hints)

    initial_metadata = [
        Metadata(
            name="go:package1",
            origin=None,
            license=[],
            version=[],
            copyright=[],
        ),
        Metadata(
            name="go:package3",
            origin=None,
            license=[],
            version=[],
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)
    expected_metadata = [
        Metadata(
            name="go:package1",
            origin=None,
            license=["license1"],
            version=[],
            copyright=[],
        ),
        Metadata(
            name="go:package3",
            origin=None,
            license=[],
            version=[],
            copyright=[],
        ),
    ]

    assert result == expected_metadata


def test_licenses_collection_strategy_ignores_hints_that_are_empty_or_unknown():
    go_hints = "package1,http://test_license_url1,Unknown\npackage2,http://test_license_url2,\n"
    strategy = GoLicensesMetadataCollectionStrategy(go_hints)

    initial_metadata = [
        Metadata(
            name="go:package1",
            origin=None,
            license=[],
            version=[],
            copyright=[],
        ),
        Metadata(
            name="go:package2",
            origin=None,
            license=[],
            version=[],
            copyright=[],
        ),
        Metadata(
            name="go:package3",
            origin=None,
            license=[],
            version=[],
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == initial_metadata
