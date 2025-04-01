# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.report_generator.writters.abstract_reporting_writter import (
    ReportingWritter,
)


class ReportGenerator:
    def __init__(self, reporting_writer: ReportingWritter):
        self.reporting_writer = reporting_writer

    def generate_report(self, metadata: list[Metadata]) -> str:
        return self.reporting_writer.write(metadata)
