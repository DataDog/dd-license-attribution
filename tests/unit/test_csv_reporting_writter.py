from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.report_generator.writters.csv_reporting_writter import (
    CSVReportingWritter,
)


def test_csv_reporting_writter_writes_metadata_to_output_string(mocker):
    metadata = [
        Metadata(
            name="test",
            version="1.0.0",
            origin="test_origin",
            license="MIT",
            copyright="test_copyright",
        ),
        Metadata(
            name="test_2",
            version="2.0.0",
            origin="test_origin_2",
            license="APACHE-2.0",
            copyright="test_copyright_2",
        ),
    ]

    csv_report_writter = CSVReportingWritter()
    csv_string = csv_report_writter.write(metadata)

    expected_csv_string = '"component","origin","license","copyright"\r\n"test","test_origin","MIT","test_copyright"\r\n"test_2","test_origin_2","APACHE-2.0","test_copyright_2"\r\n'
    assert csv_string == expected_csv_string
