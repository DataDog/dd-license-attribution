# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

# Unit tests for SPDX cleaner

from unittest.mock import Mock

from dd_license_attribution.license_cleaner.spdx_cleaner import SPDXCleaner
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.report_generator.writters.csv_reporting_writter import (
    CSVReportingWritter,
)
from dd_license_attribution.utils.license_utils import is_long_license


class TestSPDXCleaner:
    """Test SPDX cleaner functionality."""

    def setup_method(self) -> None:
        """Setup test fixtures."""
        self.mock_llm_client = Mock()
        self.cleaner = SPDXCleaner(self.mock_llm_client)
        self.csv_writer = CSVReportingWritter()

    def test_initialization(self) -> None:
        """Test SPDX cleaner initialization."""
        assert self.cleaner.llm_client == self.mock_llm_client

    def test_clean_metadata_no_changes_needed(self) -> None:
        """Test cleaning metadata when no licenses need cleaning."""
        metadata_list = [
            Metadata(
                name="test-package",
                origin="https://github.com/test/package",
                local_src_path=None,
                version=None,
                license=["MIT"],
                copyright=["Copyright 2024"],
            ),
            Metadata(
                name="another-package",
                origin="https://github.com/another/package",
                local_src_path=None,
                version=None,
                license=["Apache-2.0"],
                copyright=["Copyright 2024"],
            ),
        ]

        cleaned_metadata, changes = self.cleaner.clean_metadata(metadata_list)

        assert changes["total_rows"] == 2
        assert changes["modified_count"] == 0
        assert len(changes["changes"]) == 0
        assert cleaned_metadata[0].license == ["MIT"]
        assert cleaned_metadata[1].license == ["Apache-2.0"]
        # LLM should not be called
        self.mock_llm_client.convert_to_spdx.assert_not_called()

    def test_clean_metadata_with_long_license_text(self) -> None:
        """Test cleaning metadata with long license descriptions."""
        long_license = "BSD 3-Clause License\n\nCopyright (c) 2022, Jupyter\nAll rights reserved.\n\nRedistribution and use in source and binary forms..."
        metadata_list = [
            Metadata(
                name="test-package",
                origin="https://github.com/test/package",
                local_src_path=None,
                version=None,
                license=[long_license],
                copyright=["Copyright 2024"],
            )
        ]

        self.mock_llm_client.convert_to_spdx.return_value = "BSD-3-Clause"

        cleaned_metadata, changes = self.cleaner.clean_metadata(metadata_list)

        assert changes["total_rows"] == 1
        assert changes["modified_count"] == 1
        assert len(changes["changes"]) == 1
        assert changes["changes"][0]["component"] == "test-package"
        assert changes["changes"][0]["converted"] == "BSD-3-Clause"
        assert cleaned_metadata[0].license == ["BSD-3-Clause"]

        # Verify LLM was called with the long license
        self.mock_llm_client.convert_to_spdx.assert_called_once_with(long_license)

    def test_clean_metadata_multiple_licenses_in_row(self) -> None:
        """Test cleaning metadata with multiple licenses (mixed short and long)."""
        long_license = "MIT License\n\nCopyright (c) 2023\n\nPermission is hereby granted, free of charge..."
        metadata_list = [
            Metadata(
                name="test-package",
                origin="https://github.com/test/package",
                local_src_path=None,
                version=None,
                license=["Apache-2.0", long_license],
                copyright=["Copyright 2024"],
            )
        ]

        self.mock_llm_client.convert_to_spdx.return_value = "MIT"

        cleaned_metadata, changes = self.cleaner.clean_metadata(metadata_list)

        assert changes["total_rows"] == 1
        assert changes["modified_count"] == 1
        assert "Apache-2.0" in cleaned_metadata[0].license
        assert "MIT" in cleaned_metadata[0].license

        # Verify LLM was called only for the long license
        self.mock_llm_client.convert_to_spdx.assert_called_once_with(long_license)

    def test_clean_metadata_multiple_rows_with_changes(self) -> None:
        """Test cleaning metadata with multiple rows needing changes."""
        long_license1 = "BSD 3-Clause License\n\nCopyright (c) 2022..."
        long_license2 = "Apache License\nVersion 2.0, January 2004..."
        metadata_list = [
            Metadata(
                name="package1",
                origin="https://github.com/test/package1",
                local_src_path=None,
                version=None,
                license=[long_license1],
                copyright=["Copyright 2024"],
            ),
            Metadata(
                name="package2",
                origin="https://github.com/test/package2",
                local_src_path=None,
                version=None,
                license=["MIT"],
                copyright=["Copyright 2024"],
            ),
            Metadata(
                name="package3",
                origin="https://github.com/test/package3",
                local_src_path=None,
                version=None,
                license=[long_license2],
                copyright=["Copyright 2024"],
            ),
        ]

        self.mock_llm_client.convert_to_spdx.side_effect = [
            "BSD-3-Clause",
            "Apache-2.0",
        ]

        cleaned_metadata, changes = self.cleaner.clean_metadata(metadata_list)

        assert changes["total_rows"] == 3
        assert changes["modified_count"] == 2
        assert len(changes["changes"]) == 2
        assert cleaned_metadata[0].license == ["BSD-3-Clause"]
        assert cleaned_metadata[1].license == ["MIT"]
        assert cleaned_metadata[2].license == ["Apache-2.0"]

        # Verify LLM was called twice (for two long licenses)
        assert self.mock_llm_client.convert_to_spdx.call_count == 2

    def test_clean_metadata_empty_list(self) -> None:
        """Test cleaning an empty metadata list."""
        metadata_list: list[Metadata] = []

        cleaned_metadata, changes = self.cleaner.clean_metadata(metadata_list)

        assert changes["total_rows"] == 0
        assert changes["modified_count"] == 0
        assert len(changes["changes"]) == 0
        assert len(cleaned_metadata) == 0
        self.mock_llm_client.convert_to_spdx.assert_not_called()

    def test_is_long_license_with_newlines(self) -> None:
        """Test is_long_license with license containing newlines."""
        license_with_newlines = "MIT License\n\nCopyright 2024"
        assert is_long_license(license_with_newlines) is True

    def test_is_long_license_with_long_text(self) -> None:
        """Test is_long_license with long text (>50 chars)."""
        long_text = (
            "This is a very long license description that exceeds fifty characters"
        )
        assert is_long_license(long_text) is True

    def test_is_long_license_with_spdx_identifier(self) -> None:
        """Test is_long_license with short SPDX identifier."""
        assert is_long_license("MIT") is False
        assert is_long_license("BSD-3-Clause") is False
        assert is_long_license("Apache-2.0") is False

    def test_clean_metadata_preserves_order(self) -> None:
        """Test that metadata order is preserved after cleaning."""
        long_license = "BSD 3-Clause License\n\nCopyright (c) 2022..."
        metadata_list = [
            Metadata(
                name="package-a",
                origin="https://github.com/a",
                local_src_path=None,
                version=None,
                license=["MIT"],
                copyright=["Copyright 2024"],
            ),
            Metadata(
                name="package-b",
                origin="https://github.com/b",
                local_src_path=None,
                version=None,
                license=[long_license],
                copyright=["Copyright 2024"],
            ),
            Metadata(
                name="package-c",
                origin="https://github.com/c",
                local_src_path=None,
                version=None,
                license=["Apache-2.0"],
                copyright=["Copyright 2024"],
            ),
        ]

        self.mock_llm_client.convert_to_spdx.return_value = "BSD-3-Clause"

        cleaned_metadata, changes = self.cleaner.clean_metadata(metadata_list)

        # Verify order is preserved
        assert cleaned_metadata[0].name == "package-a"
        assert cleaned_metadata[1].name == "package-b"
        assert cleaned_metadata[2].name == "package-c"

    def test_clean_metadata_returns_changes_dict_structure(self) -> None:
        """Test that changes dict has expected structure."""
        metadata_list = [
            Metadata(
                name="test-package",
                origin="https://github.com/test/package",
                local_src_path=None,
                version=None,
                license=["MIT"],
                copyright=["Copyright 2024"],
            )
        ]

        _, changes = self.cleaner.clean_metadata(metadata_list)

        assert "total_rows" in changes
        assert "modified_count" in changes
        assert "changes" in changes
        assert isinstance(changes["total_rows"], int)
        assert isinstance(changes["modified_count"], int)
        assert isinstance(changes["changes"], list)

    def test_clean_metadata_change_entry_structure(self) -> None:
        """Test that each change entry has expected structure."""
        long_license = "BSD 3-Clause License\n\nCopyright (c) 2022..."
        metadata_list = [
            Metadata(
                name="test-package",
                origin="https://github.com/test/package",
                local_src_path=None,
                version=None,
                license=[long_license],
                copyright=["Copyright 2024"],
            )
        ]

        self.mock_llm_client.convert_to_spdx.return_value = "BSD-3-Clause"

        _, changes = self.cleaner.clean_metadata(metadata_list)

        assert len(changes["changes"]) == 1
        change = changes["changes"][0]
        assert "row" in change
        assert "component" in change
        assert "origin" in change
        assert "original" in change
        assert "converted" in change
        assert change["component"] == "test-package"
        assert change["converted"] == "BSD-3-Clause"

    def test_clean_metadata_with_callback_accept(self) -> None:
        """Test cleaning with callback that accepts changes."""
        long_license = "BSD 3-Clause License\n\nCopyright (c) 2022..."
        metadata_list = [
            Metadata(
                name="test-package",
                origin="https://github.com/test/package",
                local_src_path=None,
                version=None,
                license=[long_license],
                copyright=["Copyright 2024"],
            )
        ]

        self.mock_llm_client.convert_to_spdx.return_value = "BSD-3-Clause"

        # Callback that always accepts
        callback = Mock(return_value=True)

        cleaned_metadata, changes = self.cleaner.clean_metadata(
            metadata_list, change_callback=callback
        )

        assert changes["modified_count"] == 1
        assert cleaned_metadata[0].license == ["BSD-3-Clause"]
        callback.assert_called_once()

    def test_clean_metadata_with_callback_reject(self) -> None:
        """Test cleaning with callback that rejects changes."""
        long_license = "BSD 3-Clause License\n\nCopyright (c) 2022..."
        metadata_list = [
            Metadata(
                name="test-package",
                origin="https://github.com/test/package",
                local_src_path=None,
                version=None,
                license=[long_license],
                copyright=["Copyright 2024"],
            )
        ]

        self.mock_llm_client.convert_to_spdx.return_value = "BSD-3-Clause"

        # Callback that always rejects
        callback = Mock(return_value=False)

        cleaned_metadata, changes = self.cleaner.clean_metadata(
            metadata_list, change_callback=callback
        )

        assert changes["modified_count"] == 0
        # Original license should be kept
        assert cleaned_metadata[0].license == [long_license]
        callback.assert_called_once()
