"""This test runs the Stratus Red Team CSV report and compares the output
 to the manually created CSV reports written by the Stratus Red Team."""

from src.metadata_collector import MetadataCollector
from src.metadata_collector.strategies.github_sbom_collection_strategy import GitHubMetadataCollectionStrategy
from src.report_generator.report_generator import ReportGenerator
from src.report_generator.writters.csv_reporting_writter import CSVReportingWritter

def test_stratus_red_team_csv_report():
    # Run the Stratus Red Team CSV report
    metadata_collector = MetadataCollector([GitHubMetadataCollectionStrategy('github_token')])
    metadata = metadata_collector.collect_metadata('https://github.com/DataDog/stratus-red-team')
    
    csv_reporter = ReportGenerator(metadata, CSVReportingWritter())
    
    output = csv_reporter.generate_report()
    # Compare the output to the manually created CSV reports
    with open('tests/integration/test_stratus_red_team_csv/expected_stratus_report.csv', 'r') as f:
        stratus_red_team_csv_report = f.read()
        assert output == stratus_red_team_csv_report
