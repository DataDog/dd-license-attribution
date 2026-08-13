# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

# Unit tests for clean-spdx-id CLI command

from typing import Any
from unittest.mock import Mock, call, patch

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

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
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
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test successful execution with no changes needed."""
        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]  # input exists, output doesn't
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

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
                "--yes",
            ],
        )

        assert result.exit_code == 0
        mock_create_llm_client.assert_called_once_with("openai", "test-key", None)
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_spdx_cleaner_class.assert_called_once_with(mock_llm_client)
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert call_args[1]["change_callback"] is None
        mock_csv_writer_class.assert_called_once()
        mock_csv_writer.write.assert_called_once_with(self.sample_metadata)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_write_file.assert_called_once_with("/abs/output.csv", self.cleaned_csv)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
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
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test using Anthropic as LLM provider."""
        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

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
                "--yes",
            ],
        )

        assert result.exit_code == 0
        mock_create_llm_client.assert_called_once_with("anthropic", "test-key", None)
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_spdx_cleaner_class.assert_called_once_with(mock_llm_client)
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert call_args[1]["change_callback"] is None
        mock_csv_writer_class.assert_called_once()
        mock_csv_writer.write.assert_called_once_with(self.sample_metadata)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_write_file.assert_called_once_with("/abs/output.csv", self.cleaned_csv)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
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
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test using custom model."""
        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

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
                "--yes",
            ],
        )

        assert result.exit_code == 0
        mock_create_llm_client.assert_called_once_with(
            "openai", "test-key", "gpt-3.5-turbo"
        )
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_spdx_cleaner_class.assert_called_once_with(mock_llm_client)
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert call_args[1]["change_callback"] is None
        mock_csv_writer_class.assert_called_once()
        mock_csv_writer.write.assert_called_once_with(self.sample_metadata)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_write_file.assert_called_once_with("/abs/output.csv", self.cleaned_csv)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.get_env_var")
    def test_clean_spdx_id_missing_api_key(self, mock_get_env_var: Mock) -> None:
        """Test error handling when API key is missing."""
        # Ensure no API keys are available from environment
        mock_get_env_var.return_value = None

        result = runner.invoke(
            app,
            ["clean-spdx-id", "input.csv", "output.csv", "--yes"],
        )

        assert result.exit_code == 1
        assert "API key is required" in result.stderr
        mock_get_env_var.assert_called_once_with("OPENAI_API_KEY")

    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
    def test_clean_spdx_id_input_file_not_found(self, mock_path_exists: Mock) -> None:
        """Test error handling when input file doesn't exist."""
        mock_path_exists.return_value = False

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "nonexistent.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--yes",
            ],
        )

        assert result.exit_code == 1
        assert "Input CSV file not found" in result.stderr
        mock_path_exists.assert_called_once_with("nonexistent.csv")

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    def test_clean_spdx_id_with_modifications_auto_confirm_mode(
        self,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test execution with modifications in auto-confirm mode."""
        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

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
                "--yes",
            ],
        )

        assert result.exit_code == 0
        mock_create_llm_client.assert_called_once_with("openai", "test-key", None)
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_spdx_cleaner_class.assert_called_once_with(mock_llm_client)
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert call_args[1]["change_callback"] is None
        mock_csv_writer_class.assert_called_once()
        mock_csv_writer.write.assert_called_once_with(self.sample_metadata)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_write_file.assert_called_once_with("/abs/output.csv", self.cleaned_csv)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
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
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test execution with modifications in prompting mode (user accepts)."""
        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

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
        mock_create_llm_client.assert_called_once_with("openai", "test-key", None)
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_spdx_cleaner_class.assert_called_once_with(mock_llm_client)
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert callable(call_args[1]["change_callback"])
        mock_csv_writer_class.assert_called_once()
        mock_csv_writer.write.assert_called_once_with(self.sample_metadata)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_write_file.assert_called_once_with("/abs/output.csv", self.cleaned_csv)
        # Callback should be called once for each change with expected prompt
        mock_confirm.assert_called_once_with(
            "Apply this change?", err=True, default=True
        )

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
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
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test execution with modifications in prompting mode (user rejects)."""
        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

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
        mock_create_llm_client.assert_called_once_with("openai", "test-key", None)
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_spdx_cleaner_class.assert_called_once_with(mock_llm_client)
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert callable(call_args[1]["change_callback"])
        mock_csv_writer_class.assert_called_once()
        mock_csv_writer.write.assert_called_once_with(self.sample_metadata)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_has_calls([call("input.csv"), call("output.csv")])
        # File should still be written (with no changes since user rejected)
        mock_write_file.assert_called_once_with("/abs/output.csv", self.cleaned_csv)
        # Callback should be called once for the change with expected prompt
        mock_confirm.assert_called_once_with(
            "Apply this change?", err=True, default=True
        )

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
                "--yes",
            ],
        )

        assert result.exit_code == 1
        # Command exits early at log-level validation; no business logic should run
        mock_create_llm_client.assert_not_called()
        mock_write_file.assert_not_called()
        mock_spdx_cleaner_class.assert_not_called()
        mock_strategy_class.assert_not_called()
        mock_csv_writer_class.assert_not_called()

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
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
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test error handling when ValueError is raised."""
        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

        mock_create_llm_client.side_effect = ValueError("Invalid provider")

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--yes",
            ],
        )

        assert result.exit_code == 1
        assert "Configuration error: Invalid provider" in result.stderr
        mock_create_llm_client.assert_called_once_with("openai", "test-key", None)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_not_called()
        mock_write_file.assert_not_called()
        mock_spdx_cleaner_class.assert_not_called()
        mock_strategy_class.assert_not_called()
        mock_csv_writer_class.assert_not_called()

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
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
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test error handling when generic Exception is raised."""
        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

        mock_llm_client = Mock()
        mock_create_llm_client.return_value = mock_llm_client

        # Mock strategy to return metadata
        mock_strategy = Mock()
        mock_strategy.augment_metadata.return_value = self.sample_metadata
        mock_strategy_class.return_value = mock_strategy

        # Mock cleaner to raise exception
        mock_cleaner = Mock()
        mock_cleaner.clean_metadata.side_effect = RuntimeError("Unexpected error")
        mock_spdx_cleaner_class.return_value = mock_cleaner

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--api-key",
                "test-key",
                "--yes",
            ],
        )

        assert result.exit_code == 1
        mock_create_llm_client.assert_called_once_with("openai", "test-key", None)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_called_once_with("input.csv")
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_spdx_cleaner_class.assert_called_once_with(mock_llm_client)
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert call_args[1]["change_callback"] is None
        mock_write_file.assert_not_called()
        mock_csv_writer_class.assert_not_called()

    @patch("dd_license_attribution.cli.clean_spdx_id_command.write_file")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.CSVReportingWritter")
    @patch(
        "dd_license_attribution.cli.clean_spdx_id_command.License3rdPartyMetadataCollectionStrategy"
    )
    @patch("dd_license_attribution.cli.clean_spdx_id_command.SPDXCleaner")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.create_llm_client")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.typer.confirm")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
    def test_clean_spdx_id_output_file_exists_reject_overwrite(
        self,
        mock_path_exists: Mock,
        mock_confirm: Mock,
        mock_create_llm_client: Mock,
        mock_spdx_cleaner_class: Mock,
        mock_strategy_class: Mock,
        mock_csv_writer_class: Mock,
        mock_write_file: Mock,
    ) -> None:
        """Test prompting for overwrite when output file exists (user rejects)."""
        mock_path_exists.side_effect = [True, True]  # input exists, output exists
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
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_confirm.assert_called_once_with(
            "Output file output.csv already exists. Overwrite?", err=True
        )
        mock_create_llm_client.assert_not_called()
        mock_spdx_cleaner_class.assert_not_called()
        mock_strategy_class.assert_not_called()
        mock_csv_writer_class.assert_not_called()

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.get_env_var")
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
        mock_get_env_var: Mock,
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test that ANTHROPIC_API_KEY is used when Anthropic provider is selected."""
        # Mock get_env_var to return appropriate key based on env var name
        mock_get_env_var.side_effect = lambda name: {
            "OPENAI_API_KEY": "openai-key",
            "ANTHROPIC_API_KEY": "anthropic-key",
        }.get(name)

        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

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
                "--yes",
            ],
        )

        assert result.exit_code == 0
        # Should use anthropic-key, not openai-key
        mock_create_llm_client.assert_called_once_with(
            "anthropic", "anthropic-key", None
        )
        mock_get_env_var.assert_called_once_with("ANTHROPIC_API_KEY")
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_spdx_cleaner_class.assert_called_once_with(mock_llm_client)
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert call_args[1]["change_callback"] is None
        mock_csv_writer_class.assert_called_once()
        mock_csv_writer.write.assert_called_once_with(self.sample_metadata)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_write_file.assert_called_once_with("/abs/output.csv", self.cleaned_csv)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.absolute_path")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.path_exists")
    @patch("dd_license_attribution.cli.clean_spdx_id_command.get_env_var")
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
        mock_get_env_var: Mock,
        mock_path_exists: Mock,
        mock_absolute_path: Mock,
    ) -> None:
        """Test that OPENAI_API_KEY is used when OpenAI provider is selected (default)."""
        # Mock get_env_var to return appropriate key based on env var name
        mock_get_env_var.side_effect = lambda name: {
            "OPENAI_API_KEY": "openai-key",
            "ANTHROPIC_API_KEY": "anthropic-key",
        }.get(name)

        # Mock adaptor functions
        mock_path_exists.side_effect = [True, False]
        mock_absolute_path.side_effect = ["/abs/input.csv", "/abs/output.csv"]

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
                "--yes",
            ],
        )

        assert result.exit_code == 0
        # Should use openai-key (default provider), not anthropic-key
        mock_create_llm_client.assert_called_once_with("openai", "openai-key", None)
        mock_get_env_var.assert_called_once_with("OPENAI_API_KEY")
        mock_strategy_class.assert_called_once_with("/abs/input.csv")
        mock_strategy.augment_metadata.assert_called_once_with([])
        mock_spdx_cleaner_class.assert_called_once_with(mock_llm_client)
        mock_cleaner.clean_metadata.assert_called_once()
        call_args = mock_cleaner.clean_metadata.call_args
        assert call_args[0][0] == self.sample_metadata
        assert call_args[1]["change_callback"] is None
        mock_csv_writer_class.assert_called_once()
        mock_csv_writer.write.assert_called_once_with(self.sample_metadata)
        mock_path_exists.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_absolute_path.assert_has_calls([call("input.csv"), call("output.csv")])
        mock_write_file.assert_called_once_with("/abs/output.csv", self.cleaned_csv)

    @patch("dd_license_attribution.cli.clean_spdx_id_command.get_env_var")
    def test_clean_spdx_id_missing_api_key_with_wrong_env_var(
        self, mock_get_env_var: Mock
    ) -> None:
        """Test error when wrong environment variable is set for provider."""
        # Only OPENAI_API_KEY is set, but we're using Anthropic
        mock_get_env_var.side_effect = lambda name: {
            "OPENAI_API_KEY": "openai-key",
        }.get(name)

        result = runner.invoke(
            app,
            [
                "clean-spdx-id",
                "input.csv",
                "output.csv",
                "--llm-provider",
                "anthropic",
                "--yes",
            ],
        )

        assert result.exit_code == 1
        assert "API key is required" in result.stderr
        mock_get_env_var.assert_called_once_with("ANTHROPIC_API_KEY")
