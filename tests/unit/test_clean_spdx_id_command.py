# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

# Unit tests for clean-spdx-id CLI command

from typing import Any
from unittest.mock import Mock, patch

from typer.testing import CliRunner

from dd_license_attribution.cli.main_cli import app
from dd_license_attribution.metadata_collector.metadata import Metadata

runner = CliRunner()


class TestCleanSPDXIdCommand:
    """Test clean-spdx-id CLI command."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        # Sample metadata objects
        self.sample_metadata = [
            Metadata(
                name="test-package",
                origin="https://github.com/test/package",
                local_src_path=None,
                version=None,
                license=["MIT"],
                copyright=["Copyright 2024"],
            )
        ]

        self.cleaned_csv = """"component","origin","license","copyright"
"test-package","https://github.com/test/package","['MIT']","['Copyright 2024']"
"""

        self.changes_no_modifications = {
            "total_rows": 1,
            "modified_count": 0,
            "changes": [],
        }

        self.changes_with_modifications = {
            "total_rows": 1,
            "modified_count": 1,
            "changes": [
                {
                    "row": 0,
                    "component": "test-package",
                    "origin": "https://github.com/test/package",
                    "original": "BSD 3-Clause License...",
                    "converted": "BSD-3-Clause",
                }
            ],
        }

    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_success_no_changes(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
    ) -> None:
        """Test successful execution with no changes needed."""
        # Mock Path objects
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner
        mock_cleaner = Mock()
        mock_cleaner.clean_metadata.return_value = (
            self.sample_metadata,
            self.changes_no_modifications,
        )
        mock_spdx_cleaner_class.return_value = mock_cleaner

        # Mock CSV writer
        mock_csv_writer = Mock()
        mock_csv_writer.write.return_value = self.cleaned_csv
        mock_csv_writer_class.return_value = mock_csv_writer

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--silent",
            ],
        )

        assert result.exit_code == 0
        mock_create_llm_client.assert_called_once_with("openai", "test-key", None)
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert call_args[1]["change_callback"] is None
        mock_csv_writer.write.assert_called_once_with(self.sample_metadata)
        mock_write_file.assert_called_once()

    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_with_anthropic_provider(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
    ) -> None:
        """Test using Anthropic as LLM provider."""
        # Mock Path objects
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner
        mock_cleaner = Mock()
        mock_cleaner.clean_metadata.return_value = (
            self.sample_metadata,
            self.changes_no_modifications,
        )
        mock_spdx_cleaner_class.return_value = mock_cleaner

        # Mock CSV writer
        mock_csv_writer = Mock()
        mock_csv_writer.write.return_value = self.cleaned_csv
        mock_csv_writer_class.return_value = mock_csv_writer

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--llm-provider",
                "anthropic",
                "--api-key",
                "test-key",
                "--silent",
            ],
        )

        assert result.exit_code == 0
        mock_create_llm_client.assert_called_once_with("anthropic", "test-key", None)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_with_custom_model(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
    ) -> None:
        """Test using custom model."""
        # Mock Path objects
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner
        mock_cleaner = Mock()
        mock_cleaner.clean_metadata.return_value = (
            self.sample_metadata,
            self.changes_no_modifications,
        )
        mock_spdx_cleaner_class.return_value = mock_cleaner

        # Mock CSV writer
        mock_csv_writer = Mock()
        mock_csv_writer.write.return_value = self.cleaned_csv
        mock_csv_writer_class.return_value = mock_csv_writer

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--model",
                "gpt-3.5-turbo",
                "--silent",
            ],
        )

        assert result.exit_code == 0
        mock_create_llm_client.assert_called_once_with(
            "openai", "test-key", "gpt-3.5-turbo"
        )

    @patch("dd_license_attribution.cli.clean_spdx_id_command.os.environ")
    def test_clean_spdx_id_missing_api_key(self, mock_environ: Mock) -> None:
        """Test error handling when API key is missing."""
        # Ensure no API keys are available from environment
        mock_environ.get.return_value = None

        result = runner.invoke(
            app,
            ["clean-spdx-id", "input.csv", "output.csv", "--silent"],
        )

        assert result.exit_code == 1
        assert "API key is required" in result.stderr

    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    def test_clean_spdx_id_input_file_not_found(self, mock_path: Mock) -> None:
        """Test error handling when input file doesn't exist."""
        mock_input_path = Mock()
        mock_input_path.exists.return_value = False
        mock_path.return_value = mock_input_path

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "nonexistent.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--silent",
            ],
        )

        assert result.exit_code == 1
        assert "Input CSV file not found" in result.stderr

    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_with_modifications_silent_mode(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
    ) -> None:
        """Test execution with modifications in silent mode."""
        # Mock Path objects
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner
        mock_cleaner = Mock()
        mock_cleaner.clean_metadata.return_value = (
            self.sample_metadata,
            self.changes_with_modifications,
        )
        mock_spdx_cleaner_class.return_value = mock_cleaner

        # Mock CSV writer
        mock_csv_writer = Mock()
        mock_csv_writer.write.return_value = self.cleaned_csv
        mock_csv_writer_class.return_value = mock_csv_writer

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--silent",
            ],
        )

        assert result.exit_code == 0
        mock_write_file.assert_called_once()

    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.typer.confirm")
    def test_clean_spdx_id_with_modifications_prompting_mode_accept(
        self,
        mock_confirm: Mock,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
    ) -> None:
        """Test execution with modifications in prompting mode (user accepts)."""
        # Mock Path objects
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner with callback simulation
        mock_cleaner = Mock()

        def mock_clean_metadata(
            metadata_list: list[Metadata],
            change_callback: Any = None,
        ) -> tuple[list[Metadata], dict[str, Any]]:
            # If callback is provided, call it for each change
            if change_callback:
                changes_list: list[dict[str, Any]] = self.changes_with_modifications.get("changes", [])  # type: ignore[assignment]
                for change in changes_list:
                    if not change_callback(change):
                        # User rejected, return no changes
                        return (
                            metadata_list,
                            {"total_rows": 1, "modified_count": 0, "changes": []},
                        )
            return (metadata_list, self.changes_with_modifications)

        mock_cleaner.clean_metadata.side_effect = mock_clean_metadata
        mock_spdx_cleaner_class.return_value = mock_cleaner

        # Mock CSV writer
        mock_csv_writer = Mock()
        mock_csv_writer.write.return_value = self.cleaned_csv
        mock_csv_writer_class.return_value = mock_csv_writer

        mock_confirm.return_value = True

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
            ],
        )

        assert result.exit_code == 0
        mock_write_file.assert_called_once()
        # Callback should be called once for each change
        changes_list: list[Any] = self.changes_with_modifications.get("changes", [])  # type: ignore[assignment]
        assert mock_confirm.call_count == len(changes_list)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.typer.confirm")
    def test_clean_spdx_id_with_modifications_prompting_mode_reject(
        self,
        mock_confirm: Mock,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
    ) -> None:
        """Test execution with modifications in prompting mode (user rejects)."""
        # Mock Path objects
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner with callback simulation
        mock_cleaner = Mock()

        def mock_clean_metadata_reject(
            metadata_list: list[Metadata],
            change_callback: Any = None,
        ) -> tuple[list[Metadata], dict[str, Any]]:
            # If callback is provided, call it and simulate rejection
            if change_callback:
                changes_list: list[dict[str, Any]] = self.changes_with_modifications.get("changes", [])  # type: ignore[assignment]
                for change in changes_list:
                    if not change_callback(change):
                        # User rejected, return no changes
                        return (
                            metadata_list,
                            {"total_rows": 1, "modified_count": 0, "changes": []},
                        )
            return (metadata_list, self.changes_with_modifications)

        mock_cleaner.clean_metadata.side_effect = mock_clean_metadata_reject
        mock_spdx_cleaner_class.return_value = mock_cleaner

        # Mock CSV writer
        mock_csv_writer = Mock()
        mock_csv_writer.write.return_value = self.cleaned_csv
        mock_csv_writer_class.return_value = mock_csv_writer

        mock_confirm.return_value = False  # User rejects the change

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
            ],
        )

        assert result.exit_code == 0
        # File should still be written (with no changes since user rejected)
        mock_write_file.assert_called_once()
        # Callback should be called once for the change
        changes_list: list[Any] = self.changes_with_modifications.get("changes", [])  # type: ignore[assignment]
        assert mock_confirm.call_count == len(changes_list)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_with_invalid_log_level(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
    ) -> None:
        """Test error handling with invalid log level."""
        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--log-level",
                "INVALID",
                "--silent",
            ],
        )

        assert result.exit_code == 1

    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_with_value_error(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
    ) -> None:
        """Test error handling when ValueError is raised."""
        # Mock Path objects to pass validation
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_create_llm_client.side_effect = ValueError("Invalid provider")

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--silent",
            ],
        )

        assert result.exit_code == 1
        assert "Configuration error: Invalid provider" in result.stderr

    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_with_generic_exception(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
    ) -> None:
        """Test error handling when generic Exception is raised."""
        # Mock Path objects to pass validation
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner to raise exception
        mock_cleaner = Mock()
        mock_cleaner.clean_metadata.side_effect = Exception("Unexpected error")
        mock_spdx_cleaner_class.return_value = mock_cleaner

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--silent",
            ],
        )

        assert result.exit_code == 1

    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.typer.confirm")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    def test_clean_spdx_id_output_file_exists_reject_overwrite(
        self,
        mock_path_class: Mock,
        mock_confirm: Mock,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
    ) -> None:
        """Test prompting for overwrite when output file exists (user rejects)."""
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_output_path = Mock()
        mock_output_path.exists.return_value = True

        def path_side_effect(path: str) -> Mock:
            if "input" in path:
                return mock_input_path
            return mock_output_path

        mock_path_class.side_effect = path_side_effect
        mock_confirm.return_value = False

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
            ],
        )

        assert result.exit_code == 0
        mock_write_file.assert_not_called()

    @patch("dd_license_attribution.cli.clean_spdx_id_command.os.environ")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_uses_anthropic_env_var_with_anthropic_provider(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
        mock_environ: Mock,
    ) -> None:
        """Test that ANTHROPIC_API_KEY is used when Anthropic provider is selected."""
        # Mock environment with both keys set
        mock_environ.get.side_effect = lambda key: {
            "OPENAI_API_KEY": "openai-key",
            "ANTHROPIC_API_KEY": "anthropic-key",
        }.get(key)

        # Mock Path objects
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner
        mock_cleaner = Mock()
        mock_cleaner.clean_metadata.return_value = (
            self.sample_metadata,
            self.changes_no_modifications,
        )
        mock_spdx_cleaner_class.return_value = mock_cleaner

        # Mock CSV writer
        mock_csv_writer = Mock()
        mock_csv_writer.write.return_value = self.cleaned_csv
        mock_csv_writer_class.return_value = mock_csv_writer

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--llm-provider",
                "anthropic",
                "--silent",
            ],
        )

        assert result.exit_code == 0
        # Should use anthropic-key, not openai-key
        mock_create_llm_client.assert_called_once_with(
            "anthropic", "anthropic-key", None
        )

    @patch("dd_license_attribution.cli.clean_spdx_id_command.os.environ")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.Path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_uses_openai_env_var_with_openai_provider(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path: Mock,
        mock_environ: Mock,
    ) -> None:
        """Test that OPENAI_API_KEY is used when OpenAI provider is selected (default)."""
        # Mock environment with both keys set
        mock_environ.get.side_effect = lambda key: {
            "OPENAI_API_KEY": "openai-key",
            "ANTHROPIC_API_KEY": "anthropic-key",
        }.get(key)

        # Mock Path objects
        mock_input_path = Mock()
        mock_input_path.exists.return_value = True
        mock_input_path.absolute.return_value = "/abs/input.csv"
        mock_output_path = Mock()
        mock_output_path.exists.return_value = False
        mock_output_path.absolute.return_value = "/abs/output.csv"
        mock_path.side_effect = [mock_input_path, mock_output_path]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner
        mock_cleaner = Mock()
        mock_cleaner.clean_metadata.return_value = (
            self.sample_metadata,
            self.changes_no_modifications,
        )
        mock_spdx_cleaner_class.return_value = mock_cleaner

        # Mock CSV writer
        mock_csv_writer = Mock()
        mock_csv_writer.write.return_value = self.cleaned_csv
        mock_csv_writer_class.return_value = mock_csv_writer

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--silent",
            ],
        )

        assert result.exit_code == 0
        # Should use openai-key (default provider), not anthropic-key
        mock_create_llm_client.assert_called_once_with("openai", "openai-key", None)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.os.environ")
    def test_clean_spdx_id_missing_api_key_with_wrong_env_var(
        self, mock_environ: Mock
    ) -> None:
        """Test error when wrong environment variable is set for provider."""
        # Only OPENAI_API_KEY is set, but we're using Anthropic
        mock_environ.get.side_effect = lambda key: {
            "OPENAI_API_KEY": "openai-key",
        }.get(key)

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--llm-provider",
                "anthropic",
                "--silent",
            ],
        )

        assert result.exit_code == 1
        assert "API key is required" in result.stderr or "API key is required" in str(
            result.exception
        )
