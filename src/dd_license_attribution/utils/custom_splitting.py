# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
#
# This product includes software developed at Datadog
# (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import csv
from io import StringIO


class CustomSplit:
    def __init__(self, protected_terms: list[str] | None = None):
        """
        Initialize CustomSplit with optional protected terms.

        Args:
            protected_terms: List of terms that should not be split.
                           If None, no term-based protection is applied.
        """
        self.protected_terms = protected_terms or []

    def custom_split(self, input_string: str, delimiter: str = ",") -> list[str]:
        """
        Parse a delimited string with support for quoted values and
        protected terms.

        This method combines CSV parsing (for quote handling) with
        protected terms logic.
        """

        if not input_string.strip():
            return []

        try:
            reader = csv.reader(
                StringIO(input_string), delimiter=delimiter, skipinitialspace=True
            )
            parsed_values = next(reader)
            parsed_values = [v.strip() for v in parsed_values if v.strip()]
        except (csv.Error, StopIteration):
            # If CSV parsing fails, fall back to string split
            parsed_values = [
                v.strip() for v in input_string.split(delimiter) if v.strip()
            ]

        if self.protected_terms:
            # Re-merge items that should be protected
            result: list[str] = []
            for value in parsed_values:
                if result and not self._should_split(value):
                    # This value should be merged with the previous one
                    result[-1] += f"{delimiter} {value}"
                else:
                    result.append(value)
            parsed_values = result

        return parsed_values

    def _should_split(self, text: str) -> bool:
        return not any(
            text.lower().startswith(string) for string in self.protected_terms
        )
