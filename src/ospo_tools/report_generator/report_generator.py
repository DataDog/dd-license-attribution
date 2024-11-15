from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.report_generator.writters.abstract_reporting_writter import (
    ReportingWritter,
)


class ReportGenerator:
    def __init__(self, reporting_writer: ReportingWritter):
        self.reporting_writer = reporting_writer

    def generate_report(self, metadata: list[Metadata]) -> str:
        return self.reporting_writer.write(metadata)
