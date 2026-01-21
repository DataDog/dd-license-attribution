# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

# SPDX license cleaner that converts long license descriptions to SPDX identifiers

import logging
from typing import Any, Callable

from dd_license_attribution.license_cleaner.llm_client import LLMClient
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.utils.license_utils import is_long_license

logger = logging.getLogger(__name__)


class SPDXCleaner:
    """Cleans license descriptions by converting them to SPDX identifiers."""

    def __init__(self, llm_client: LLMClient) -> None:
        """
        Initialize the SPDX cleaner.

        Args:
            llm_client: LLM client to use for license text conversion
        """
        self.llm_client = llm_client
        logger.debug("Initialized SPDX cleaner")

    def clean_metadata(
        self,
        metadata_list: list[Metadata],
        change_callback: Callable[[dict[str, Any]], bool] | None = None,
    ) -> tuple[list[Metadata], dict[str, Any]]:
        """
        Clean license descriptions in metadata list.

        Args:
            metadata_list: List of Metadata objects to clean
            change_callback: Optional callback function called for each conversion.
                           Receives change dict, returns True to apply, False to skip.
                           If None, all changes are applied automatically.

        Returns:
            A tuple of (cleaned_metadata_list, changes_dict) where changes_dict
            contains information about the changes made
        """
        logger.info("Starting license cleaning process")

        changes: dict[str, Any] = {"total_rows": len(metadata_list), "changes": []}
        modified_count = 0

        # Process each metadata object
        for idx, metadata in enumerate(metadata_list):
            # Clean each license in the list
            cleaned_licenses: list[str] = []
            row_changed = False

            for license_text in metadata.license:
                if is_long_license(license_text):
                    logger.info(
                        "Converting long license text to SPDX for component: %s",
                        metadata.name,
                    )

                    spdx_id = self.llm_client.convert_to_spdx(license_text)

                    # Prepare change information
                    change_info = {
                        "row": idx,
                        "component": metadata.name,
                        "origin": metadata.origin,
                        "original": (
                            license_text[:100] + "..."
                            if len(license_text) > 100
                            else license_text
                        ),
                        "original_full": license_text,
                        "converted": spdx_id,
                    }

                    # If callback provided, ask for confirmation for this specific change
                    apply_change = True
                    if change_callback is not None:
                        apply_change = change_callback(change_info)

                    if apply_change:
                        cleaned_licenses.append(spdx_id)
                        changes["changes"].append(change_info)
                        row_changed = True
                    else:
                        # Keep original if user rejected
                        cleaned_licenses.append(license_text)
                else:
                    cleaned_licenses.append(license_text)

            if row_changed:
                # Update the metadata object with cleaned licenses
                metadata.license = cleaned_licenses
                modified_count += 1

        changes["modified_count"] = modified_count
        logger.info("Completed cleaning process. Modified %d rows", modified_count)

        return metadata_list, changes
