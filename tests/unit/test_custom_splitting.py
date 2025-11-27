# Unless explicitly stated otherwise all files in this repository are
# licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog
# (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

from dd_license_attribution.utils.custom_splitting import CustomSplit


def test_custom_split_simple_values() -> None:
    """Test CustomSplit with simple comma-separated values."""
    splitter = CustomSplit()
    result = splitter.custom_split("MIT, Apache-2.0, BSD-3-Clause")
    assert result == ["MIT", "Apache-2.0", "BSD-3-Clause"]


def test_custom_split_quoted_values() -> None:
    """Test CustomSplit with quoted values containing commas."""
    splitter = CustomSplit()
    result = splitter.custom_split('"Datadog, Inc.", Google LLC')
    assert result == ["Datadog, Inc.", "Google LLC"]


def test_custom_split_with_protected_terms() -> None:
    """Test CustomSplit with protected terms."""
    splitter = CustomSplit(protected_terms=["inc."])
    result = splitter.custom_split("Datadog, Inc., Google LLC")
    assert result == ["Datadog, Inc.", "Google LLC"]


def test_custom_split_quotes_and_protected_terms() -> None:
    """Test CustomSplit with both quotes and protected terms."""
    splitter = CustomSplit(protected_terms=["llc"])
    result = splitter.custom_split('"Datadog, Inc.", Google, LLC, Apple')
    assert result == ["Datadog, Inc.", "Google, LLC", "Apple"]


def test_custom_split_protected_terms_without_quotes() -> None:
    """Test that protected terms work without quotes."""
    splitter = CustomSplit(protected_terms=["corp."])
    input_str = "Test, Corp., Google"
    result = splitter.custom_split(input_str)
    assert result == ["Test, Corp.", "Google"]


def test_custom_split_protected_terms_blank() -> None:
    """Test that protected terms work without quotes and blank values."""
    splitter = CustomSplit(protected_terms=["corp."])
    input_str = "Test, Corp., , Google"
    result = splitter.custom_split(input_str)
    assert result == ["Test, Corp.", "Google"]


def test_custom_split_empty_string() -> None:
    """Test CustomSplit with empty string."""
    splitter = CustomSplit()
    assert splitter.custom_split("") == []
    assert splitter.custom_split("   ") == []


def test_custom_split_different_delimiter() -> None:
    """Test CustomSplit with a different delimiter."""
    splitter = CustomSplit()
    result = splitter.custom_split("MIT; Apache-2.0; BSD", delimiter=";")
    assert result == ["MIT", "Apache-2.0", "BSD"]


def test_custom_split_no_protected_terms() -> None:
    """Test CustomSplit initialized without protected terms."""
    splitter = CustomSplit(protected_terms=None)
    result = splitter.custom_split("MIT, Apache-2.0")
    assert result == ["MIT", "Apache-2.0"]
