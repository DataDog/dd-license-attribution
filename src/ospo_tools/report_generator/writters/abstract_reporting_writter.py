from abc import ABC, abstractmethod


class ReportingWritter(ABC):
    @abstractmethod
    def write(self, data) -> None:
        pass
