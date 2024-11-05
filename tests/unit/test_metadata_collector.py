# need a mock metadata strategy
# need a mock reporting writer
# need a test that uses both

import copy
from ospo_tools.metadata_collector import MetadataCollector
from ospo_tools.metadata_collector.metadata import Metadata

import pytest


from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


def test_metadata_collector_with_no_strategies_returns_empty_metadata():
    metadata_collector = MetadataCollector([])
    metadata = metadata_collector.collect_metadata("package")
    expected = [
        Metadata(name="", version="", origin="package", license="", copyright="")
    ]
    assert metadata == expected


def test_metadata_collector_with_one_strategy_returns_metadata(mocker):
    mocked_metadata = Metadata(
        name="name",
        version="version",
        origin="origin",
        license="license",
        copyright="copyright",
    )
    mock_strategy = mocker.Mock(spec=MetadataCollectionStrategy)

    mock_strategy.augment_metadata.return_value = [mocked_metadata]
    expected = [mocked_metadata]

    metadata_collector = MetadataCollector([mock_strategy])
    actual_metadata = metadata_collector.collect_metadata("package")

    mock_strategy.augment_metadata.assert_called_once_with(
        [Metadata(name="", version="", origin="package", license="", copyright="")]
    )
    assert actual_metadata == expected


def test_metadata_collection_with_multiple_strategies_cascade_the_metadata():
    pass
