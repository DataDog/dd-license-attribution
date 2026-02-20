# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import os
from unittest.mock import Mock, patch

import pytest
from typer.testing import CliRunner

from dd_license_attribution.cli.main_cli import app

runner = CliRunner()


def test_basic_run() -> None:
    result = runner.invoke(
        app,
        ["generate-sbom-csv", "test", "--no-gh-auth"],
        color=False,
    )
    assert result.exit_code == 0


def test_no_github_auth() -> None:
    # Save the original environment variable if it there
    original_github_token = os.environ.pop("GITHUB_TOKEN", None)

    try:
        result = runner.invoke(app, ["generate-sbom-csv", "test"], color=False)
        assert result.exit_code == 2
        assert "Invalid value for '--github-token'" in result.output_bytes.decode(
            "utf-8", "ignore"
        )
    finally:
        # Restore the original environment variable
        if original_github_token is not None:
            os.environ["GITHUB_TOKEN"] = original_github_token


def test_github_auth_param() -> None:
    result = runner.invoke(
        app,
        ["generate-sbom-csv", "test", "--github-token=12345"],
        color=False,
    )
    assert result.exit_code == 0


def test_github_auth_env() -> None:
    result = runner.invoke(
        app,
        ["generate-sbom-csv", "test"],
        env={"GITHUB_TOKEN": "12345"},
        color=False,
    )
    assert result.exit_code == 0


@pytest.mark.parametrize(
    "arg, strategy_name",
    [
        (["--no-pypi-strategy"], "PythonPipMetadataCollectionStrategy"),
        (["--no-gopkg-strategy"], "GoPkgsMetadataCollectionStrategy"),
        (["--no-github-sbom-strategy"], "GitHubSbomMetadataCollectionStrategy"),
        (["--no-scancode-strategy"], "ScanCodeToolkitMetadataCollectionStrategy"),
    ],
)
@patch("dd_license_attribution.cli.generate_sbom_csv_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.MetadataCollector")
def test_skip_strategies_options(
    mock_metadata_collector: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    arg: list[str],
    strategy_name: str,
) -> None:
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )

    args = ["--no-gh-auth"] + arg
    result = runner.invoke(
        app,
        ["generate-sbom-csv", "https://github.com/org/repo"] + args,
    )
    assert result.exit_code == 0

    strategies = mock_metadata_collector.call_args[0][0]

    strategy_classes = [strategy.__class__.__name__ for strategy in strategies]
    assert strategy_name not in strategy_classes


@patch("dd_license_attribution.cli.generate_sbom_csv_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.MetadataCollector")
def test_skip_all_strategies(
    mock_metadata_collector: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
) -> None:
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )

    result = runner.invoke(
        app,
        [
            "generate-sbom-csv",
            "https://github.com/org/repo",
            "--no-gh-auth",
            "--no-pypi-strategy",
            "--no-gopkg-strategy",
            "--no-github-sbom-strategy",
            "--no-scancode-strategy",
        ],
    )
    assert result.exit_code == 0

    strategies = mock_metadata_collector.call_args[0][0]
    strategy_classes = [strategy.__class__.__name__ for strategy in strategies]

    assert "PythonPipMetadataCollectionStrategy" not in strategy_classes
    assert "GoPkgsMetadataCollectionStrategy" not in strategy_classes
    assert "GitHubSbomMetadataCollectionStrategy" not in strategy_classes
    assert "ScanCodeToolkitMetadataCollectionStrategy" not in strategy_classes


def test_missing_package() -> None:
    result = runner.invoke(app, ["generate-sbom-csv"], color=False)
    assert result.exit_code == 2
    assert "Missing argument 'PACKAGE'." in result.stderr


@patch("dd_license_attribution.config.json_config_parser.open_file")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.MetadataCollector")
def test_use_mirrors_invalid_json(
    mock_metadata_collector: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_open_file: Mock,
) -> None:
    mock_open_file.return_value = "invalid json"
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    result = runner.invoke(
        app,
        [
            "generate-sbom-csv",
            "--use-mirrors=test.json",
            "--no-gh-auth",
            "--log-level=DEBUG",
            "--",
            "https://github.com/DataDog/test",
        ],
        color=False,
    )
    assert result.exit_code == 1
    assert "Invalid JSON in mirror configuration file: test.json" in result.stderr


@patch("dd_license_attribution.config.json_config_parser.open_file")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.MetadataCollector")
def test_use_mirrors_valid_config(
    mock_metadata_collector: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_open_file: Mock,
) -> None:
    mock_open_file.return_value = """[
        {
            "original_url": "https://github.com/DataDog/test",
            "mirror_url": "https://github.com/mirror/test",
            "ref_mapping": {
                "branch:main": "branch:development"
            }
        }
    ]"""
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "test",
        None,
    )
    result = runner.invoke(
        app,
        [
            "generate-sbom-csv",
            "--use-mirrors=test.json",
            "--no-gh-auth",
            "--log-level=DEBUG",
            "--",
            "test",
        ],
        color=False,
    )
    assert result.exit_code == 0


@patch("dd_license_attribution.cli.generate_sbom_csv_command.NpmPackageResolver")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.MetadataCollector")
def test_ecosystem_npm_builds_correct_strategy_pipeline(
    mock_metadata_collector: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_npm_resolver: Mock,
) -> None:
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    mock_npm_resolver.return_value.resolve_package.return_value = (
        "/tmp/npm_resolve/express"
    )

    result = runner.invoke(
        app,
        [
            "generate-sbom-csv",
            "express",
            "--ecosystem",
            "npm",
            "--no-gh-auth",
        ],
    )
    assert result.exit_code == 0

    strategies = mock_metadata_collector.call_args[0][0]
    strategy_classes = [strategy.__class__.__name__ for strategy in strategies]

    # npm ecosystem pipeline should include these strategies
    assert "NpmMetadataCollectionStrategy" in strategy_classes
    assert "ScanCodeToolkitMetadataCollectionStrategy" in strategy_classes
    assert "GitHubRepositoryMetadataCollectionStrategy" in strategy_classes
    assert "CleanupCopyrightMetadataStrategy" in strategy_classes

    # npm ecosystem pipeline should NOT include these strategies
    assert "GitHubSbomMetadataCollectionStrategy" not in strategy_classes
    assert "GoPkgMetadataCollectionStrategy" not in strategy_classes
    assert "PypiMetadataCollectionStrategy" not in strategy_classes

    # Verify NpmPackageResolver was called
    mock_npm_resolver.assert_called_once()
    mock_npm_resolver.return_value.resolve_package.assert_called_once_with("express")


def test_ecosystem_invalid_value_rejected() -> None:
    result = runner.invoke(
        app,
        [
            "generate-sbom-csv",
            "some-package",
            "--ecosystem",
            "invalid",
            "--no-gh-auth",
        ],
        color=False,
    )
    assert result.exit_code != 0
    assert (
        "Unsupported ecosystem" in result.stderr
        or "Unsupported ecosystem" in result.output
    )


@patch("dd_license_attribution.cli.generate_sbom_csv_command.NpmPackageResolver")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.MetadataCollector")
def test_ecosystem_npm_resolver_failure_exits(
    mock_metadata_collector: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_npm_resolver: Mock,
) -> None:
    mock_npm_resolver.return_value.resolve_package.return_value = None

    result = runner.invoke(
        app,
        [
            "generate-sbom-csv",
            "nonexistent-package",
            "--ecosystem",
            "npm",
            "--no-gh-auth",
        ],
    )
    assert result.exit_code == 1
    mock_npm_resolver.return_value.resolve_package.assert_called_once_with(
        "nonexistent-package"
    )


@patch("dd_license_attribution.cli.generate_sbom_csv_command.NpmPackageResolver")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_csv_command.MetadataCollector")
def test_ecosystem_npm_passes_local_project_path_to_strategy(
    mock_metadata_collector: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_npm_resolver: Mock,
) -> None:
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    mock_npm_resolver.return_value.resolve_package.return_value = (
        "/tmp/npm_resolve/express"
    )

    result = runner.invoke(
        app,
        [
            "generate-sbom-csv",
            "express",
            "--ecosystem",
            "npm",
            "--no-gh-auth",
        ],
    )
    assert result.exit_code == 0

    strategies = mock_metadata_collector.call_args[0][0]
    npm_strategy = next(
        s for s in strategies if s.__class__.__name__ == "NpmMetadataCollectionStrategy"
    )
    assert npm_strategy.local_project_path == "/tmp/npm_resolve/express"


# NOTE: test_cache_ttl_without_cache_dir and test_transitive_root_same_time must
# come last because the cache_validation_callback closure retains mutable state
# across test invocations, which can corrupt subsequent tests.


def test_cache_ttl_without_cache_dir() -> None:
    result = runner.invoke(
        app,
        ["generate-sbom-csv", "test", "--cache-ttl=10"],
        color=False,
    )
    assert result.exit_code == 2
    assert "Invalid value for '--cache-ttl'" in result.stderr


def test_transitive_root_same_time() -> None:
    result = runner.invoke(
        app,
        [
            "generate-sbom-csv",
            "test",
            "--only-transitive-dependencies",
            "--only-root-project",
        ],
        color=False,
    )
    assert result.exit_code == 2
    assert "Invalid value for '--only-root-project'" in result.stderr
