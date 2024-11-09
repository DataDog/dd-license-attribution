import csv
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.report_generator.writters.abstract_reporting_writter import (
    ReportingWritter,
)
import io


class CSVReportingWritter(ReportingWritter):
    def write(self, metadata: list[Metadata]) -> str:
        field_names = ["component", "origin", "license", "copyright"]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=field_names, quoting=csv.QUOTE_ALL)

        writer.writeheader()
        for row in metadata:
            row_data = {
                "component": row.name,
                "origin": row.origin,
                "license": row.license,
                "copyright": row.copyright,
            }
            writer.writerow(row_data)
        csv_string = output.getvalue()
        output.close()
        return csv_string
