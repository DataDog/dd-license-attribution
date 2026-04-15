# SPDX-License-Identifier: Apache-2.0
#
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
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
    assert checker._is_cautionary_license("GPL-3.0")
    assert checker._is_cautionary_license("GPL-2.0")
    assert checker._is_cautionary_license("GPL")


def test_is_cautionary_license_with_eupl() -> None:
    """Test that EUPL licenses are correctly identified as cautionary."""
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
    assert checker._is_cautionary_license("EUPL-1.2")
    assert checker._is_cautionary_license("EUPL")


def test_is_cautionary_license_with_agpl() -> None:
    """Test that AGPL licenses are correctly identified as cautionary."""
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
    assert checker._is_cautionary_license("AGPL-3.0")
    assert checker._is_cautionary_license("AGPL")


def test_is_cautionary_license_with_non_cautionary() -> None:
    """Test that non-cautionary licenses are correctly identified."""
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
    assert not checker._is_cautionary_license("MIT")
    assert not checker._is_cautionary_license("Apache-2.0")
    assert not checker._is_cautionary_license("BSD-3-Clause")
    assert not checker._is_cautionary_license("LGPL-3.0")


def test_is_cautionary_license_case_insensitive() -> None:
    """Test that license detection is case insensitive."""
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
    assert checker._is_cautionary_license("gpl-3.0")
    assert checker._is_cautionary_license("eupl-1.2")
    assert checker._is_cautionary_license("agpl-3.0")


def test_check_cautionary_licenses_with_empty_metadata_list() -> None:
    """Test that checking an empty metadata list exists fast."""
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
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
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
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
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
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
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
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
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
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
    checker = LicenseChecker(
        default_config.preset_cautionary_licenses, default_config.recognized_licenses
    )
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


# ── SPDX ID validation ────────────────────────────────────────────────────────


def _make_checker() -> LicenseChecker:
    return LicenseChecker(
        default_config.preset_cautionary_licenses,
        default_config.recognized_licenses,
    )


def _make_metadata(license_values: list[str]) -> Metadata:
    return Metadata(
        name="test-package",
        version="1.0.0",
        origin="test",
        local_src_path=None,
        license=license_values,
        copyright=[],
    )


# _is_osi_approved_spdx_expression -------------------------------------------


def test_is_osi_approved_spdx_expression_mit() -> None:
    """Simple OSI-approved SPDX identifier passes."""
    checker = _make_checker()
    assert checker._is_osi_approved_spdx_expression("MIT")


def test_is_osi_approved_spdx_expression_apache() -> None:
    checker = _make_checker()
    assert checker._is_osi_approved_spdx_expression("Apache-2.0")


def test_is_osi_approved_spdx_expression_compound_or() -> None:
    """OR compound of two OSI identifiers passes."""
    checker = _make_checker()
    assert checker._is_osi_approved_spdx_expression("MIT OR Apache-2.0")


def test_is_osi_approved_spdx_expression_compound_and() -> None:
    """AND compound of OSI identifiers passes."""
    checker = _make_checker()
    assert checker._is_osi_approved_spdx_expression("Apache-2.0 AND MIT")


def test_is_osi_approved_spdx_expression_with_exception() -> None:
    """WITH exception expression: only the license part is checked against OSI list."""
    checker = _make_checker()
    assert checker._is_osi_approved_spdx_expression(
        "GPL-2.0-or-later WITH GCC-exception-3.1"
    )


def test_is_osi_approved_spdx_expression_non_osi_spdx() -> None:
    """Valid SPDX identifier that is NOT OSI-approved returns False."""
    checker = _make_checker()
    # CC-BY-4.0 is a valid SPDX ID but is not OSI-approved
    assert not checker._is_osi_approved_spdx_expression("CC-BY-4.0")


def test_is_osi_approved_spdx_expression_compound_with_non_osi() -> None:
    """Compound expression mixing OSI and non-OSI identifiers returns False."""
    checker = _make_checker()
    assert not checker._is_osi_approved_spdx_expression("Apache-2.0 AND CC-BY-4.0")


def test_is_osi_approved_spdx_expression_invalid_syntax() -> None:
    """Malformed string that is not a valid SPDX expression returns False."""
    checker = _make_checker()
    assert not checker._is_osi_approved_spdx_expression("MIT License")


def test_is_osi_approved_spdx_expression_license_ref() -> None:
    """LicenseRef-* custom identifiers are not OSI-approved."""
    checker = _make_checker()
    assert not checker._is_osi_approved_spdx_expression(
        "LicenseRef-scancode-other-permissive"
    )


def test_is_osi_approved_spdx_expression_deprecated_gpl() -> None:
    """Deprecated GPL-2.0 alias is included in the OSI set for compatibility."""
    checker = _make_checker()
    assert checker._is_osi_approved_spdx_expression("GPL-2.0")


def test_is_osi_approved_spdx_expression_lgpl_or_later() -> None:
    checker = _make_checker()
    assert checker._is_osi_approved_spdx_expression("LGPL-3.0-or-later")


# check_spdx_ids ---------------------------------------------------------------


def test_check_spdx_ids_empty_list_no_warning() -> None:
    """Empty metadata list emits no warnings."""
    checker = _make_checker()
    with patch(
        "dd_license_attribution.metadata_collector.license_checker.logger.warning"
    ) as mock_warn:
        checker.check_spdx_ids([])
        mock_warn.assert_not_called()


def test_check_spdx_ids_no_license_no_warning() -> None:
    """Package with empty license list emits no warnings."""
    checker = _make_checker()
    metadata = _make_metadata([])
    with patch(
        "dd_license_attribution.metadata_collector.license_checker.logger.warning"
    ) as mock_warn:
        checker.check_spdx_ids([metadata])
        mock_warn.assert_not_called()


def test_check_spdx_ids_valid_osi_no_warning() -> None:
    """Valid OSI-approved SPDX ID emits no warning."""
    checker = _make_checker()
    metadata = _make_metadata(["MIT"])
    with patch(
        "dd_license_attribution.metadata_collector.license_checker.logger.warning"
    ) as mock_warn:
        checker.check_spdx_ids([metadata])
        mock_warn.assert_not_called()


def test_check_spdx_ids_valid_compound_no_warning() -> None:
    """Valid compound SPDX expression emits no warning."""
    checker = _make_checker()
    metadata = _make_metadata(["Apache-2.0 OR BSD-3-Clause"])
    with patch(
        "dd_license_attribution.metadata_collector.license_checker.logger.warning"
    ) as mock_warn:
        checker.check_spdx_ids([metadata])
        mock_warn.assert_not_called()


def test_check_spdx_ids_non_osi_emits_warning() -> None:
    """Non-OSI SPDX identifier emits exactly one warning."""
    checker = _make_checker()
    metadata = _make_metadata(["CC-BY-4.0"])
    with patch(
        "dd_license_attribution.metadata_collector.license_checker.logger.warning"
    ) as mock_warn:
        checker.check_spdx_ids([metadata])
        mock_warn.assert_called_once()
        # Warning message mentions both remediation commands
        warning_msg = mock_warn.call_args[0][0]
        assert "generate-overrides" in warning_msg
        assert "clean-spdx-id" in warning_msg


def test_check_spdx_ids_malformed_string_emits_warning() -> None:
    """Malformed license string (not valid SPDX) emits a warning."""
    checker = _make_checker()
    metadata = _make_metadata(["Apache License"])
    with patch(
        "dd_license_attribution.metadata_collector.license_checker.logger.warning"
    ) as mock_warn:
        checker.check_spdx_ids([metadata])
        mock_warn.assert_called_once()


def test_check_spdx_ids_multiple_licenses_mixed() -> None:
    """Package with one valid and one invalid license emits one warning."""
    checker = _make_checker()
    metadata = _make_metadata(["MIT", "CC-BY-4.0"])
    with patch(
        "dd_license_attribution.metadata_collector.license_checker.logger.warning"
    ) as mock_warn:
        checker.check_spdx_ids([metadata])
        mock_warn.assert_called_once()


def test_check_spdx_ids_multiple_packages_warns_per_bad_license() -> None:
    """Each package with a bad license gets its own warning."""
    checker = _make_checker()
    metadata_list = [
        _make_metadata(["MIT"]),
        _make_metadata(["CC-BY-4.0"]),
        _make_metadata(["Apache License"]),
        _make_metadata(["Apache-2.0"]),
    ]
    with patch(
        "dd_license_attribution.metadata_collector.license_checker.logger.warning"
    ) as mock_warn:
        checker.check_spdx_ids(metadata_list)
        assert mock_warn.call_count == 2


def test_check_spdx_ids_license_ref_emits_warning() -> None:
    """LicenseRef-* custom identifiers are not OSI-approved and emit a warning."""
    checker = _make_checker()
    metadata = _make_metadata(["LicenseRef-scancode-other-permissive"])
    with patch(
        "dd_license_attribution.metadata_collector.license_checker.logger.warning"
    ) as mock_warn:
        checker.check_spdx_ids([metadata])
        mock_warn.assert_called_once()


def test_recognized_licenses_contains_common_osi_licenses() -> None:
    """Spot-check that the recognized list contains well-known OSI-approved licenses."""
    for spdx_id in [
        "MIT",
        "Apache-2.0",
        "GPL-3.0-only",
        "LGPL-2.1-or-later",
        "ISC",
        "BSD-3-Clause",
    ]:
        assert (
            spdx_id in default_config.recognized_licenses
        ), f"{spdx_id} missing from recognized_licenses"


def test_recognized_licenses_excludes_non_osi() -> None:
    """Spot-check that non-OSI licenses are absent from the recognized list."""
    for spdx_id in ["CC-BY-4.0", "BUSL-1.1", "SSPL-1.0", "CC-BY-SA-4.0"]:
        assert (
            spdx_id not in default_config.recognized_licenses
        ), f"{spdx_id} should not be in recognized_licenses"
