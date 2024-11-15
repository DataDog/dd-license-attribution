from abc import ABC, abstractmethod
from typing import List
from ospo_tools.metadata_collector.metadata import Metadata


class MetadataCollectionStrategy(ABC):
    @abstractmethod
    def augment_metadata(self, metadata: List[Metadata]) -> List[Metadata]:
        raise NotImplementedError
