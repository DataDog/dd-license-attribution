# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

# Utility functions for license text processing


def is_long_license(license_text: str) -> bool:
    """
    Check if a license text is a long description that should not be split or processed as a simple identifier.

    Long licenses typically contain the full license text rather than just an SPDX identifier.
    This helps distinguish between:
    - Short SPDX identifiers: "MIT", "BSD-3-Clause", "Apache-2.0"
    - Long license text: Full license content with newlines and extensive text

    Args:
        license_text: The license text to check

    Returns:
        True if the license text is long (contains newlines or is longer than 50 characters),
        False if it appears to be a short SPDX identifier
    """
    # Consider it long if it has newlines or is longer than 50 characters
    # (typical SPDX IDs are short like "MIT", "BSD-3-Clause", "Apache-2.0")
    return "\n" in license_text or len(license_text) > 50
