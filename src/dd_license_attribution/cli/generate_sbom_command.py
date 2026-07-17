# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

# Command for generating SBOM (Software Bill of Materials) reports.

import contextlib
import copy
import inspect
import json
import logging
import sys
import tempfile
from collections.abc import Callable
from typing import Annotated, Any, get_args, get_origin

import click
import typer
from agithub.GitHub import GitHub

import dd_license_attribution.config.cli_configs as cli_config
from dd_license_attribution.adaptors.os import (
    create_dirs,
    path_exists,
    path_join,
    write_file,
)
from dd_license_attribution.artifact_management.artifact_manager import (
    validate_cache_dir,
)
from dd_license_attribution.artifact_management.go_package_resolver import (
    GoPackageResolver,
)
from dd_license_attribution.artifact_management.npm_package_resolver import (
    NpmPackageResolver,
)
from dd_license_attribution.artifact_management.pypi_package_resolver import (
    PypiPackageResolver,
)
from dd_license_attribution.artifact_management.python_env_manager import (
    PyEnvRuntimeError,
    PythonEnvManager,
)
from dd_license_attribution.artifact_management.rust_package_resolver import (
    RustPackageResolver,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    NonAccessibleRepository,
    SourceCodeManager,
    UnauthorizedRepository,
)
from dd_license_attribution.config import JsonConfigParser
from dd_license_attribution.metadata_collector import (
    MetadataCollector,
    ThreePhaseMetadataCollector,
)
from dd_license_attribution.metadata_collector.license_checker import LicenseChecker
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.cleanup_copyright_metadata_strategy import (
    CleanupCopyrightMetadataStrategy,
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
from dd_license_attribution.metadata_collector.strategies.npm_collection_strategy import (
    NpmMetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.override_strategy import (
    OverrideCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.pypi_collection_strategy import (
    PypiMetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.rust_collection_strategy import (
    RustLicenseToolNotInstalledError,
    RustMetadataCollectionStrategy,
    ensure_rust_license_tool_installed,
)
from dd_license_attribution.metadata_collector.strategies.rust_crates_io_collection_strategy import (
    RustCratesIoMetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy import (
    ScanCodeToolkitMetadataCollectionStrategy,
)
from dd_license_attribution.report_generator.report_generator import ReportGenerator
from dd_license_attribution.report_generator.writters.abstract_reporting_writter import (
    ReportingWritter,
)
from dd_license_attribution.report_generator.writters.csv_reporting_writter import (
    CSVReportingWritter,
)
from dd_license_attribution.report_generator.writters.markdown_reporting_writter import (
    MarkdownReportingWritter,
)
from dd_license_attribution.report_generator.writters.spdx_reporting_writter import (
    SPDXReportingWritter,
)
from dd_license_attribution.utils.logging import setup_logging

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")

_OUTPUT_EXTENSIONS = {"csv": "csv", "spdx": "json", "markdown": "md"}
_RESERVED_FILENAME_CHARS = '<>:"/\\|?*'


def _report_document_name(package: str) -> str:
    return package.replace("https://", "").replace("http://", "")


def _report_output_base(package: str) -> str:
    base = "".join(
        "_" if char in _RESERVED_FILENAME_CHARS or ord(char) < 32 else char
        for char in _report_document_name(package)
    ).strip(" .")
    if base:
        return base
    return "sbom"


def _canonical_ecosystem(ecosystem: str | None) -> str | None:
    if ecosystem == "python":
        return "pypi"
    return ecosystem


def _build_writer(
    output_format: str, package: str, ecosystem: str | None
) -> ReportingWritter:
    if output_format == "csv":
        return CSVReportingWritter()

    document_name = _report_document_name(package)
    if output_format == "spdx":
        return SPDXReportingWritter(document_name=document_name)
    if output_format == "markdown":
        return MarkdownReportingWritter(
            document_name=document_name, ecosystem=ecosystem
        )

    raise ValueError(f"Unsupported output format: {output_format}")


def mutually_exclusive_group() -> (
    Callable[[typer.Context, typer.CallbackParam, bool], bool | None]
):
    def callback(
        ctx: typer.Context, param: typer.CallbackParam, value: bool
    ) -> bool | None:
        group: set[str] = ctx.meta.setdefault("mutually_exclusive_group", set())
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
    def callback(
        ctx: typer.Context, param: typer.CallbackParam, value: str | None
    ) -> str | None:
        group: dict[str, Any] = ctx.meta.setdefault("cache_validation_group", {})
        param_dir: set[typer.CallbackParam] = ctx.meta.setdefault(
            "cache_validation_param_dir", set()
        )
        param_ttl: set[typer.CallbackParam] = ctx.meta.setdefault(
            "cache_validation_param_ttl", set()
        )
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


def github_token_conditional_group() -> Callable[
    [typer.Context, typer.CallbackParam, str | bool | None],
    str | bool | None,
]:
    def callback(
        ctx: typer.Context, param: typer.CallbackParam, value: str | bool | None
    ) -> str | bool | None:
        group: dict[str, Any] = ctx.meta.setdefault("github_token_group", {})
        param_token: set[typer.CallbackParam] = ctx.meta.setdefault(
            "github_token_param_token", set()
        )
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


def generate_sbom(
    ctx: typer.Context,
    package: Annotated[
        str,
        typer.Argument(
            help="The package to analyze. A GitHub repository URL, or a package name when --ecosystem is set."
        ),
    ],
    ecosystem: Annotated[
        str | None,
        typer.Option(
            "--ecosystem",
            help="Treat the package argument as a package name in the given ecosystem instead of a GitHub repository URL. Supported: 'npm', 'python' (or 'pypi'), 'go', 'rust'.",
            rich_help_panel="Scanning Options",
        ),
    ] = None,
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
    skip_github_sbom: Annotated[
        bool,
        typer.Option(
            "--no-github-sbom-strategy",
            help="Skip the GitHub SBOM collection strategy.",
            rich_help_panel="Scanning Options",
        ),
    ] = False,
    skip_npm: Annotated[
        bool,
        typer.Option(
            "--no-npm-strategy",
            help="Skip the NPM collection strategy.",
            rich_help_panel="Scanning Options",
        ),
    ] = False,
    skip_rust: Annotated[
        bool,
        typer.Option(
            "--no-rust-strategy",
            help="Skip the Rust collection strategy.",
            rich_help_panel="Scanning Options",
        ),
    ] = False,
    skip_scancode: Annotated[
        bool,
        typer.Option(
            "--no-scancode-strategy",
            help="Skip the ScanCodeToolkit collection strategy.",
            rich_help_panel="Scanning Options",
        ),
    ] = False,
    experimental_strategy: Annotated[
        bool,
        typer.Option(
            "--experimental-strategy",
            help="Enable experimental three-phase dependency discovery (pre-find / find / enrich). Pre-finders run once on the root; finders run in a fixpoint loop; enrichers run once on the stable set. Not yet stable.",
            rich_help_panel="Scanning Options",
        ),
    ] = False,
    cache_dir: Annotated[
        str | None,
        typer.Option(
            "--cache-dir",
            help="Directory to store cached artifacts. If not provided, a temporary directory will be used.",
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
            help="Time to live for cached artifacts in seconds. Default is 86400 (24 hours).",
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
    override_spec: Annotated[
        str | None,
        typer.Option(
            "--override-spec",
            help="A file with a JSON formatted array of override rules to address hard to process or incorrectly extracted dependency information.",
            rich_help_panel="Processing Options",
        ),
    ] = None,
    log_level: Annotated[
        str,
        typer.Option(
            "--log-level",
            help="Set the logging level. Default is INFO.",
            rich_help_panel="Logging Options",
        ),
    ] = "INFO",
    use_mirrors: Annotated[
        str | None,
        typer.Option(
            help="Path to a JSON file containing mirror specifications for repositories."
        ),
    ] = None,
    yarn_subdirs: Annotated[
        list[str] | None,
        typer.Option(
            "--yarn-subdir",
            help="Subdirectory path(s) containing additional yarn.lock files to include in dependency analysis. Can be specified multiple times. Paths are relative to repository root.",
            rich_help_panel="Scanning Options",
        ),
    ] = None,
    output_formats: Annotated[
        list[str] | None,
        typer.Option(
            "--format",
            help="Output format(s). Repeatable. One of: csv, spdx, markdown. Default: csv.",
            rich_help_panel="Output Options",
        ),
    ] = None,
    output_dir: Annotated[
        str | None,
        typer.Option(
            "--output-dir",
            help="Write one file per --format into this directory instead of stdout. Created if missing.",
            rich_help_panel="Output Options",
        ),
    ] = None,
) -> None:
    """
    Generate an SBOM report of third party dependencies for a given
    open source repository.
    """
    if package is None:
        raise click.MissingParameter(param=click.Argument(["package"]))

    if log_level.upper() == "DEBUG":
        setup_logging(logging.DEBUG)
    elif log_level.upper() == "ERROR":
        setup_logging(logging.ERROR)
    elif log_level.upper() == "WARNING":
        setup_logging(logging.WARNING)
    elif log_level.upper() == "INFO":
        setup_logging(logging.INFO)
    else:
        raise ValueError(
            f"Invalid log level. Must be one of: DEBUG, ERROR, WARNING, INFO. Provided: {log_level}"
        )

    if ctx.info_name == "generate-sbom-csv":
        logger.warning(
            "generate-sbom-csv is deprecated; use generate-sbom --format csv instead."
        )
        output_formats = ["csv"]

    requested_output_formats = list(dict.fromkeys(output_formats or ["csv"]))

    supported_output_formats = {"csv", "spdx", "markdown"}
    for requested_output_format in requested_output_formats:
        if requested_output_format not in supported_output_formats:
            raise typer.BadParameter(
                f"Unsupported output format: '{requested_output_format}'. Supported formats: {', '.join(sorted(supported_output_formats))}."
            )

    if output_dir is None and len(requested_output_formats) > 1:
        raise typer.BadParameter("Multiple --format values require --output-dir.")

    supported_ecosystems = ["npm", "python", "pypi", "go", "rust"]
    if ecosystem is not None and ecosystem not in supported_ecosystems:
        raise typer.BadParameter(
            f"Unsupported ecosystem: '{ecosystem}'. Supported ecosystems: {', '.join(supported_ecosystems)}."
        )
    ecosystem = _canonical_ecosystem(ecosystem)

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
        "NpmMetadataCollectionStrategy": True,
        "RustMetadataCollectionStrategy": True,
        "ScanCodeToolkitMetadataCollectionStrategy": True,
        "GitHubRepositoryMetadataCollectionStrategy": True,
        "CleanupCopyrightMetadataStrategy": True,
    }

    if cache_ttl is None:
        cache_ttl = 86400

    with contextlib.ExitStack() as cleanup_stack:

        if cache_dir is None:
            temp_dir = cleanup_stack.enter_context(tempfile.TemporaryDirectory())
            cache_dir = temp_dir

        # Load mirror configurations if provided
        mirrors = None
        if use_mirrors:
            try:
                mirrors = JsonConfigParser.load_mirror_configs(use_mirrors)
            except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
                logger.error(str(e))
                sys.exit(1)

        if debug:
            debug_info = json.loads(debug)
            if "enabled_strategies" in debug_info:
                debug_enabled_strategies = debug_info["enabled_strategies"]
                for strategy in enabled_strategies:
                    if strategy not in debug_enabled_strategies:
                        enabled_strategies[strategy] = False
                logger.debug("Enabled strategies: %s", enabled_strategies)
            else:
                logger.debug(
                    "No strategies enabled - if you wanted to enable strategies, provide a debug object with a list of them in the 'enabled_strategies' key."
                )
                logger.debug(
                    'Example: --debug \'{"enabled_strategies": ["GitHubSbomMetadataCollectionStrategy", "GoPkgMetadataCollectionStrategy"]}\''
                )
                logger.debug(
                    "Available strategies: GitHubSbomMetadataCollectionStrategy, GoPkgMetadataCollectionStrategy, ScanCodeToolkitMetadataCollectionStrategy, GitHubRepositoryMetadataCollectionStrategy"
                )

        if skip_pypi:
            enabled_strategies["PythonPipMetadataCollectionStrategy"] = False

        if skip_gopkg:
            enabled_strategies["GoPkgsMetadataCollectionStrategy"] = False

        if skip_github_sbom:
            enabled_strategies["GitHubSbomMetadataCollectionStrategy"] = False

        if skip_npm:
            enabled_strategies["NpmMetadataCollectionStrategy"] = False

        if skip_rust:
            enabled_strategies["RustMetadataCollectionStrategy"] = False

        if skip_scancode:
            enabled_strategies["ScanCodeToolkitMetadataCollectionStrategy"] = False

        if no_gh_auth or not github_token:
            github_client = GitHub()
        else:
            github_client = GitHub(token=github_token)

        strategies: list[MetadataCollectionStrategy] = []

        try:
            source_code_manager = SourceCodeManager(
                cache_dir, github_client, cache_ttl, mirrors
            )
        except ValueError as e:
            logger.error(str(e))
            sys.exit(1)

        if ecosystem == "go":
            # Go package mode: resolve the Go package and build go-specific pipeline
            # Use a separate temp directory for Go resolution to avoid colliding with
            # SourceCodeManager's cache directory structure (which expects only
            # timestamp-formatted subdirectories).
            go_temp_dir = cleanup_stack.enter_context(tempfile.TemporaryDirectory())
            go_resolver = GoPackageResolver(go_temp_dir)
            local_project_path = go_resolver.resolve_package(package)
            if local_project_path is None:
                logger.error("Failed to resolve Go package: %s", package)
                sys.exit(1)

            if enabled_strategies["GoPkgsMetadataCollectionStrategy"]:
                strategies.append(
                    GoPkgMetadataCollectionStrategy(
                        package,
                        source_code_manager,
                        project_scope,
                        local_project_path=local_project_path,
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
                strategies.append(
                    GitHubRepositoryMetadataCollectionStrategy(
                        github_client, source_code_manager
                    )
                )
        elif ecosystem == "rust":
            if enabled_strategies["RustMetadataCollectionStrategy"]:
                try:
                    ensure_rust_license_tool_installed()
                except RustLicenseToolNotInstalledError as e:
                    logger.error(str(e))
                    sys.exit(1)

            rust_temp_dir = cleanup_stack.enter_context(tempfile.TemporaryDirectory())
            rust_resolver = RustPackageResolver(rust_temp_dir, source_code_manager)
            local_project_path = rust_resolver.resolve_package(package)
            if local_project_path is None:
                logger.error("Failed to resolve Rust crate: %s", package)
                sys.exit(1)

            if enabled_strategies["RustMetadataCollectionStrategy"]:
                strategies.append(
                    RustMetadataCollectionStrategy(
                        package,
                        source_code_manager,
                        project_scope,
                        local_project_path=local_project_path,
                    )
                )
                strategies.append(
                    RustCratesIoMetadataCollectionStrategy(
                        package,
                        source_code_manager,
                        local_project_path=local_project_path,
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
                strategies.append(
                    GitHubRepositoryMetadataCollectionStrategy(
                        github_client, source_code_manager
                    )
                )
        elif ecosystem == "npm":
            # npm-package mode: resolve the npm package and build npm-specific pipeline
            # Use a separate temp directory for npm resolution to avoid colliding with
            # SourceCodeManager's cache directory structure (which expects only
            # timestamp-formatted subdirectories).
            npm_temp_dir = cleanup_stack.enter_context(tempfile.TemporaryDirectory())
            resolver = NpmPackageResolver(npm_temp_dir)
            local_project_path = resolver.resolve_package(package)
            if local_project_path is None:
                logger.error("Failed to resolve npm package: %s", package)
                sys.exit(1)

            if enabled_strategies["NpmMetadataCollectionStrategy"]:
                strategies.append(
                    NpmMetadataCollectionStrategy(
                        package,
                        source_code_manager,
                        project_scope,
                        yarn_subdirs=yarn_subdirs or [],
                        local_project_path=local_project_path,
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
                strategies.append(
                    GitHubRepositoryMetadataCollectionStrategy(
                        github_client, source_code_manager
                    )
                )
        elif ecosystem == "pypi":
            # PyPI package mode: resolve the PyPI package and build pypi-specific pipeline
            pypi_temp_dir = cleanup_stack.enter_context(tempfile.TemporaryDirectory())
            pypi_resolver = PypiPackageResolver(pypi_temp_dir)
            local_project_path = pypi_resolver.resolve_package(package)
            if local_project_path is None:
                logger.error("Failed to resolve PyPI package: %s", package)
                sys.exit(1)

            python_env_manager = PythonEnvManager(cache_dir, cache_ttl)

            if enabled_strategies["PythonPipMetadataCollectionStrategy"]:
                strategies.append(
                    PypiMetadataCollectionStrategy(
                        package,
                        source_code_manager,
                        python_env_manager,
                        project_scope,
                        local_project_path=local_project_path,
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
                strategies.append(
                    GitHubRepositoryMetadataCollectionStrategy(
                        github_client, source_code_manager
                    )
                )
        else:
            # Standard GitHub repository mode
            if enabled_strategies["GitHubSbomMetadataCollectionStrategy"]:
                strategies.append(
                    GitHubSbomMetadataCollectionStrategy(
                        github_client, source_code_manager, project_scope
                    )
                )

            if enabled_strategies["GoPkgsMetadataCollectionStrategy"]:
                strategies.append(
                    GoPkgMetadataCollectionStrategy(
                        package, source_code_manager, project_scope
                    )
                )

            python_env_manager = PythonEnvManager(cache_dir, cache_ttl)

            if enabled_strategies["PythonPipMetadataCollectionStrategy"]:
                strategies.append(
                    PypiMetadataCollectionStrategy(
                        package, source_code_manager, python_env_manager, project_scope
                    )
                )

            if enabled_strategies["NpmMetadataCollectionStrategy"]:
                strategies.append(
                    NpmMetadataCollectionStrategy(
                        package,
                        source_code_manager,
                        project_scope,
                        yarn_subdirs=yarn_subdirs or [],
                    )
                )

            if enabled_strategies["RustMetadataCollectionStrategy"]:
                strategies.append(
                    RustMetadataCollectionStrategy(
                        package, source_code_manager, project_scope
                    )
                )
                strategies.append(
                    RustCratesIoMetadataCollectionStrategy(
                        package,
                        source_code_manager,
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
                strategies.append(
                    GitHubRepositoryMetadataCollectionStrategy(
                        github_client, source_code_manager
                    )
                )

        override_strategy = None
        if override_spec:
            try:
                override_rules = JsonConfigParser.load_override_configs(override_spec)
                override_strategy = OverrideCollectionStrategy(override_rules)
            except (FileNotFoundError, json.JSONDecodeError, ValueError) as e:
                logger.error(str(e))
                sys.exit(1)

        if experimental_strategy:
            # Three-phase path:
            #   pre_finders — run once on the root (strategies that already do full
            #                 transitive closure, e.g. GitHub SBOM; must not iterate)
            #   finders     — fixpoint loop (ecosystem finders, one level per call)
            #   enrichers   — run once on the complete dep set
            # Override interleaving is handled internally by ThreePhaseMetadataCollector.
            _PRE_FINDER_STRATEGY_NAMES = {
                "GitHubSbomMetadataCollectionStrategy",
            }
            _FINDER_STRATEGY_NAMES = {
                "GoPkgMetadataCollectionStrategy",
                "PypiMetadataCollectionStrategy",
                "NpmMetadataCollectionStrategy",
            }
            pre_finders = [
                s
                for s in strategies
                if s.__class__.__name__ in _PRE_FINDER_STRATEGY_NAMES
            ]
            finders = [
                s for s in strategies if s.__class__.__name__ in _FINDER_STRATEGY_NAMES
            ]
            enrichers = [
                s
                for s in strategies
                if s.__class__.__name__
                not in _PRE_FINDER_STRATEGY_NAMES | _FINDER_STRATEGY_NAMES
            ]
            if enabled_strategies["CleanupCopyrightMetadataStrategy"]:
                enrichers.append(CleanupCopyrightMetadataStrategy())
            metadata_collector: MetadataCollector | ThreePhaseMetadataCollector = (
                ThreePhaseMetadataCollector(
                    pre_finders=pre_finders,
                    finders=finders,
                    enrichers=enrichers,
                    override_strategy=override_strategy,
                )
            )
        else:
            # Existing linear cascade path.
            if override_strategy is not None:
                # interleave overrides before every strategy so they fire as
                # soon as dependencies are added to the closure
                for i in range(len(strategies) - 1, -1, -1):
                    strategies.insert(i, override_strategy)
            if enabled_strategies["CleanupCopyrightMetadataStrategy"]:
                strategies.append(CleanupCopyrightMetadataStrategy())
            metadata_collector = MetadataCollector(strategies)
        try:
            metadata = metadata_collector.collect_metadata(package)
        except (NonAccessibleRepository, UnauthorizedRepository) as e:
            logger.error(str(e))
            sys.exit(1)
        except PyEnvRuntimeError as e:
            logger.error(str(e))
            logger.error(
                "This error can be bypassed by skipping the PyPI strategy (--no-pypi-strategy)."
            )
            logger.error(
                "When skipping this strategy, the tool will not try to extract dependencies or metadata from PyPI."
            )
            sys.exit(1)
        except RustLicenseToolNotInstalledError as e:
            logger.error(str(e))
            sys.exit(1)

        checker = LicenseChecker(
            cli_config.default_config.preset_cautionary_licenses,
            cli_config.default_config.recognized_licenses,
        )
        checker.check_cautionary_licenses(metadata)
        checker.check_spdx_ids(metadata)

        if output_dir is None:
            reporting_writter = _build_writer(
                requested_output_formats[0], package, ecosystem
            )
            reporter = ReportGenerator(reporting_writter)
            output = reporter.generate_report(metadata)

            # Output report to STDOUT for piping/redirection (e.g., ddla generate-sbom URL > output.csv)
            # This is intentional CLI output, not logging. Do not replace with logger.info()
            print(output, end="")
        else:
            create_dirs(output_dir)
            report_base = _report_output_base(package)
            for requested_output_format in requested_output_formats:
                reporting_writter = _build_writer(
                    requested_output_format, package, ecosystem
                )
                reporter = ReportGenerator(reporting_writter)
                output = reporter.generate_report(metadata)
                output_path = path_join(
                    output_dir,
                    f"{report_base}.{_OUTPUT_EXTENSIONS[requested_output_format]}",
                )
                write_file(output_path, output)
                logger.info(
                    "Wrote %s report to %s", requested_output_format, output_path
                )
    if override_strategy is not None and len(override_strategy.unused_targets()) != 0:
        logger.warning("Not all targets in the override spec file were used.")
        logger.warning(
            "Unused targets: %s. Consider removing them.",
            override_strategy.unused_targets(),
        )


def generate_sbom_csv(**kwargs: Any) -> None:
    if kwargs.get("package") is None:
        raise click.MissingParameter(param=click.Argument(["package"]))
    kwargs.pop("output_format", None)
    kwargs["output_formats"] = ["csv"]
    generate_sbom(**kwargs)


def _generate_sbom_csv_signature() -> inspect.Signature:
    signature = inspect.signature(generate_sbom)
    parameters = [
        _clone_signature_parameter(parameter)
        for parameter in signature.parameters.values()
        if parameter.name != "output_formats"
    ]
    return signature.replace(parameters=parameters)


def _clone_signature_parameter(parameter: inspect.Parameter) -> inspect.Parameter:
    annotation = parameter.annotation
    if get_origin(annotation) is Annotated:
        annotated_args = get_args(annotation)
        metadata = tuple(copy.copy(item) for item in annotated_args[1:])
        annotation = Annotated[annotated_args[0], *metadata]
    return parameter.replace(annotation=annotation)


setattr(generate_sbom_csv, "__signature__", _generate_sbom_csv_signature())
