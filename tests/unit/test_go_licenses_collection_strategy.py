from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy import (
    GoLicensesMetadataCollectionStrategy,
)


def test_go_licenses_with_non_properly_formatted_go_licenses_report_hint_raises_exception() -> (
    None
):
    strategy = GoLicensesMetadataCollectionStrategy("test_purl")

    initial_metadata = [
        Metadata(
            name="test_package", origin=None, license=[], version=None, copyright=[]
        )
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == initial_metadata


def test_go_licenses_collection_strategy_parses_the_hint_and_uses_its_licenses() -> (
    None
):
    go_hints = "package1,http://test_license_url1,license1\npackage2,http://test_license_url2,license2\n"
    strategy = GoLicensesMetadataCollectionStrategy(go_hints)

    initial_metadata = [
        Metadata(
            name="package1",
            origin=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package2",
            origin=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)
    expected_metadata = [
        Metadata(
            name="package1",
            origin=None,
            license=["license1"],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package2",
            origin=None,
            license=["license2"],
            version=None,
            copyright=[],
        ),
    ]

    assert result == expected_metadata


def test_go_licenses_collection_strategy_do_not_add_hints_not_in_the_received_closure() -> (
    None
):
    go_hints = "package1,http://test_license_url1,license1\npackage2,http://test_license_url2,license2\n"
    strategy = GoLicensesMetadataCollectionStrategy(go_hints)

    initial_metadata = [
        Metadata(
            name="package1",
            origin=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package3",
            origin=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)
    expected_metadata = [
        Metadata(
            name="package1",
            origin=None,
            license=["license1"],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package3",
            origin=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    assert result == expected_metadata


def test_licenses_collection_strategy_ignores_hints_that_are_empty_or_unknown() -> None:
    go_hints = "package1,http://test_license_url1,Unknown\npackage2,http://test_license_url2,\n"
    strategy = GoLicensesMetadataCollectionStrategy(go_hints)

    initial_metadata = [
        Metadata(
            name="package1",
            origin=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package2",
            origin=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package3",
            origin=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == initial_metadata


def test_go_licenses_collection_strategy_replaces_origin_when_identified_a_valid_one_and_received_is_invalid() -> (
    None
):
    go_hints = "package1,https://github.com/Azure/azure-sdk-for-go/blob/sdk/resourcemanager/compute/armcompute/v1.0.0/sdk/resourcemanager/compute/armcompute/LICENSE.txt,LICENSE\npackage2,Unknown,Unknown\npackage3,http://test_license_url/package/LICENSE.txt,LICENSE\n"
    strategy = GoLicensesMetadataCollectionStrategy(go_hints)

    initial_metadata = [
        Metadata(
            name="package1",
            origin="invalid_url/invalid_repo",
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package2",
            origin="invalid_url/invalid_repo",
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package3",
            origin="https://github.com/DataDog/datadog-agent",
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert (
        result[0].origin
        == "https://github.com/Azure/azure-sdk-for-go/tree/sdk/resourcemanager/compute/armcompute/v1.0.0/sdk/resourcemanager/compute/armcompute"
    )  # the origin is replaced by the hint
    assert result[0].license == ["LICENSE"]  # the license is added from the hint
    assert (
        result[1].origin == "invalid_url/invalid_repo"
    )  # the origin is not replaced by the hint since hint is invalid
    assert (
        result[1].license == []
    )  # the license is not added from the hint since hint is invalid
    assert (
        result[2].origin == "https://github.com/DataDog/datadog-agent"
    )  # the origin is not replaced by the hint since it is valid
    assert result[2].license == [
        "LICENSE"
    ]  # the license is added from the hint since hint is valid
