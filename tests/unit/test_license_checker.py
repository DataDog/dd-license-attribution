# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from unittest.mock import patch

from dd_license_attribution.config.cli_configs import default_config
from dd_license_attribution.metadata_collector.license_checker import LicenseChecker
from dd_license_attribution.metadata_collector.metadata import Metadata


def test_is_cautionary_license_with_gpl() -> None:
    """Test that GPL licenses are correctly identified as cautionary."""
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    assert checker._is_cautionary_license("GPL-3.0")
    assert checker._is_cautionary_license("GPL-2.0")
    assert checker._is_cautionary_license("GPL")


def test_is_cautionary_license_with_eupl() -> None:
    """Test that EUPL licenses are correctly identified as cautionary."""
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    assert checker._is_cautionary_license("EUPL-1.2")
    assert checker._is_cautionary_license("EUPL")


def test_is_cautionary_license_with_agpl() -> None:
    """Test that AGPL licenses are correctly identified as cautionary."""
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    assert checker._is_cautionary_license("AGPL-3.0")
    assert checker._is_cautionary_license("AGPL")


def test_is_cautionary_license_with_non_cautionary() -> None:
    """Test that non-cautionary licenses are correctly identified."""
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    assert not checker._is_cautionary_license("MIT")
    assert not checker._is_cautionary_license("Apache-2.0")
    assert not checker._is_cautionary_license("BSD-3-Clause")
    assert not checker._is_cautionary_license("LGPL-3.0")


def test_is_cautionary_license_case_insensitive() -> None:
    """Test that license detection is case insensitive."""
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    assert checker._is_cautionary_license("gpl-3.0")
    assert checker._is_cautionary_license("eupl-1.2")
    assert checker._is_cautionary_license("agpl-3.0")


def test_check_cautionary_licenses_with_empty_metadata_list() -> None:
    """Test that checking an empty metadata list exists fast."""
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    with patch.object(checker, "_is_cautionary_license") as mock_is_cautionary:
        checker.check_cautionary_licenses([])
        mock_is_cautionary.assert_not_called()


def test_check_cautionary_licenses_with_no_license() -> None:
    """Test that metadata with no license exists fast."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="test",
        local_src_path=None,
        license=[],
        copyright=[],
    )
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    with patch.object(checker, "_is_cautionary_license") as mock_is_cautionary:
        checker.check_cautionary_licenses([metadata])
        mock_is_cautionary.assert_not_called()


def test_check_cautionary_licenses_with_non_cautionary_license() -> None:
    """Test that non-cautionary licenses don't raise any warnings."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="test",
        local_src_path=None,
        license=["MIT"],
        copyright=[],
    )
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    with patch.object(checker, "_is_cautionary_license") as mock_is_cautionary:
        mock_is_cautionary.return_value = False
        checker.check_cautionary_licenses([metadata])
        mock_is_cautionary.assert_called_once_with("MIT")
        with patch(
            "dd_license_attribution.metadata_collector.license_checker.logger.warning"
        ) as mock_logging:
            mock_logging.assert_not_called()


def test_check_cautionary_licenses_with_cautionary_license() -> None:
    """Test that cautionary licenses raise appropriate warnings."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="test",
        local_src_path=None,
        license=["GPL-3.0"],
        copyright=[],
    )
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    with patch.object(checker, "_is_cautionary_license") as mock_is_cautionary:
        mock_is_cautionary.return_value = True
        with patch(
            "dd_license_attribution.metadata_collector.license_checker.logger.warning"
        ) as mock_logging:
            checker.check_cautionary_licenses([metadata])
            mock_is_cautionary.assert_called_once_with("GPL-3.0")
            mock_logging.assert_called_once()


def test_check_cautionary_licenses_with_multiple_licenses() -> None:
    """Test that checking multiple licenses works correctly."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="test",
        local_src_path=None,
        license=["MIT", "GPL-3.0", "Apache-2.0"],
        copyright=[],
    )
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    with patch.object(checker, "_is_cautionary_license") as mock_is_cautionary:
        mock_is_cautionary.side_effect = [False, True, False]
        with patch(
            "dd_license_attribution.metadata_collector.license_checker.logger.warning"
        ) as mock_logging:
            checker.check_cautionary_licenses([metadata])
            assert mock_is_cautionary.call_count == 3
            mock_logging.assert_called_once()


def test_check_cautionary_licenses_with_all_cautionary_keywords() -> None:
    """Test that all cautionary keywords are detected correctly."""
    metadata_list = [
        Metadata(
            name=f"test-package-{i}",
            version="1.0.0",
            origin="test",
            local_src_path=None,
            license=[f"{keyword}-3.0"],
            copyright=[],
        )
        for i, keyword in enumerate(default_config.preset_cautionary_licenses)
    ]
    checker = LicenseChecker(default_config.preset_cautionary_licenses)
    with patch.object(checker, "_is_cautionary_license") as mock_is_cautionary:
        mock_is_cautionary.return_value = True
        with patch(
            "dd_license_attribution.metadata_collector.license_checker.logger.warning"
        ) as mock_logging:
            checker.check_cautionary_licenses(metadata_list)
            assert mock_is_cautionary.call_count == len(
                default_config.preset_cautionary_licenses
            )
            assert mock_logging.call_count == len(
                default_config.preset_cautionary_licenses
            )
