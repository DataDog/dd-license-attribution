# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from unittest.mock import ANY, Mock, call, patch

from typer.testing import CliRunner

from dd_license_attribution.cli.main_cli import app

runner = CliRunner()


@patch("dd_license_attribution.cli.generate_sbom_command.ThreePhaseMetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
def test_experimental_strategy_uses_three_phase_collector(
    mock_csv: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_metadata_collector: Mock,
    mock_three_phase_collector: Mock,
) -> None:
    mock_three_phase_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )
    mock_csv.return_value.write.return_value = ""

    result = runner.invoke(
        app,
        [
            "generate-sbom",
            "https://github.com/org/repo",
            "--no-gh-auth",
            "--experimental-strategy",
        ],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0, result.output
    mock_three_phase_collector.assert_called_once()
    mock_metadata_collector.assert_not_called()


@patch("dd_license_attribution.cli.generate_sbom_command.ThreePhaseMetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
def test_experimental_github_repo_puts_github_sbom_in_pre_finders_not_finders(
    mock_csv: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_metadata_collector: Mock,
    mock_three_phase_collector: Mock,
) -> None:
    mock_three_phase_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )
    mock_csv.return_value.write.return_value = ""

    result = runner.invoke(
        app,
        [
            "generate-sbom",
            "https://github.com/org/repo",
            "--no-gh-auth",
            "--experimental-strategy",
        ],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0, result.output
    _, kwargs = mock_three_phase_collector.call_args
    pre_finder_classes = [f.__class__.__name__ for f in kwargs["pre_finders"]]
    finder_classes = [f.__class__.__name__ for f in kwargs["finders"]]
    assert "GitHubSbomMetadataCollectionStrategy" in pre_finder_classes
    assert "GitHubSbomMetadataCollectionStrategy" not in finder_classes


@patch("dd_license_attribution.cli.generate_sbom_command.ThreePhaseMetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
def test_without_experimental_strategy_uses_metadata_collector(
    mock_csv: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_metadata_collector: Mock,
    mock_three_phase_collector: Mock,
) -> None:
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )
    mock_csv.return_value.write.return_value = ""

    result = runner.invoke(
        app,
        ["generate-sbom", "https://github.com/org/repo", "--no-gh-auth"],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0, result.output
    mock_metadata_collector.assert_called_once()
    mock_three_phase_collector.assert_not_called()


@patch("dd_license_attribution.cli.generate_sbom_command.ThreePhaseMetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
def test_experimental_strategy_no_scancode_excludes_it_from_enrichers(
    mock_csv: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_metadata_collector: Mock,
    mock_three_phase_collector: Mock,
) -> None:
    mock_three_phase_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )
    mock_csv.return_value.write.return_value = ""

    result = runner.invoke(
        app,
        [
            "generate-sbom",
            "https://github.com/org/repo",
            "--no-gh-auth",
            "--experimental-strategy",
            "--no-scancode-strategy",
        ],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0, result.output
    _, kwargs = mock_three_phase_collector.call_args
    enricher_classes = [e.__class__.__name__ for e in kwargs["enrichers"]]
    assert "ScanCodeToolkitMetadataCollectionStrategy" not in enricher_classes


@patch("dd_license_attribution.cli.generate_sbom_command.PypiPackageResolver")
@patch("dd_license_attribution.cli.generate_sbom_command.ThreePhaseMetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
def test_experimental_ecosystem_python_puts_pypi_in_finders(
    mock_csv: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_metadata_collector: Mock,
    mock_three_phase_collector: Mock,
    mock_pypi_resolver: Mock,
) -> None:
    mock_three_phase_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "pypi:requests",
        None,
    )
    mock_pypi_resolver.return_value.resolve_package.return_value = "/tmp/fake-pypi"
    mock_csv.return_value.write.return_value = ""

    result = runner.invoke(
        app,
        [
            "generate-sbom",
            "requests",
            "--no-gh-auth",
            "--experimental-strategy",
            "--ecosystem",
            "python",
        ],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0, result.output
    mock_three_phase_collector.assert_called_once()
    _, kwargs = mock_three_phase_collector.call_args
    finder_classes = [f.__class__.__name__ for f in kwargs["finders"]]
    assert "PypiMetadataCollectionStrategy" in finder_classes
    assert "GoPkgMetadataCollectionStrategy" not in finder_classes
    assert "GitHubSbomMetadataCollectionStrategy" not in finder_classes
    assert "NpmMetadataCollectionStrategy" not in finder_classes


@patch("dd_license_attribution.cli.generate_sbom_command.GoPackageResolver")
@patch("dd_license_attribution.cli.generate_sbom_command.ThreePhaseMetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
def test_experimental_ecosystem_go_puts_gopkg_in_finders(
    mock_csv: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_metadata_collector: Mock,
    mock_three_phase_collector: Mock,
    mock_go_resolver: Mock,
) -> None:
    mock_three_phase_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "go:github.com/foo/bar",
        None,
    )
    mock_go_resolver.return_value.resolve_package.return_value = "/tmp/fake-go"
    mock_csv.return_value.write.return_value = ""

    result = runner.invoke(
        app,
        [
            "generate-sbom",
            "github.com/foo/bar",
            "--no-gh-auth",
            "--experimental-strategy",
            "--ecosystem",
            "go",
        ],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0, result.output
    mock_three_phase_collector.assert_called_once()
    _, kwargs = mock_three_phase_collector.call_args
    finder_classes = [f.__class__.__name__ for f in kwargs["finders"]]
    assert "GoPkgMetadataCollectionStrategy" in finder_classes
    assert "PypiMetadataCollectionStrategy" not in finder_classes
    assert "GitHubSbomMetadataCollectionStrategy" not in finder_classes
    assert "NpmMetadataCollectionStrategy" not in finder_classes


@patch("dd_license_attribution.cli.generate_sbom_command.NpmPackageResolver")
@patch("dd_license_attribution.cli.generate_sbom_command.ThreePhaseMetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
def test_experimental_ecosystem_npm_puts_npm_in_finders(
    mock_csv: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_metadata_collector: Mock,
    mock_three_phase_collector: Mock,
    mock_npm_resolver: Mock,
) -> None:
    mock_three_phase_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "npm:lodash",
        None,
    )
    mock_npm_resolver.return_value.resolve_package.return_value = "/tmp/fake-npm"
    mock_csv.return_value.write.return_value = ""

    result = runner.invoke(
        app,
        [
            "generate-sbom",
            "lodash",
            "--no-gh-auth",
            "--experimental-strategy",
            "--ecosystem",
            "npm",
        ],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0, result.output
    mock_three_phase_collector.assert_called_once()
    _, kwargs = mock_three_phase_collector.call_args
    finder_classes = [f.__class__.__name__ for f in kwargs["finders"]]
    assert "NpmMetadataCollectionStrategy" in finder_classes
    assert "PypiMetadataCollectionStrategy" not in finder_classes
    assert "GoPkgMetadataCollectionStrategy" not in finder_classes
    assert "GitHubSbomMetadataCollectionStrategy" not in finder_classes


@patch("dd_license_attribution.cli.generate_sbom_command.PypiPackageResolver")
@patch("dd_license_attribution.cli.generate_sbom_command.ThreePhaseMetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
def test_experimental_ecosystem_python_no_pypi_strategy_yields_empty_finders(
    mock_csv: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
    mock_metadata_collector: Mock,
    mock_three_phase_collector: Mock,
    mock_pypi_resolver: Mock,
) -> None:
    mock_three_phase_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "pypi:requests",
        None,
    )
    mock_pypi_resolver.return_value.resolve_package.return_value = "/tmp/fake-pypi"
    mock_csv.return_value.write.return_value = ""

    result = runner.invoke(
        app,
        [
            "generate-sbom",
            "requests",
            "--no-gh-auth",
            "--experimental-strategy",
            "--ecosystem",
            "python",
            "--no-pypi-strategy",
        ],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0, result.output
    mock_three_phase_collector.assert_called_once()
    _, kwargs = mock_three_phase_collector.call_args
    finder_classes = [f.__class__.__name__ for f in kwargs["finders"]]
    assert finder_classes == []


def test_root_help_hides_deprecated_generate_sbom_csv_alias() -> None:
    result = runner.invoke(app, [], color=False)

    assert result.exit_code == 2
    assert "generate-sbom" in result.stdout
    assert "Generate an SBOM report" in result.stdout
    assert "generate-sbom-csv" not in result.stdout


@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.SPDXReportingWritter")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
def test_generate_sbom_defaults_to_csv(
    mock_metadata_collector: Mock,
    mock_csv_reporting_writter: Mock,
    mock_spdx_reporting_writter: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
) -> None:
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )
    mock_csv_reporting_writter.return_value.write.return_value = "csv-output"

    result = runner.invoke(
        app,
        ["generate-sbom", "https://github.com/org/repo", "--no-gh-auth"],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0
    assert result.stdout == "csv-output"
    mock_github.assert_called_once_with()
    mock_source_code_manager.assert_called_once_with(
        ANY, mock_github.return_value, 86400, None
    )
    mock_source_code_manager.return_value.get_canonical_urls.assert_has_calls(
        [
            call("https://github.com/org/repo"),
            call("https://github.com/org/repo"),
            call("https://github.com/org/repo"),
        ]
    )
    mock_python_env_manager.assert_called_once_with(ANY, 86400)
    mock_metadata_collector.assert_called_once_with(ANY)
    mock_metadata_collector.return_value.collect_metadata.assert_called_once_with(
        "https://github.com/org/repo"
    )
    mock_csv_reporting_writter.assert_called_once_with()
    mock_csv_reporting_writter.return_value.write.assert_called_once_with([])
    mock_spdx_reporting_writter.assert_not_called()


@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.SPDXReportingWritter")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
def test_generate_sbom_supports_spdx_format(
    mock_metadata_collector: Mock,
    mock_csv_reporting_writter: Mock,
    mock_spdx_reporting_writter: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
) -> None:
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )
    mock_spdx_reporting_writter.return_value.write.return_value = "spdx-output"

    result = runner.invoke(
        app,
        [
            "generate-sbom",
            "https://github.com/org/repo",
            "--no-gh-auth",
            "--format",
            "spdx",
        ],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0
    assert result.stdout == "spdx-output"
    mock_github.assert_called_once_with()
    mock_source_code_manager.assert_called_once_with(
        ANY, mock_github.return_value, 86400, None
    )
    mock_source_code_manager.return_value.get_canonical_urls.assert_has_calls(
        [
            call("https://github.com/org/repo"),
            call("https://github.com/org/repo"),
            call("https://github.com/org/repo"),
        ]
    )
    mock_python_env_manager.assert_called_once_with(ANY, 86400)
    mock_metadata_collector.assert_called_once_with(ANY)
    mock_metadata_collector.return_value.collect_metadata.assert_called_once_with(
        "https://github.com/org/repo"
    )
    mock_spdx_reporting_writter.assert_called_once_with(
        document_name="github.com/org/repo"
    )
    mock_spdx_reporting_writter.return_value.write.assert_called_once_with([])
    mock_csv_reporting_writter.assert_not_called()


def test_generate_sbom_rejects_unknown_format() -> None:
    result = runner.invoke(
        app,
        [
            "generate-sbom",
            "https://github.com/org/repo",
            "--no-gh-auth",
            "--format",
            "yaml",
        ],
        color=False,
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code != 0
    assert "Unsupported output format: 'yaml'" in result.stderr


def test_generate_sbom_missing_package_with_option_shows_usage_error() -> None:
    result = runner.invoke(
        app,
        ["generate-sbom", "--no-gh-auth"],
        color=False,
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 2
    assert "Missing argument 'PACKAGE'." in result.stderr
    assert "Traceback" not in result.stderr


@patch("dd_license_attribution.cli.generate_sbom_command.GitHub")
@patch("dd_license_attribution.cli.generate_sbom_command.SourceCodeManager")
@patch("dd_license_attribution.cli.generate_sbom_command.PythonEnvManager")
@patch("dd_license_attribution.cli.generate_sbom_command.SPDXReportingWritter")
@patch("dd_license_attribution.cli.generate_sbom_command.CSVReportingWritter")
@patch("dd_license_attribution.cli.generate_sbom_command.MetadataCollector")
def test_generate_sbom_csv_deprecated_alias_uses_csv(
    mock_metadata_collector: Mock,
    mock_csv_reporting_writter: Mock,
    mock_spdx_reporting_writter: Mock,
    mock_python_env_manager: Mock,
    mock_source_code_manager: Mock,
    mock_github: Mock,
) -> None:
    mock_metadata_collector.return_value.collect_metadata.return_value = []
    mock_source_code_manager.return_value.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )
    mock_csv_reporting_writter.return_value.write.return_value = "csv-output"

    result = runner.invoke(
        app,
        ["generate-sbom-csv", "https://github.com/org/repo", "--no-gh-auth"],
        env={"GITHUB_TOKEN": ""},
    )

    assert result.exit_code == 0
    assert result.stdout == "csv-output"
    assert "generate-sbom-csv is deprecated" in result.stderr
    mock_github.assert_called_once_with()
    mock_source_code_manager.assert_called_once_with(
        ANY, mock_github.return_value, 86400, None
    )
    mock_source_code_manager.return_value.get_canonical_urls.assert_has_calls(
        [
            call("https://github.com/org/repo"),
            call("https://github.com/org/repo"),
            call("https://github.com/org/repo"),
        ]
    )
    mock_python_env_manager.assert_called_once_with(ANY, 86400)
    mock_metadata_collector.assert_called_once_with(ANY)
    mock_metadata_collector.return_value.collect_metadata.assert_called_once_with(
        "https://github.com/org/repo"
    )
    mock_csv_reporting_writter.assert_called_once_with()
    mock_csv_reporting_writter.return_value.write.assert_called_once_with([])
    mock_spdx_reporting_writter.assert_not_called()
