# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

# Unit tests for license utilities

from dd_license_attribution.utils.license_utils import is_long_license


class TestIsLongLicense:
    """Test is_long_license utility function."""

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
        """Test is_long_license with short SPDX identifiers."""
        assert is_long_license("MIT") is False
        assert is_long_license("BSD-3-Clause") is False
        assert is_long_license("Apache-2.0") is False
        assert is_long_license("GPL-3.0-or-later") is False

    def test_is_long_license_with_empty_string(self) -> None:
        """Test is_long_license with empty string."""
        assert is_long_license("") is False

    def test_is_long_license_at_boundary(self) -> None:
        """Test is_long_license at exactly 50 characters."""
        exactly_50_chars = "a" * 50
        assert is_long_license(exactly_50_chars) is False

        just_over_50_chars = "a" * 51
        assert is_long_license(just_over_50_chars) is True

    def test_is_long_license_with_full_bsd_license(self) -> None:
        """Test is_long_license with full BSD license text."""
        full_license = """BSD 3-Clause License

Copyright (c) 2022, Jupyter
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer.
"""
        assert is_long_license(full_license) is True

    def test_is_long_license_with_comma_separated_licenses(self) -> None:
        """Test is_long_license with comma-separated SPDX identifiers."""
        # These should not be considered long licenses
        assert is_long_license("MIT, Apache-2.0") is False
        assert is_long_license("BSD-3-Clause, GPL-2.0") is False
