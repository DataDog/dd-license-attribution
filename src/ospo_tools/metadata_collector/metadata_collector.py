""" Metadata collector class uses passed strategies to collect metadata from
    a package and its dependencies. """

from ospo_tools.metadata_collector.metadata import Metadata


class MetadataCollector:
    # constructor
    def __init__(self, strategies):
        self.strategies = strategies

    # method to collect metadata
    def collect_metadata(self, package):
        # for each strategy in the list of strategies collect metadata and
        # pass it to next strategy
        initial_package_metadata = Metadata(
            name="", version="", origin=package, license="", copyright=""
        )
        metadata = [initial_package_metadata]
        for strategy in self.strategies:
            metadata = strategy.augment_metadata(metadata)
        return metadata
