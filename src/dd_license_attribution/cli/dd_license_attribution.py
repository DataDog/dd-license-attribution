# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

# This file is an entry point for the command line tool generate-3rd-party-csv.
# Here we parse parameters and call the right metadata_collector and report_generator

import sys
import tempfile
import typer
import logging
from agithub.GitHub import GitHub
from typing import Annotated
from dd_license_attribution.adaptors.os import path_exists, create_dirs
from dd_license_attribution.utils.logging import setup_logging

from collections.abc import Callable
from dd_license_attribution.artifact_management.python_env_manager import (
    PyEnvRuntimeError,
    PythonEnvManager,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    NonAccessibleRepository,
    SourceCodeManager,
    UnauthorizedRepository,
)
from dd_license_attribution.artifact_management.artifact_manager import (
    validate_cache_dir,
)
from dd_license_attribution.metadata_collector import MetadataCollector
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy import (
    GitHubRepositoryMetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy import (
    GitHubSbomMetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy import (
    GoPkgMetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.pypi_collection_strategy import (
    PypiMetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy import (
    ScanCodeToolkitMetadataCollectionStrategy,
)
from dd_license_attribution.report_generator.report_generator import ReportGenerator
import json
from dd_license_attribution.report_generator.writters.csv_reporting_writter import (
    CSVReportingWritter,
)

import dd_license_attribution.config.cli_configs as cli_config

from dd_license_attribution.metadata_collector.license_checker import LicenseChecker

app = typer.Typer(add_completion=False)


def mutually_exclusive_group() -> (
    Callable[[typer.Context, typer.CallbackParam, bool], bool | None]
):
    group = set()

    def callback(
        ctx: typer.Context, param: typer.CallbackParam, value: bool
    ) -> bool | None:
        # Add cli option to group if it was called with a value
        if (
            value is True
            and param.name not in group
            and (
                param.name == "only_root_project"
                or param.name == "only_transitive_dependencies"
            )
        ):
            group.add(param.name)

        if len(group) == 2:
            raise typer.BadParameter(
                "Cannot specify both only-root-project and only-transitive-dependencies"
            )

        return value

    return callback


only_root_project_or_transitive_callback = mutually_exclusive_group()


def cache_validation() -> (
    Callable[[typer.Context, typer.CallbackParam, str | None], str | None]
):
    group = {}
    param_dir = set()
    param_ttl = set()

    def callback(
        ctx: typer.Context, param: typer.CallbackParam, value: str | None
    ) -> str | None:
        if (
            param.name == "cache_dir"
            or param.name == "cache_ttl"
            or param.name == "force_cache_creation"
        ):
            group[param.name] = value
        if param.name == "cache_dir":
            param_dir.add(param)
        if param.name == "cache_ttl":
            param_ttl.add(param)
        if len(group) == 3:
            if group["cache_dir"] is None and group["cache_ttl"] is not None:
                raise typer.BadParameter(
                    "Cannot specify --cache-ttl without --cache-dir",
                    param=param_ttl.pop(),
                )
            if group["cache_dir"] is not None:
                if path_exists(group["cache_dir"]) is False:
                    if group["force_cache_creation"]:
                        create_dirs(group["cache_dir"])
                    else:
                        create = typer.confirm(
                            "The folder doesn't exist. Create?", err=True
                        )
                        if create:
                            create_dirs(group["cache_dir"])
                        else:
                            raise typer.BadParameter(
                                "Cache directory doesn't exist.",
                                param=param_dir.pop(),
                            )
                if validate_cache_dir(group["cache_dir"]) is False:
                    raise typer.BadParameter(
                        "Cache directory is not in the expected format.",
                        param=param_dir.pop(),
                    )
        return value

    return callback


cache_validation_callback = cache_validation()


def github_token_conditional_group() -> (
    Callable[[typer.Context, typer.CallbackParam, str | bool | None], str | bool | None]
):
    group = {}
    param_token = set()

    def callback(
        ctx: typer.Context, param: typer.CallbackParam, value: str | bool | None
    ) -> str | bool | None:
        if param.name == "github_token":
            param_token.add(param)
        if param.name == "github_token" or param.name == "no_gh_auth":
            group[param.name] = value
        if len(group) == 2:
            if group["github_token"] is None and group["no_gh_auth"] is False:
                raise typer.BadParameter(
                    message="No Github token available. If this is intentional, pass --no-gh-auth flag to the command. Throttling limits will be lower and access will be limited to public resources only.",
                    param=param_token.pop(),
                )

        return value

    return callback


github_token_callback = github_token_conditional_group()


@app.command()
def main(
    package: Annotated[
        str, typer.Argument(help="The package to generate the report for.")
    ],
    deep_scanning: Annotated[
        bool,
        typer.Option(
            "--deep-scanning",
            help="Enable deep scanning.",
            rich_help_panel="Scanning Options",
        ),
    ] = False,
    only_transitive_dependencies: Annotated[
        bool,
        typer.Option(
            "--only-transitive-dependencies",
            help="Only report on transitive dependencies.",
            rich_help_panel="Scanning Options",
            callback=only_root_project_or_transitive_callback,
        ),
    ] = False,
    only_root_project: Annotated[
        bool,
        typer.Option(
            "--only-root-project",
            help="Only report on the root project.",
            rich_help_panel="Scanning Options",
            callback=only_root_project_or_transitive_callback,
        ),
    ] = False,
    skip_pypi: Annotated[
        bool,
        typer.Option(
            "--no-pypi-strategy",
            help="Skip the PyPI collection strategy.",
            rich_help_panel="Scanning Options",
        ),
    ] = False,
    skip_gopkg: Annotated[
        bool,
        typer.Option(
            "--no-gopkg-strategy",
            help="Skip the GoPkg collection strategy.",
            rich_help_panel="Scanning Options",
        ),
    ] = False,
    cache_dir: Annotated[
        str | None,
        typer.Option(
            "--cache-dir",
            help="A directory to save artifacts, as cloned repositories, to reuse between runs. By default, nothing is reused and a new temp directory is created per run.",
            rich_help_panel="Cache Configuration",
            callback=cache_validation_callback,
        ),
    ] = None,
    force_cache_creation: Annotated[
        bool | None,
        typer.Option(
            "--force-cache-creation",
            help="Force the creation of a new cache directory, if it doesn't exist.",
            rich_help_panel="Cache Configuration",
            callback=cache_validation_callback,
        ),
    ] = None,
    cache_ttl: Annotated[
        int | None,
        typer.Option(
            "--cache-ttl",
            help="The time in seconds to keep the cache. Default is 86400 seconds (1 day).",
            rich_help_panel="Cache Configuration",
            callback=cache_validation_callback,
        ),
    ] = None,
    github_token: Annotated[
        str | None,
        typer.Option(
            "--github-token",
            help="The GitHub token to use for authentication. If not provided, the GITHUB_TOKEN environment variable will be used.",
            rich_help_panel="GitHub Authentication",
            envvar="GITHUB_TOKEN",
            callback=github_token_callback,
        ),
    ] = None,
    no_gh_auth: Annotated[
        bool,
        typer.Option(
            "--no-gh-auth",
            help="Do not use github auth token. Throttling limits are going to be lower and access to non public resources will be blocked.",
            rich_help_panel="GitHub Authentication",
            callback=github_token_callback,
        ),
    ] = False,
    debug: Annotated[
        str,
        typer.Option(
            help="A JSON formatted object used for debugging purposes. This is not a stable interface.",
            rich_help_panel="Debug Options",
        ),
    ] = "",
) -> None:
    """
    Generate a CSV report of third party dependencies for a given open source repository.
    """
    setup_logging(logging.INFO)

    if not only_root_project and not only_transitive_dependencies:
        project_scope = ProjectScope.ALL
    elif only_root_project:
        project_scope = ProjectScope.ONLY_ROOT_PROJECT
    elif only_transitive_dependencies:
        project_scope = ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES
    enabled_strategies = {
        "GitHubSbomMetadataCollectionStrategy": True,
        "GoPkgsMetadataCollectionStrategy": True,
        "PythonPipMetadataCollectionStrategy": True,
        "ScanCodeToolkitMetadataCollectionStrategy": True,
        "GitHubRepositoryMetadataCollectionStrategy": True,
    }

    if cache_ttl is None:
        cache_ttl = 86400
    if cache_dir is None:
        temp_dir = tempfile.TemporaryDirectory()
        cache_dir = temp_dir.name
    else:
        temp_dir = None

    if debug:
        debug_info = json.loads(debug)
        if "enabled_strategies" in debug_info:
            debug_enabled_strategies = debug_info["enabled_strategies"]
            for strategy in enabled_strategies:
                if strategy not in debug_enabled_strategies:
                    enabled_strategies[strategy] = False
            logging.debug(f"Enabled strategies: {enabled_strategies}")
        else:
            logging.debug(
                "No strategies enabled - if you wanted to enable strategies, provide a debug object with a list of them in the 'enabled_strategies' key."
            )
            logging.debug(
                'Example: --debug \'{"enabled_strategies": ["GitHubSbomMetadataCollectionStrategy", "GoPkgMetadataCollectionStrategy"]}\''
            )
            logging.debug(
                "Available strategies: GitHubSbomMetadataCollectionStrategy, GoPkgMetadataCollectionStrategy, ScanCodeToolkitMetadataCollectionStrategy, GitHubRepositoryMetadataCollectionStrategy"
            )

    if skip_pypi:
        enabled_strategies["PythonPipMetadataCollectionStrategy"] = False

    if skip_gopkg:
        enabled_strategies["GoPkgsMetadataCollectionStrategy"] = False

    if not github_token:
        github_client = GitHub()
    else:
        github_client = GitHub(token=github_token)

    strategies: list[MetadataCollectionStrategy] = []

    if enabled_strategies["GitHubSbomMetadataCollectionStrategy"]:
        strategies.append(
            GitHubSbomMetadataCollectionStrategy(github_client, project_scope)
        )

    try:
        source_code_manager = SourceCodeManager(cache_dir, cache_ttl)
    except ValueError as e:
        logging.error(str(e))
        sys.exit(1)

    if enabled_strategies["GoPkgsMetadataCollectionStrategy"]:
        strategies.append(
            GoPkgMetadataCollectionStrategy(package, source_code_manager, project_scope)
        )

    python_env_manager = PythonEnvManager(cache_dir, cache_ttl)

    if enabled_strategies["PythonPipMetadataCollectionStrategy"]:
        strategies.append(
            PypiMetadataCollectionStrategy(
                package, source_code_manager, python_env_manager, project_scope
            )
        )

    if enabled_strategies["ScanCodeToolkitMetadataCollectionStrategy"]:
        if deep_scanning:
            strategies.append(
                ScanCodeToolkitMetadataCollectionStrategy(source_code_manager)
            )
        else:
            strategies.append(
                ScanCodeToolkitMetadataCollectionStrategy(
                    source_code_manager,
                    cli_config.default_config.preset_license_file_locations,
                    cli_config.default_config.preset_copyright_file_locations,
                )
            )

    if enabled_strategies["GitHubRepositoryMetadataCollectionStrategy"]:
        strategies.append(GitHubRepositoryMetadataCollectionStrategy(github_client))

    metadata_collector = MetadataCollector(strategies)
    try:
        metadata = metadata_collector.collect_metadata(package)
    except (NonAccessibleRepository, UnauthorizedRepository) as e:
<<<<<<< HEAD
        logging.error(str(e))
=======
        print(f"\033[91m{e}\033[0m", file=sys.stderr)
>>>>>>> ceac356 (Add Python best practices)
        sys.exit(1)
    except PyEnvRuntimeError as e:
        logging.error(str(e))
        logging.error(
            "This error can be bypassed by skipping the PyPI strategy (--no-pypi-strategy)."
        )
        logging.error(
            "When skipping this strategy, the tool will not try to extract dependencies or metadata from PyPI."
        )
        sys.exit(1)

    csv_reporter = ReportGenerator(CSVReportingWritter())

    checker = LicenseChecker(cli_config.default_config.preset_cautionary_licenses)
    checker.check_cautionary_licenses(metadata)

    output = csv_reporter.generate_report(metadata)
    if temp_dir is not None:
        temp_dir.cleanup()
    print(output)


if __name__ == "__main__":
    app()
