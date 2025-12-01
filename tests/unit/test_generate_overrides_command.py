# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are
# licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog
# (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import sys
from unittest.mock import Mock, patch

import pytest
import typer
from typer.testing import CliRunner

from dd_license_attribution.metadata_collector.metadata import Metadata


@pytest.fixture
def runner() -> CliRunner:
    """Create a fresh CLI runner for each test."""
    return CliRunner()


@pytest.fixture
def app() -> typer.Typer:
    """
    Create a fresh app instance for each test.

    This avoids callback state issues.
    """
    # Remove the module from sys.modules to force a fresh import
    modules_to_reload = [
        "dd_license_attribution.cli.generate_overrides_command",
        "dd_license_attribution.cli.main_cli",
    ]
    for mod in modules_to_reload:
        if mod in sys.modules:
            del sys.modules[mod]

    # Import fresh
    from dd_license_attribution.cli.main_cli import app as fresh_app

    return fresh_app


def test_file_not_found(app: typer.Typer, runner: CliRunner) -> None:
    """Test that the command handles missing CSV files gracefully."""
    result = runner.invoke(app, ["generate-overrides", "nonexistent.csv"], color=False)
    assert result.exit_code == 1
    assert "Error: File 'nonexistent.csv' not found." in result.stderr


@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_empty_csv_file(
    mock_strategy_augment_metadata: Mock, app: typer.Typer, runner: CliRunner
) -> None:
    """Test that the command handles empty CSV files correctly."""
    mock_strategy_augment_metadata.return_value = []

    result = runner.invoke(app, ["generate-overrides", "empty.csv"], color=False)
    assert result.exit_code == 1
    assert "Error: CSV file is empty." in result.stderr


@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_invalid_csv_file(
    mock_strategy_augement_metadata: Mock, app: typer.Typer, runner: CliRunner
) -> None:
    """Test that the command handles invalid CSV files (ValueError)."""
    mock_strategy_augement_metadata.side_effect = ValueError("Invalid CSV format")

    result = runner.invoke(app, ["generate-overrides", "invalid.csv"], color=False)
    assert result.exit_code == 1
    assert "Error: Invalid CSV format" in result.stderr


@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_no_problematic_entries(
    mock_strategy_augment_metadata: Mock, app: typer.Typer, runner: CliRunner
) -> None:
    """Test command handles CSV files with no problematic entries."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="https://github.com/test/test",
        local_src_path=None,
        license=["MIT"],
        copyright=["Copyright 2024 Test Corp"],
    )
    mock_strategy_augment_metadata.return_value = [metadata]

    result = runner.invoke(app, ["generate-overrides", "good.csv"], color=False)
    assert result.exit_code == 0
    assert (
        "No entries with missing license or copyright information found."
        in result.stdout
    )


@patch("dd_license_attribution.adaptors.os.write_file")
@patch(
    "dd_license_attribution.cli.generate_overrides_command.OverridesGenerator.generate_overrides"
)
@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_user_skips_all_entries(
    mock_strategy_augment_metadata: Mock,
    mock_generator_generate_overrides: Mock,
    mock_file: Mock,
    app: typer.Typer,
    runner: CliRunner,
) -> None:
    """Test that the command handles the user skipping all entries."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="https://github.com/test/test",
        local_src_path=None,
        license=[],
        copyright=["Copyright 2024 Test Corp"],
    )
    mock_strategy_augment_metadata.return_value = [metadata]

    # Simulate user saying "no" to fixing the entry
    result = runner.invoke(
        app, ["generate-overrides", "test.csv"], input="n\n", color=False
    )
    assert result.exit_code == 0
    assert "No override rules were created." in result.stdout


@patch("dd_license_attribution.cli.generate_overrides_command.write_file")
@patch(
    "dd_license_attribution.cli.generate_overrides_command.OverridesGenerator.generate_overrides"
)
@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_successful_override_generation(
    mock_strategy_augment_metadata: Mock,
    mock_generator_generate_overrides: Mock,
    mock_file: Mock,
    app: typer.Typer,
    runner: CliRunner,
) -> None:
    """Test successful generation of override file with user input."""
    # Create metadata with missing license
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="https://github.com/test/test",
        local_src_path=None,
        license=[],
        copyright=["Copyright 2024 Test Corp"],
    )
    mock_strategy_augment_metadata.return_value = [metadata]

    # Mock the generator
    mock_generator_generate_overrides.return_value = '{"overrides": []}'

    # Simulate user input: yes to fix, keep origin, add MIT license,
    # keep copyright
    user_input = "y\n\nMIT\n\n"
    result = runner.invoke(
        app, ["generate-overrides", "test.csv"], input=user_input, color=False
    )

    assert result.exit_code == 0
    assert "Successfully created override file: .ddla-overrides" in result.stdout
    assert "with 1 rule(s)." in result.stdout
    mock_file.assert_called_once_with(".ddla-overrides", '{"overrides": []}')


@patch("dd_license_attribution.cli.generate_overrides_command.write_file")
@patch(
    "dd_license_attribution.cli.generate_overrides_command.OverridesGenerator.generate_overrides"
)
@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_custom_output_file(
    mock_strategy_augment_metadata: Mock,
    mock_generator_generate_overrides: Mock,
    mock_file: Mock,
    app: typer.Typer,
    runner: CliRunner,
) -> None:
    """Test that custom output file path is respected."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="https://github.com/test/test",
        local_src_path=None,
        license=[],
        copyright=["Copyright 2024 Test Corp"],
    )
    mock_strategy_augment_metadata.return_value = [metadata]

    mock_generator_generate_overrides.return_value = '{"overrides": []}'

    user_input = "y\n\nMIT\n\n"
    result = runner.invoke(
        app,
        [
            "generate-overrides",
            "test.csv",
            "--output",
            "custom-overrides.json",
        ],
        input=user_input,
        color=False,
    )

    assert result.exit_code == 0
    assert "Successfully created override file: custom-overrides.json" in result.stdout
    mock_file.assert_called_once_with("custom-overrides.json", '{"overrides": []}')


@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_only_license_option(
    mock_strategy_augment_metadata: Mock, app: typer.Typer, runner: CliRunner
) -> None:
    """Test that --only-license filters entries correctly."""
    metadata_missing_license = Metadata(
        name="test-package-1",
        version="1.0.0",
        origin="https://github.com/test/test1",
        local_src_path=None,
        license=[],
        copyright=["Copyright 2024 Test Corp"],
    )
    # Create metadata with missing copyright but present license
    metadata_missing_copyright = Metadata(
        name="test-package-2",
        version="1.0.0",
        origin="https://github.com/test/test2",
        local_src_path=None,
        license=["MIT"],
        copyright=[],
    )
    mock_strategy_augment_metadata.return_value = [
        metadata_missing_license,
        metadata_missing_copyright,
    ]

    # Skip all entries to avoid dealing with prompts
    result = runner.invoke(
        app,
        ["generate-overrides", "test.csv", "--only-license"],
        input="n\n",
        color=False,
    )

    assert result.exit_code == 0
    # Should only show 1 entry (the one missing license)
    assert (
        "Found 1 entries with missing license or copyright information."
        in result.stdout
    )


@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_only_copyright_option(
    mock_strategy_augment_metadata: Mock, app: typer.Typer, runner: CliRunner
) -> None:
    """Test that --only-copyright filters entries correctly."""
    metadata_missing_license = Metadata(
        name="test-package-1",
        version="1.0.0",
        origin="https://github.com/test/test1",
        local_src_path=None,
        license=[],
        copyright=["Copyright 2024 Test Corp"],
    )
    # Create metadata with missing copyright but present license
    metadata_missing_copyright = Metadata(
        name="test-package-2",
        version="1.0.0",
        origin="https://github.com/test/test2",
        local_src_path=None,
        license=["MIT"],
        copyright=[],
    )
    mock_strategy_augment_metadata.return_value = [
        metadata_missing_license,
        metadata_missing_copyright,
    ]

    # Skip all entries to avoid dealing with prompts
    result = runner.invoke(
        app,
        ["generate-overrides", "test.csv", "--only-copyright"],
        input="n\n",
        color=False,
    )

    assert result.exit_code == 0
    # Should only show 1 entry (the one missing copyright)
    assert (
        "Found 1 entries with missing license or copyright information."
        in result.stdout
    )


def test_mutually_exclusive_options(app: typer.Typer, runner: CliRunner) -> None:
    """Test that --only-license and --only-copyright can't be used together."""
    result = runner.invoke(
        app,
        [
            "generate-overrides",
            "test.csv",
            "--only-license",
            "--only-copyright",
        ],
        color=False,
    )
    assert result.exit_code == 2
    # Error message is present in output, possibly with formatting
    output = result.stdout + result.stderr
    assert "--only-license" in output
    assert "--only-copyright" in output


@patch("dd_license_attribution.cli.generate_overrides_command.write_file")
@patch(
    "dd_license_attribution.cli.generate_overrides_command.OverridesGenerator.generate_overrides"
)
@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_multiple_entries_mixed_responses(
    mock_strategy_augment_metadata: Mock,
    mock_generator_generate_overrides: Mock,
    mock_file: Mock,
    app: typer.Typer,
    runner: CliRunner,
) -> None:
    """Test handling multiple entries with mixed user responses."""
    metadata1 = Metadata(
        name="test-package-1",
        version="1.0.0",
        origin="https://github.com/test/test1",
        local_src_path=None,
        license=[],
        copyright=["Copyright 2024 Test Corp"],
    )
    metadata2 = Metadata(
        name="test-package-2",
        version="2.0.0",
        origin="https://github.com/test/test2",
        local_src_path=None,
        license=["MIT"],
        copyright=[],
    )
    mock_strategy_augment_metadata.return_value = [metadata1, metadata2]
    mock_generator_generate_overrides.return_value = '{"overrides": []}'

    # Fix first entry, skip second entry
    user_input = "y\n\nMIT\n\nn\n"
    result = runner.invoke(
        app, ["generate-overrides", "test.csv"], input=user_input, color=False
    )

    assert result.exit_code == 0
    assert (
        "Found 2 entries with missing license or copyright information."
        in result.stdout
    )
    assert "Successfully created override file: .ddla-overrides" in result.stdout
    assert "with 1 rule(s)." in result.stdout


@patch("dd_license_attribution.cli.generate_overrides_command.write_file")
@patch(
    "dd_license_attribution.cli.generate_overrides_command.OverridesGenerator.generate_overrides"
)
@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_error_writing_output_file(
    mock_strategy_augment_metadata: Mock,
    mock_generator_generate_overrides: Mock,
    mock_file: Mock,
    app: typer.Typer,
    runner: CliRunner,
) -> None:
    """Test that errors during file writing are handled gracefully."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="https://github.com/test/test",
        local_src_path=None,
        license=[],
        copyright=["Copyright 2024 Test Corp"],
    )
    mock_strategy_augment_metadata.return_value = [metadata]

    mock_generator_generate_overrides.return_value = '{"overrides": []}'

    # Simulate file write error
    mock_file.side_effect = IOError("Permission denied")

    user_input = "y\n\nMIT\n\n"
    result = runner.invoke(
        app, ["generate-overrides", "test.csv"], input=user_input, color=False
    )

    assert result.exit_code == 1
    assert "Error writing override file: Permission denied" in result.stderr


@patch("dd_license_attribution.cli.generate_overrides_command.write_file")
@patch(
    "dd_license_attribution.cli.generate_overrides_command.OverridesGenerator.generate_overrides"
)
@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_comma_separated_licenses_and_copyrights(
    mock_strategy_augment_metadata: Mock,
    mock_generator_generate_overrides: Mock,
    mock_file: Mock,
    app: typer.Typer,
    runner: CliRunner,
) -> None:
    """Test that comma-separated licenses and copyrights are parsed."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="https://github.com/test/test",
        local_src_path=None,
        license=[],
        copyright=[],
    )
    mock_strategy_augment_metadata.return_value = [metadata]

    mock_generator_generate_overrides.return_value = '{"overrides": []}'

    # Provide multiple licenses and copyrights separated by commas
    user_input = (
        "y\n\nMIT, Apache-2.0\n"
        "Copyright 2024 Test Corp, Copyright 2024 Another Corp\n"
    )
    result = runner.invoke(
        app, ["generate-overrides", "test.csv"], input=user_input, color=False
    )

    assert result.exit_code == 0
    assert "Successfully created override file: .ddla-overrides" in result.stdout

    # Verify that generate_overrides was called with proper rules
    mock_generator_generate_overrides.assert_called_once()
    override_rules = mock_generator_generate_overrides.call_args[0][0]
    assert len(override_rules) == 1
    assert override_rules[0].replacement.license == ["MIT", "Apache-2.0"]
    assert override_rules[0].replacement.copyright == [
        "Copyright 2024 Test Corp",
        "Copyright 2024 Another Corp",
    ]


@patch("dd_license_attribution.cli.generate_overrides_command.write_file")
@patch(
    "dd_license_attribution.cli.generate_overrides_command.OverridesGenerator.generate_overrides"
)
@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_keep_current_values_on_empty_input(
    mock_strategy_augment_metadata: Mock,
    mock_generator_generate_overrides: Mock,
    mock_file: Mock,
    app: typer.Typer,
    runner: CliRunner,
) -> None:
    """Test that pressing Enter keeps current values."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="https://github.com/test/test",
        local_src_path=None,
        license=["MIT"],
        copyright=[],
    )
    mock_strategy_augment_metadata.return_value = [metadata]

    mock_generator_generate_overrides.return_value = '{"overrides": []}'

    # Press Enter for origin, license (keep), and provide new copyright
    user_input = "y\n\n\nCopyright 2024 Test Corp\n"
    result = runner.invoke(
        app, ["generate-overrides", "test.csv"], input=user_input, color=False
    )

    assert result.exit_code == 0

    # Verify that the original license was kept
    override_rules = mock_generator_generate_overrides.call_args[0][0]
    assert len(override_rules) == 1
    assert override_rules[0].replacement.license == ["MIT"]
    assert override_rules[0].replacement.copyright == ["Copyright 2024 Test Corp"]


@patch("dd_license_attribution.cli.generate_overrides_command.write_file")
@patch(
    "dd_license_attribution.cli.generate_overrides_command.OverridesGenerator.generate_overrides"
)
@patch(
    "dd_license_attribution.cli.generate_overrides_command."
    "License3rdPartyMetadataCollectionStrategy.augment_metadata"
)
def test_quoted_values_with_commas(
    mock_strategy_augment_metadata: Mock,
    mock_generator_generate_overrides: Mock,
    mock_file: Mock,
    app: typer.Typer,
    runner: CliRunner,
) -> None:
    """
    Test that quoted copyright holders containing commas are parsed correctly.
    """
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="https://github.com/test/test",
        local_src_path=None,
        license=[],
        copyright=[],
    )
    mock_strategy_augment_metadata.return_value = [metadata]

    mock_generator_generate_overrides.return_value = '{"overrides": []}'

    # Use quoted values to preserve commas within copyright holder names
    user_input = (
        "y\n\n"  # yes to fix, keep origin
        "MIT\n"  # license
        '"Datadog, Inc.", "Google, LLC"\n'  # copyright with commas
    )
    result = runner.invoke(
        app, ["generate-overrides", "test.csv"], input=user_input, color=False
    )

    assert result.exit_code == 0
    assert "Successfully created override file: .ddla-overrides" in result.stdout

    # Verify that quoted values preserved internal commas
    override_rules = mock_generator_generate_overrides.call_args[0][0]
    assert len(override_rules) == 1
    assert override_rules[0].replacement.license == ["MIT"]
    # Should be two copyright holders, each preserving their internal commas
    assert override_rules[0].replacement.copyright == [
        "Datadog, Inc.",
        "Google, LLC",
    ]
