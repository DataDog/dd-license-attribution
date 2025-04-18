# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import pytest_mock

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.report_generator.report_generator import ReportGenerator
from dd_license_attribution.report_generator.writters.abstract_reporting_writter import (
    ReportingWritter,
)


def test_report_generator_saves_reporter_and_calls_it_when_metadata_is_passed(
    mocker: pytest_mock.MockFixture,
) -> None:
    reporting_writer_mock = mocker.Mock(spec_set=ReportingWritter)
    metadata = [
        Metadata(
            name="test",
            version="1.0.0",
            origin="test_origin",
            local_src_path=None,
            license=["MIT"],
            copyright=["test"],
        )
    ]

    report_generator = ReportGenerator(reporting_writer_mock)
    report_generator.generate_report(metadata)

    reporting_writer_mock.write.assert_called_once_with(metadata)
