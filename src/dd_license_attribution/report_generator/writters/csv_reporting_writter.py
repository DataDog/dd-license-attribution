# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import csv
import io

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.report_generator.writters.abstract_reporting_writter import (
    ReportingWritter,
)
from dd_license_attribution.report_generator.writters.metadata_combiner import (
    combine_metadata,
)


class CSVReportingWritter(ReportingWritter):
    def write(self, metadata: list[Metadata]) -> str:
        field_names = ["component", "origin", "license", "copyright"]
        output = io.StringIO()
        writer = csv.DictWriter(
            output, fieldnames=field_names, quoting=csv.QUOTE_ALL, lineterminator="\r\n"
        )

        writer.writeheader()
        for row_data in combine_metadata(metadata):
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
