from abc import ABC, abstractmethod

from ospo_tools.metadata_collector.metadata import Metadata


class ReportingWritter(ABC):
    @abstractmethod
    def write(self, metadata: list[Metadata]) -> str:
        raise NotImplementedError
