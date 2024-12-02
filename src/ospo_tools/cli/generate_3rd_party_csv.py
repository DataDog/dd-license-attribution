# This file is an entry point for the command line tool generate-3rd-party-csv.
# Here we parse parameters and call the right metadata_collector and report_generator

import os
import sys
import typer
from agithub.GitHub import GitHub
from typing import Annotated

from ospo_tools.metadata_collector import MetadataCollector
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
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
import json
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
    go_licenses_csv_file: Annotated[
        str,
        typer.Option(
            help="The path to the Go licenses CSV output file to be used as hint."
        ),
    ] = "",
    debug: Annotated[
        str,
        typer.Option(
            help="A JSON formatted object used for debugging purposes. This is not a stable interface."
        ),
    ] = "",
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
    enabled_strategies = {
        "GitHubSbomMetadataCollectionStrategy": True,
        "GoLicensesMetadataCollectionStrategy": True,
        "ScanCodeToolkitMetadataCollectionStrategy": True,
        "GitHubRepositoryMetadataCollectionStrategy": True,
    }

    if debug:
        debug_info = json.loads(debug)
        if "enabled_strategies" in debug_info:
            debug_enabled_strategies = debug_info["enabled_strategies"]
            for strategy in enabled_strategies:
                if strategy not in debug_enabled_strategies:
                    enabled_strategies[strategy] = False
            print(f"DEBUG: Enabled strategies: {enabled_strategies}")
        else:
            print(
                "DEBUG: No strategies enabled - if you wanted to enable strategies, please provide a debug object with a list of them in the 'enabled_strategies' key."
            )
            print(
                'DEBUG: Example: --debug \'{"enabled_strategies": ["GitHubSbomMetadataCollectionStrategy", "GoLicensesMetadataCollectionStrategy"]}\''
            )
            print(
                "DEBUG: Available strategies: GitHubSbomMetadataCollectionStrategy, GoLicensesMetadataCollectionStrategy, ScanCodeToolkitMetadataCollectionStrategy, GitHubRepositoryMetadataCollectionStrategy"
            )

    github_token = os.environ.get("GITHUB_TOKEN")

    if not github_token:
        github_client = GitHub()
    else:
        github_client = GitHub(token=github_token)

    strategies: list[MetadataCollectionStrategy] = []

    if enabled_strategies["GitHubSbomMetadataCollectionStrategy"]:
        strategies.append(
            GitHubSbomMetadataCollectionStrategy(github_client, project_scope)
        )

    if (
        enabled_strategies["GoLicensesMetadataCollectionStrategy"]
        and go_licenses_csv_file
    ):
        with open(go_licenses_csv_file, "r") as f:
            go_licenses_report_hint = f.read()
        strategies.append(GoLicensesMetadataCollectionStrategy(go_licenses_report_hint))

    if enabled_strategies["ScanCodeToolkitMetadataCollectionStrategy"]:
        strategies.append(
            ScanCodeToolkitMetadataCollectionStrategy(
                cli_config.default_config.preset_license_file_locations,
                cli_config.default_config.preset_copyright_file_locations,
            )
        )
        if deep_scanning:
            strategies.append(ScanCodeToolkitMetadataCollectionStrategy())

    if enabled_strategies["GitHubRepositoryMetadataCollectionStrategy"]:
        strategies.append(GitHubRepositoryMetadataCollectionStrategy(github_client))

    metadata_collector = MetadataCollector(strategies)
    metadata = metadata_collector.collect_metadata(package)

    csv_reporter = ReportGenerator(CSVReportingWritter())

    output = csv_reporter.generate_report(metadata)
    print(output)


typer.run(main)

if __name__ == "__main__":
    typer.run(main)
