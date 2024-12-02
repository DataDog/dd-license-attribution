# This file is an entry point for the command line tool generate-3rd-party-csv.
# Here we parse parameters and call the right metadata_collector and report_generator

import os
import sys
import typer
from agithub.GitHub import GitHub
from typing import Annotated

from ospo_tools.metadata_collector import MetadataCollector
from ospo_tools.metadata_collector.strategies.github_repository_collection_strategy import (
    GitHubRepositoryMetadataCollectionStrategy,
)
from ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy import (
    GitHubSbomMetadataCollectionStrategy,
    ProjectScope,
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

import ospo_tools.config.cli_configs as cli_config


def main(
    package: Annotated[
        str, typer.Argument(help="The package to generate the report for.")
    ],
    deep_scanning: Annotated[
        bool, typer.Option("--deep-scanning", help="Enable deep scanning.")
    ] = False,
    only_transitive_dependencies: Annotated[
        bool,
        typer.Option(
            "--only-transitive-dependencies",
            help="Only report on transitive dependencies.",
        ),
    ] = False,
    only_root_project: Annotated[
        bool,
        typer.Option("--only-root-project", help="Only report on the root project."),
    ] = False,
) -> None:
    """
    Generate a CSV report of third party dependencies for a given open source repository.
    """
    if only_root_project and only_transitive_dependencies:
        print(
            "\033[91mCannot specify both --only-root-project and --only-transitive-dependencies\033[0m",
            file=sys.stderr,
        )
        sys.exit(1)
    if not only_root_project and not only_transitive_dependencies:
        project_scope = ProjectScope.ALL
    elif only_root_project:
        project_scope = ProjectScope.ONLY_ROOT_PROJECT
    elif only_transitive_dependencies:
        project_scope = ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES

    github_token = os.environ.get("GITHUB_TOKEN")

    if not github_token:
        github_client = GitHub()
    else:
        github_client = GitHub(token=github_token)

    strategies = [
        GitHubSbomMetadataCollectionStrategy(github_client, project_scope),
        GoLicensesMetadataCollectionStrategy(package),
        ScanCodeToolkitMetadataCollectionStrategy(
            cli_config.default_config.preset_license_file_locations,
            cli_config.default_config.preset_copyright_file_locations,
        ),
    ]

    if deep_scanning:
        strategies.append(ScanCodeToolkitMetadataCollectionStrategy())

    strategies.append(GitHubRepositoryMetadataCollectionStrategy(github_client))

    metadata_collector = MetadataCollector(strategies)
    metadata = metadata_collector.collect_metadata(package)

    csv_reporter = ReportGenerator(CSVReportingWritter())

    output = csv_reporter.generate_report(metadata)
    print(output)


typer.run(main)

if __name__ == "__main__":
    typer.run(main)
