# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

from pathlib import Path

import pytest

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.license_3rdparty_metadata_collection_strategy import (  # noqa: E501
    License3rdPartyMetadataCollectionStrategy,
)


def test_reads_valid_csv_file(tmp_path: Path) -> None:
    """Test reading a valid LICENSE-3rdparty.csv file."""
    csv_content = """component,origin,license,copyright
test-package,https://github.com/test/package,"['MIT']","['Test Author']"
another-package,https://github.com/another/package,"['Apache-2.0']","['Another Author', 'Co-Author']"
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))
    result = strategy.augment_metadata([])

    assert len(result) == 2
    assert result[0].name == "test-package"
    assert result[0].origin == "https://github.com/test/package"
    assert result[0].license == ["MIT"]
    assert result[0].copyright == ["Test Author"]
    assert result[0].version is None
    assert result[0].local_src_path is None

    assert result[1].name == "another-package"
    assert result[1].origin == "https://github.com/another/package"
    assert result[1].license == ["Apache-2.0"]
    assert result[1].copyright == ["Another Author", "Co-Author"]
    assert result[1].version is None
    assert result[1].local_src_path is None


def test_handles_case_insensitive_column_names(tmp_path: Path) -> None:
    """Test that column names are case-insensitive."""
    csv_content = """Component,Origin,LICENSE,COPYRIGHT
test-package,https://github.com/test/package,"['MIT']","['Test Author']"
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))
    result = strategy.augment_metadata([])

    assert len(result) == 1
    assert result[0].name == "test-package"
    assert result[0].origin == "https://github.com/test/package"
    assert result[0].license == ["MIT"]
    assert result[0].copyright == ["Test Author"]
    assert result[0].version is None
    assert result[0].local_src_path is None


def test_handles_empty_csv_file(tmp_path: Path) -> None:
    """Test handling of an empty CSV file."""
    csv_content = """component,origin,license,copyright
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))
    result = strategy.augment_metadata([])

    assert len(result) == 0


def test_raises_error_on_missing_required_columns(tmp_path: Path) -> None:
    """Test that missing required columns raises ValueError."""
    csv_content = """component,origin,license
test-package,https://github.com/test/package,"['MIT']"
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))

    with pytest.raises(ValueError, match="CSV file must contain columns"):
        strategy.augment_metadata([])


def test_handles_empty_license_and_copyright_fields(tmp_path: Path) -> None:
    """Test handling of empty license and copyright fields."""
    csv_content = """component,origin,license,copyright
test-package,https://github.com/test/package,,
another-package,https://github.com/another/package,"[]","[]"
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))
    result = strategy.augment_metadata([])

    assert len(result) == 2
    assert result[0].name == "test-package"
    assert result[0].origin == "https://github.com/test/package"
    assert result[0].license == []
    assert result[0].copyright == []
    assert result[0].version is None
    assert result[0].local_src_path is None

    assert result[1].name == "another-package"
    assert result[1].origin == "https://github.com/another/package"
    assert result[1].license == []
    assert result[1].copyright == []
    assert result[1].version is None
    assert result[1].local_src_path is None


def test_handles_malformed_license_copyright_as_empty(tmp_path: Path) -> None:
    """Test that malformed license/copyright strings are treated as empty."""
    csv_content = """component,origin,license,copyright
test-package,https://github.com/test/package,"invalid-list","not-a-list"
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))
    result = strategy.augment_metadata([])

    assert len(result) == 1
    assert result[0].name == "test-package"
    assert result[0].origin == "https://github.com/test/package"
    assert result[0].license == []
    assert result[0].copyright == []
    assert result[0].version is None
    assert result[0].local_src_path is None


def test_augments_existing_metadata_list(tmp_path: Path) -> None:
    """Test that the strategy augments rather than replaces metadata."""
    csv_content = """component,origin,license,copyright
csv-package,https://github.com/csv/package,"['MIT']","['CSV Author']"
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    existing_metadata = [
        Metadata(
            name="existing-package",
            origin="https://github.com/existing/package",
            version="1.0.0",
            local_src_path="/path/to/package",
            license=["Apache-2.0"],
            copyright=["Existing Author"],
        )
    ]

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))
    result = strategy.augment_metadata(existing_metadata)

    assert len(result) == 2
    assert result[0].name == "existing-package"
    assert result[0].origin == "https://github.com/existing/package"
    assert result[0].version == "1.0.0"
    assert result[0].local_src_path == "/path/to/package"
    assert result[0].license == ["Apache-2.0"]
    assert result[0].copyright == ["Existing Author"]
    assert result[1].name == "csv-package"
    assert result[1].origin == "https://github.com/csv/package"
    assert result[1].version is None
    assert result[1].local_src_path is None
    assert result[1].license == ["MIT"]
    assert result[1].copyright == ["CSV Author"]


def test_merges_with_existing_metadata_by_name(tmp_path: Path) -> None:
    """Test that existing metadata values are preserved when merging."""
    csv_content = """component,origin,license,copyright
existing-package,https://github.com/csv/package,"['MIT']","['CSV Author']"
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    # Existing metadata with same name but different values
    existing_metadata = [
        Metadata(
            name="existing-package",
            origin="https://github.com/existing/package",
            version="1.0.0",
            local_src_path="/path/to/package",
            license=["Apache-2.0"],
            copyright=["Existing Author"],
        )
    ]

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))
    result = strategy.augment_metadata(existing_metadata)

    # Should only have 1 entry (merged, not added)
    assert len(result) == 1
    # Existing non-empty values should be preserved
    assert result[0].name == "existing-package"
    assert result[0].origin == "https://github.com/existing/package"
    assert result[0].version == "1.0.0"
    assert result[0].local_src_path == "/path/to/package"
    assert result[0].license == ["Apache-2.0"]
    assert result[0].copyright == ["Existing Author"]


def test_fills_empty_fields_in_existing_metadata(tmp_path: Path) -> None:
    """Test that empty fields in existing metadata are filled from CSV."""
    csv_content = """component,origin,license,copyright
existing-package,https://github.com/csv/package,"['MIT']","['CSV Author']"
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    # Existing metadata with empty license and copyright
    existing_metadata = [
        Metadata(
            name="existing-package",
            origin="https://github.com/existing/package",
            version="1.0.0",
            local_src_path="/path/to/package",
            license=[],
            copyright=[],
        )
    ]

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))
    result = strategy.augment_metadata(existing_metadata)

    # Should only have 1 entry (merged, not added)
    assert len(result) == 1
    # Empty values should be filled from CSV
    assert result[0].name == "existing-package"
    assert result[0].origin == "https://github.com/existing/package"
    assert result[0].license == ["MIT"]
    assert result[0].copyright == ["CSV Author"]
    assert result[0].version == "1.0.0"
    assert result[0].local_src_path == "/path/to/package"


def test_raises_file_not_found_error() -> None:
    """Test that FileNotFoundError is raised for non-existent file."""
    strategy = License3rdPartyMetadataCollectionStrategy("/nonexistent/file.csv")

    with pytest.raises(FileNotFoundError):
        strategy.augment_metadata([])


def test_handles_mixed_case_column_names(tmp_path: Path) -> None:
    """Test various mixed case combinations for column names."""
    csv_content = """CoMpOnEnT,ORIGIN,LiCeNsE,CoPyRiGhT
test-package,https://github.com/test/package,"['MIT']","['Test Author']"
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))
    result = strategy.augment_metadata([])

    assert len(result) == 1
    assert result[0].name == "test-package"
    assert result[0].origin == "https://github.com/test/package"
    assert result[0].license == ["MIT"]
    assert result[0].copyright == ["Test Author"]
    assert result[0].version is None
    assert result[0].local_src_path is None


def test_raises_error_on_invalid_csv_format_with_extra_columns(
    tmp_path: Path,
) -> None:
    """Test that invalid CSV format with extra columns raises ValueError."""
    csv_content = """component,origin,license,copyright
test-package,https://github.com/test/package,"['MIT']","['Test Author']",extra
"""
    csv_file = tmp_path / "test.csv"
    csv_file.write_text(csv_content)

    strategy = License3rdPartyMetadataCollectionStrategy(str(csv_file))

    with pytest.raises(ValueError, match="Invalid CSV format"):
        strategy.augment_metadata([])
