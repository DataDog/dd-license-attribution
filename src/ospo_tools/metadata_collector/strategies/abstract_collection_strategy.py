from abc import ABC, abstractmethod

class MetadataCollectionStrategy(ABC):
    @abstractmethod
    def augment_metadata(self, metadata):
        pass