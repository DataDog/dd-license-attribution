# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.report_generator.writters.csv_reporting_writter import (
    CSVReportingWritter,
)


def test_csv_reporting_writter_writes_metadata_to_output_string() -> None:
    metadata = [
        Metadata(
            name="test",
            version="1.0.0",
            origin="test_origin",
            local_src_path=None,
            license=["MIT"],
            copyright=["test_copyright"],
        ),
        Metadata(
            name="test_2",
            version="2.0.0",
            origin="test_origin_2",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["test_copyright_2"],
        ),
    ]

    csv_report_writter = CSVReportingWritter()
    csv_string = csv_report_writter.write(metadata)

    expected_csv_string = '"component","origin","license","copyright"\r\n"test","test_origin","[\'MIT\']","[\'test_copyright\']"\r\n"test_2","test_origin_2","[\'APACHE-2.0\']","[\'test_copyright_2\']"\r\n'
    assert csv_string == expected_csv_string


def test_csv_reporting_writter_writes_metadata_to_output_string_in_consistent_order() -> (
    None
):
    # version is not part of the order because it is not used in the csv output
    # duplicated metadata package-origin combinations are expected to combine the licenses and copyrights
    metadata = [
        Metadata(
            name="r_test",
            version="1.0.0",
            origin="test_origin",
            local_src_path=None,
            license=["MIT", "APACHE-2.0", "AGPL-3.0"],
            copyright=["test_copyright", "original_copyright"],
        ),
        Metadata(
            name="a_test",
            version="0.2.0",
            origin="a_test_origin",
            local_src_path=None,
            license=["MIT", "APACHE-2.0", "AGPL-3.0"],
            copyright=["test_copyright", "original_copyright"],
        ),
        Metadata(
            name="a_test",
            version="0.1.0",
            origin="test_origin_1",
            local_src_path=None,
            license=["AGPL-3.0"],
            copyright=["test_copyright", "original_copyright"],
        ),
        Metadata(  # this is an odd case, but its possible 2 distrbutions of same package-version where obtenined form different origins
            name="a_test",
            version="0.2.0",
            origin="test_origin_2",
            local_src_path=None,
            license=["MIT", "APACHE-2.0", "AGPL-3.0"],
            copyright=["test_copyright", "original_copyright"],
        ),
        Metadata(  # this is an odd case, but its possible 2 distrbutions of same package-version where copyrighted differently in docs
            name="a_test",
            version="0.2.0",
            origin="test_origin_1",
            local_src_path=None,
            license=["MIT"],
            copyright=["test_copyright", "original_copyright", "new_copyright"],
        ),
    ]

    csv_report_writter = CSVReportingWritter()
    csv_string = csv_report_writter.write(metadata)

    csv_lines = csv_string.splitlines()
    assert len(csv_lines) == 5
    assert csv_lines[0] == '"component","origin","license","copyright"'
    assert (
        csv_lines[1]
        == "\"a_test\",\"a_test_origin\",\"['AGPL-3.0', 'APACHE-2.0', 'MIT']\",\"['original_copyright', 'test_copyright']\""
    )
    assert (
        csv_lines[2]
        == "\"a_test\",\"test_origin_1\",\"['AGPL-3.0', 'MIT']\",\"['new_copyright', 'original_copyright', 'test_copyright']\""
    )
    assert (
        csv_lines[3]
        == "\"a_test\",\"test_origin_2\",\"['AGPL-3.0', 'APACHE-2.0', 'MIT']\",\"['original_copyright', 'test_copyright']\""
    )
    assert (
        csv_lines[4]
        == "\"r_test\",\"test_origin\",\"['AGPL-3.0', 'APACHE-2.0', 'MIT']\",\"['original_copyright', 'test_copyright']\""
    )
