from ospo_tools.metadata_collector import MetadataCollector
from ospo_tools.metadata_collector.metadata import Metadata
import pytest_mock

from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


def test_metadata_collector_with_no_strategies_returns_empty_metadata() -> None:
    metadata_collector = MetadataCollector([])
    metadata = metadata_collector.collect_metadata("https://package")
    expected = [
        Metadata(
            name="package",
            version="",
            origin="https://package",
            license=[],
            copyright=[],
        )
    ]
    assert metadata == expected


def test_metadata_collector_with_one_strategy_returns_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    mocked_metadata = Metadata(
        name="name",
        version="version",
        origin="origin",
        license=["license"],
        copyright=["copyright"],
    )
    mock_strategy = mocker.Mock(spec=MetadataCollectionStrategy)

    mock_strategy.augment_metadata.return_value = [mocked_metadata]
    expected = [mocked_metadata]

    metadata_collector = MetadataCollector([mock_strategy])
    actual_metadata = metadata_collector.collect_metadata("http://package")

    mock_strategy.augment_metadata.assert_called_once_with(
        [
            Metadata(
                name="package",
                version="",
                origin="http://package",
                license=[],
                copyright=[],
            )
        ]
    )
    assert actual_metadata == expected


def test_metadata_collection_with_multiple_strategies_cascade_the_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    mocked_metadata = Metadata(
        name="name",
        version="version",
        origin="origin",
        license=["license"],
        copyright=["copyright"],
    )

    mock_strategy_1 = mocker.Mock(spec=MetadataCollectionStrategy)
    mock_strategy_2 = mocker.Mock(spec=MetadataCollectionStrategy)
    mock_strategy_1.augment_metadata.return_value = [mocked_metadata]
    mock_strategy_2.augment_metadata.return_value = [mocked_metadata]

    metadata_collector = MetadataCollector([mock_strategy_1, mock_strategy_2])

    updated_metadata = metadata_collector.collect_metadata("http://package")

    mock_strategy_1.augment_metadata.assert_called_once_with(
        [
            Metadata(
                name="package",
                version="",
                origin="http://package",
                license=[],
                copyright=[],
            )
        ]
    )
    mock_strategy_2.augment_metadata.assert_called_once_with([mocked_metadata])

    assert updated_metadata == [mocked_metadata]

    expected = [mocked_metadata]
