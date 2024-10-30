# This file is an entry point for the command line tool generate-3rd-party-csv.
# Here we parse parameters and call the right metadata_collector and report_generator

import argparse
import os
from ospo_tools.metadata_collector import MetadataCollector
from ospo_tools.metadata_collector.strategies.github_repository_collection_strategy import (
    GitHubRepositoryMetadataCollectionStrategy,
)
from ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy import (
    GitHubSbomMetadataCollectionStrategy,
)
from ospo_tools.metadata_collector.strategies.go_licenses_collection_strategy import (
    GoLicensesMetadataCollectionStrategy,
)
from ospo_tools.report_generator.report_generator import ReportGenerator
from ospo_tools.report_generator.writters.csv_reporting_writter import (
    CSVReportingWritter,
)


def cli():
    parser = argparse.ArgumentParser(
        description="Generate a CSV report of 3rd party dependencies for a given package"
    )
    parser.add_argument(
        "package", type=str, help="The package to generate the report for"
    )
    args = parser.parse_args()

    # obtain github token from environment variable
    github_token = os.environ.get("GITHUB_TOKEN")

    metadata_collector = MetadataCollector(
        [
            GitHubSbomMetadataCollectionStrategy(github_token),
            GoLicensesMetadataCollectionStrategy(args.package),
            GitHubRepositoryMetadataCollectionStrategy(github_token),
        ]
    )
    metadata = metadata_collector.collect_metadata(args.package)

    csv_reporter = ReportGenerator(metadata, CSVReportingWritter())

    output = csv_reporter.generate_report()
    print(output)


if __name__ == "__main__":
    cli()
