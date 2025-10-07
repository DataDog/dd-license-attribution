# Unless explicitly stated otherwise all files in this repository are licensed
# under the Apache License Version 2.0.
#
# This product includes software developed at Datadog
# (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.


class CustomSplit:
    def __init__(self, protected_terms: list[str]):
        self.protected_terms = protected_terms

    def custom_split(self, text: str, delimiter: str) -> list[str]:
        parts = text.split(delimiter)
        result = [parts[0].strip()]
        for string in parts[1:]:
            string = string.strip()
            if self._should_split(string):
                result.append(string)
            else:
                result[-1] += f"{delimiter} {string}"
        return result

    def _should_split(self, text: str) -> bool:
        return not any(
            text.lower().startswith(string) for string in self.protected_terms
        )
