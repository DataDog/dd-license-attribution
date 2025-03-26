from unittest.mock import patch

from ospo_tools.metadata_collector.license_checker import LicenseChecker
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.config.cli_configs import default_config


def test_is_copyleft_license_with_gpl() -> None:
    """Test that GPL licenses are correctly identified as copyleft."""
    checker = LicenseChecker()
    assert checker._is_copyleft_license("GPL-3.0")
    assert checker._is_copyleft_license("GPL-2.0")
    assert checker._is_copyleft_license("GPL")


def test_is_copyleft_license_with_eupl() -> None:
    """Test that EUPL licenses are correctly identified as copyleft."""
    checker = LicenseChecker()
    assert checker._is_copyleft_license("EUPL-1.2")
    assert checker._is_copyleft_license("EUPL")


def test_is_copyleft_license_with_agpl() -> None:
    """Test that AGPL licenses are correctly identified as copyleft."""
    checker = LicenseChecker()
    assert checker._is_copyleft_license("AGPL-3.0")
    assert checker._is_copyleft_license("AGPL")


def test_is_copyleft_license_with_non_copyleft() -> None:
    """Test that non-copyleft licenses are correctly identified."""
    checker = LicenseChecker()
    assert not checker._is_copyleft_license("MIT")
    assert not checker._is_copyleft_license("Apache-2.0")
    assert not checker._is_copyleft_license("BSD-3-Clause")
    assert not checker._is_copyleft_license("LGPL-3.0")


def test_is_copyleft_license_case_insensitive() -> None:
    """Test that license detection is case insensitive."""
    checker = LicenseChecker()
    assert checker._is_copyleft_license("gpl-3.0")
    assert checker._is_copyleft_license("eupl-1.2")
    assert checker._is_copyleft_license("agpl-3.0")


def test_check_copyleft_licenses_with_empty_metadata_list() -> None:
    """Test that checking an empty metadata list exists fast."""
    checker = LicenseChecker()
    with patch.object(checker, "_is_copyleft_license") as mock_is_copyleft:
        checker.check_copyleft_licenses([])
        mock_is_copyleft.assert_not_called()


def test_check_copyleft_licenses_with_no_license() -> None:
    """Test that metadata with no license exists fast."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="test",
        local_src_path=None,
        license=[],
        copyright=[],
    )
    checker = LicenseChecker()
    with patch.object(checker, "_is_copyleft_license") as mock_is_copyleft:
        checker.check_copyleft_licenses([metadata])
        mock_is_copyleft.assert_not_called()


def test_check_copyleft_licenses_with_non_copyleft_license() -> None:
    """Test that non-copyleft licenses don't raise any warnings."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="test",
        local_src_path=None,
        license=["MIT"],
        copyright=[],
    )
    checker = LicenseChecker()
    with patch.object(checker, "_is_copyleft_license") as mock_is_copyleft:
        mock_is_copyleft.return_value = False
        checker.check_copyleft_licenses([metadata])
        mock_is_copyleft.assert_called_once_with("MIT")
        with patch("builtins.print") as mock_print:
            mock_print.assert_not_called()


def test_check_copyleft_licenses_with_copyleft_license() -> None:
    """Test that copyleft licenses raise appropriate warnings."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="test",
        local_src_path=None,
        license=["GPL-3.0"],
        copyright=[],
    )
    checker = LicenseChecker()
    with patch.object(checker, "_is_copyleft_license") as mock_is_copyleft:
        mock_is_copyleft.return_value = True
        with patch("builtins.print") as mock_print:
            checker.check_copyleft_licenses([metadata])
            mock_is_copyleft.assert_called_once_with("GPL-3.0")
            mock_print.assert_called_once()


def test_check_copyleft_licenses_with_multiple_licenses() -> None:
    """Test that checking multiple licenses works correctly."""
    metadata = Metadata(
        name="test-package",
        version="1.0.0",
        origin="test",
        local_src_path=None,
        license=["MIT", "GPL-3.0", "Apache-2.0"],
        copyright=[],
    )
    checker = LicenseChecker()
    with patch.object(checker, "_is_copyleft_license") as mock_is_copyleft:
        mock_is_copyleft.side_effect = [False, True, False]
        with patch("builtins.print") as mock_print:
            checker.check_copyleft_licenses([metadata])
            assert mock_is_copyleft.call_count == 3
            mock_print.assert_called_once()


def test_check_copyleft_licenses_with_all_copyleft_keywords() -> None:
    """Test that all copyleft keywords are detected correctly."""
    metadata_list = [
        Metadata(
            name=f"test-package-{i}",
            version="1.0.0",
            origin="test",
            local_src_path=None,
            license=[f"{keyword}-3.0"],
            copyright=[],
        )
        for i, keyword in enumerate(default_config.preset_copyleft_licenses)
    ]
    checker = LicenseChecker()
    with patch.object(checker, "_is_copyleft_license") as mock_is_copyleft:
        mock_is_copyleft.return_value = True
        with patch("builtins.print") as mock_print:
            checker.check_copyleft_licenses(metadata_list)
            assert mock_is_copyleft.call_count == len(
                default_config.preset_copyleft_licenses
            )
            assert mock_print.call_count == len(default_config.preset_copyleft_licenses)
