# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import logging

from license_expression import (
    ExpressionError,
    LicenseSymbol,
    LicenseWithExceptionSymbol,
    get_spdx_licensing,
)

from dd_license_attribution.metadata_collector.metadata import Metadata

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")

_spdx_licensing = get_spdx_licensing()


class LicenseChecker:
    """A class to check for cautionary licenses in a list of Metadata objects."""

    def __init__(
        self,
        cautionary_licenses: list[str],
        recognized_licenses: frozenset[str],
    ) -> None:
        self._cautionary_licenses = cautionary_licenses
        self._recognized_licenses = recognized_licenses

    def check_cautionary_licenses(self, metadata_list: list[Metadata]) -> None:
        for metadata in metadata_list:
            if not metadata.license:
                continue

            for license_text in metadata.license:
                if self._is_cautionary_license(license_text):
                    msg = "Package {} has a license ({}) that is in the list of cautionary licenses. Double check that the license is compatible with your project.".format(
                        metadata.name, license_text
                    )
                    logger.warning(msg)

    def check_spdx_ids(self, metadata_list: list[Metadata]) -> None:
        """Warn about licenses that are not OSI-approved SPDX identifiers.

        For each package, each license string is checked against the set of
        OSI-approved SPDX identifiers. A warning is emitted for any value that
        is not a valid SPDX expression composed entirely of OSI-approved
        identifiers.
        """
        for metadata in metadata_list:
            if not metadata.license:
                continue
            for license_text in metadata.license:
                if not self._is_osi_approved_spdx_expression(license_text):
                    logger.warning(
                        "Package %s has a license (%s) that is not a properly written SPDX "
                        "expression composed entirely of OSI-approved identifiers. Using a "
                        "non-OSI-approved license may be acceptable depending on your project's "
                        "requirements. To address this, use 'generate-overrides' for interactive "
                        "correction or 'clean-spdx-id' for AI-assisted cleanup.",
                        metadata.name,
                        license_text,
                    )

    def _is_osi_approved_spdx_expression(self, license_text: str) -> bool:
        """Return True if license_text is a valid SPDX expression whose every
        license identifier is OSI-approved."""
        try:
            parsed = _spdx_licensing.parse(license_text, validate=True)
        except ExpressionError:
            return False
        for sym in parsed.symbols:
            if isinstance(sym, LicenseWithExceptionSymbol):
                key = sym.license_symbol.key
            elif isinstance(sym, LicenseSymbol):
                key = sym.key
            else:
                return False
            if key not in self._recognized_licenses:
                return False
        return True

    def _is_cautionary_license(self, license_text: str) -> bool:
        license_text_upper = license_text.upper()
        return any(
            license_text_upper.startswith(keyword.upper())
            for keyword in self._cautionary_licenses
        )
