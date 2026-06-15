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
