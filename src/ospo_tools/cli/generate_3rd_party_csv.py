# This file is an entry point for the command line tool generate-3rd-party-csv.
# Here we parse parameters and call the right metadata_collector and report_generator

import os
import typer
from agithub.GitHub import GitHub
from typing import Annotated

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
from ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy import (
    ScanCodeToolkitMetadataCollectionStrategy,
)
from ospo_tools.report_generator.report_generator import ReportGenerator
from ospo_tools.report_generator.writters.csv_reporting_writter import (
    CSVReportingWritter,
)

from ospo_tools.config import default_config


def main(
    package: Annotated[
        str, typer.Argument(help="The package to generate the report for.")
    ],
) -> None:
    """
    Generate a CSV report of third party dependencies for a given open source repository.
    """
    github_token = os.environ.get("GITHUB_TOKEN")

    if not github_token:
        github_client = GitHub()
    else:
        github_client = GitHub(token=github_token)

    metadata_collector = MetadataCollector(
        [
            GitHubSbomMetadataCollectionStrategy(github_client),
            GoLicensesMetadataCollectionStrategy(package),
            ScanCodeToolkitMetadataCollectionStrategy(
                default_config.preset_license_file_locations,
                default_config.preset_copyright_file_locations,
            ),
            ScanCodeToolkitMetadataCollectionStrategy(),
            GitHubRepositoryMetadataCollectionStrategy(github_client),
        ]
    )
    metadata = metadata_collector.collect_metadata(package)

    csv_reporter = ReportGenerator(CSVReportingWritter())

    output = csv_reporter.generate_report(metadata)
    print(output)


typer.run(main)

if __name__ == "__main__":
    typer.run(main)
