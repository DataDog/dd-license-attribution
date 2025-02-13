"""Metadata collector class uses passed strategies to collect metadata from
a package and its dependencies."""

from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
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
