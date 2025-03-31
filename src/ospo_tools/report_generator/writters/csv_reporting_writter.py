# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import csv
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.report_generator.writters.abstract_reporting_writter import (
    ReportingWritter,
)
import io


class CSVReportingWritter(ReportingWritter):
    def write(self, metadata: list[Metadata]) -> str:
        class RowOfData:
            def __init__(
                self,
                component: str | None,
                origin: str | None,
                license: set[str],
                copyright: set[str],
            ):
                self.component = component
                self.origin = origin
                self.license = license
                self.copyright = copyright

        field_names = ["component", "origin", "license", "copyright"]
        output = io.StringIO()
        writer = csv.DictWriter(output, fieldnames=field_names, quoting=csv.QUOTE_ALL)

        writer.writeheader()
        combined_metadata: dict[tuple[str | None, str | None], RowOfData] = {}
        for md in metadata:
            key = (md.name, md.origin)
            if key not in combined_metadata:
                combined_metadata[key] = RowOfData(
                    md.name, md.origin, set(md.license), set(md.copyright)
                )
            else:
                combined_metadata[key].license.update(md.license)
                combined_metadata[key].copyright.update(md.copyright)

        for row_data in sorted(
            combined_metadata.values(), key=lambda x: (x.component, x.origin)
        ):
            prepared_row = {
                "component": row_data.component,
                "origin": row_data.origin,
                "license": str(sorted(row_data.license)),
                "copyright": str(sorted(row_data.copyright)),
            }
            writer.writerow(prepared_row)
        csv_string = output.getvalue()
        output.close()
        return csv_string
