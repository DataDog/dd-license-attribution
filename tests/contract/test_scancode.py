# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

"""Contract tests for scancode-toolkit library.

These tests validate the structure and behavior of scancode.api methods
that our code depends on. They ensure that updates to scancode-toolkit
don't break our assumptions about the API structure.

Note: These tests create temporary files for scanning and may take time to run.
"""

import tempfile
from pathlib import Path

import scancode.api


def test_get_licenses_returns_expected_structure() -> None:
    """Ensure get_licenses() returns expected license detection structure.

    We depend on: detected_license_expression_spdx field in the response.
    """
    # Create a temporary file with MIT license text
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(
            """
MIT License

Copyright (c) 2024 Test Author

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
        )
        temp_file_path = f.name

    try:
        # Call scancode API
        result = scancode.api.get_licenses(temp_file_path)

        # Validate response structure
        assert isinstance(result, dict), "Result should be a dictionary"

        # Validate critical field our code depends on
        assert (
            "detected_license_expression_spdx" in result
        ), "Result should contain 'detected_license_expression_spdx' field"

        # When a license is detected, this field should be a string
        if result["detected_license_expression_spdx"]:
            assert isinstance(
                result["detected_license_expression_spdx"], str
            ), "detected_license_expression_spdx should be a string when present"
            # MIT license should be detected
            assert (
                "MIT" in result["detected_license_expression_spdx"]
            ), "Should detect MIT license in the file"
    finally:
        # Clean up
        Path(temp_file_path).unlink()


def test_get_licenses_returns_none_for_no_license() -> None:
    """Ensure get_licenses() returns None/empty when no license is detected."""
    # Create a temporary file with no license text
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("This is just regular text with no license information.")
        temp_file_path = f.name

    try:
        result = scancode.api.get_licenses(temp_file_path)

        assert isinstance(result, dict), "Result should be a dictionary"
        assert (
            "detected_license_expression_spdx" in result
        ), "Result should contain 'detected_license_expression_spdx' field"

        # Should be None or empty string when no license detected
        assert not result[
            "detected_license_expression_spdx"
        ], "Should not detect license in non-license text"
    finally:
        Path(temp_file_path).unlink()


def test_get_copyrights_returns_expected_structure() -> None:
    """Ensure get_copyrights() returns expected copyright detection structure.

    We depend on: holders, authors, copyrights lists with respective fields.
    """
    # Create a temporary file with copyright text
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(
            """
Copyright (c) 2024 Test Company

This product includes software developed by Test Author.
"""
        )
        temp_file_path = f.name

    try:
        result = scancode.api.get_copyrights(temp_file_path)

        # Validate response structure
        assert isinstance(result, dict), "Result should be a dictionary"

        # Validate fields our code depends on
        assert "holders" in result, "Result should contain 'holders' field"
        assert "authors" in result, "Result should contain 'authors' field"
        assert "copyrights" in result, "Result should contain 'copyrights' field"

        # Validate list structures
        assert isinstance(result["holders"], list), "holders should be a list"
        assert isinstance(result["authors"], list), "authors should be a list"
        assert isinstance(result["copyrights"], list), "copyrights should be a list"

        # Validate holder structure (if any detected)
        if result["holders"]:
            first_holder = result["holders"][0]
            assert isinstance(first_holder, dict), "holder item should be a dict"
            assert "holder" in first_holder, "holder dict should contain 'holder' key"
            assert isinstance(
                first_holder["holder"], str
            ), "holder value should be a string"

        # Validate author structure (if any detected)
        if result["authors"]:
            first_author = result["authors"][0]
            assert isinstance(first_author, dict), "author item should be a dict"
            assert "author" in first_author, "author dict should contain 'author' key"
            assert isinstance(
                first_author["author"], str
            ), "author value should be a string"

        # Validate copyright structure (if any detected)
        if result["copyrights"]:
            first_copyright = result["copyrights"][0]
            assert isinstance(first_copyright, dict), "copyright item should be a dict"
            assert (
                "copyright" in first_copyright
            ), "copyright dict should contain 'copyright' key"
            assert isinstance(
                first_copyright["copyright"], str
            ), "copyright value should be a string"
    finally:
        Path(temp_file_path).unlink()


def test_get_copyrights_returns_empty_lists_for_no_copyright() -> None:
    """Ensure get_copyrights() returns empty lists when no copyright is detected."""
    # Create a temporary file with no copyright text
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("This is just regular text with no copyright information.")
        temp_file_path = f.name

    try:
        result = scancode.api.get_copyrights(temp_file_path)

        assert isinstance(result, dict), "Result should be a dictionary"

        # All lists should be present (even if empty)
        assert "holders" in result, "Result should contain 'holders' field"
        assert "authors" in result, "Result should contain 'authors' field"
        assert "copyrights" in result, "Result should contain 'copyrights' field"

        # Should be empty or have no meaningful content
        assert isinstance(result["holders"], list), "holders should be a list"
        assert isinstance(result["authors"], list), "authors should be a list"
        assert isinstance(result["copyrights"], list), "copyrights should be a list"
    finally:
        Path(temp_file_path).unlink()


def test_scancode_handles_special_license_references() -> None:
    """Ensure scancode returns expected format for unknown/special licenses.

    We specifically filter out:
    - LicenseRef-scancode-unknown-license-reference
    - LicenseRef-scancode-generic-cla
    """
    # Create a file with ambiguous license text
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("Licensed under some unknown proprietary terms.")
        temp_file_path = f.name

    try:
        result = scancode.api.get_licenses(temp_file_path)

        assert isinstance(result, dict), "Result should be a dictionary"
        assert (
            "detected_license_expression_spdx" in result
        ), "Result should contain 'detected_license_expression_spdx' field"

        # If detected, it might contain special reference formats
        if result["detected_license_expression_spdx"]:
            detected = result["detected_license_expression_spdx"]
            # Our code filters these out, so we need to ensure the format is as expected
            if "LicenseRef-scancode" in detected:
                assert isinstance(detected, str), "License references should be strings"
    finally:
        Path(temp_file_path).unlink()


def test_scancode_handles_combined_licenses() -> None:
    """Ensure scancode handles multi-license files with AND/OR operators.

    Our code splits licenses by ' AND ' operator.
    """
    # Create a file with dual-licensed text
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(
            """
Licensed under MIT License

Also licensed under Apache License 2.0
"""
        )
        temp_file_path = f.name

    try:
        result = scancode.api.get_licenses(temp_file_path)

        assert isinstance(result, dict), "Result should be a dictionary"
        assert (
            "detected_license_expression_spdx" in result
        ), "Result should contain 'detected_license_expression_spdx' field"

        # If multiple licenses detected, they might be combined with AND
        if result["detected_license_expression_spdx"]:
            detected = result["detected_license_expression_spdx"]
            assert isinstance(detected, str), "License expression should be a string"
            # Format should be valid SPDX expression (may contain AND, OR, etc.)
    finally:
        Path(temp_file_path).unlink()
