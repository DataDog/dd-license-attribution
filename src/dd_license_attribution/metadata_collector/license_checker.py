# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import logging

# Get application-specific logger
logger = logging.getLogger("dd_license_attribution")

from dd_license_attribution.metadata_collector.metadata import Metadata


class LicenseChecker:
    """A class to check for cautionary licenses in a list of Metadata objects."""

    def __init__(self, cautionary_licenses: list[str]) -> None:
        self._cautionary_licenses = cautionary_licenses

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

    def _is_cautionary_license(self, license_text: str) -> bool:
        license_text_upper = license_text.upper()
        return any(
            license_text_upper.startswith(keyword.upper())
            for keyword in self._cautionary_licenses
        )
