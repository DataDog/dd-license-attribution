# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import re

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


class CleanupCopyrightMetadataStrategy(MetadataCollectionStrategy):

    def remove_unnecessary_strings(self, copyright_text: str) -> str:
        """
        Remove all occurrences of "copyright" and "(c)" from the given text
        Remove all occurences of years in the format YYYY-YYYY or YYYY or YYYY - YYYY. Also remove YYYY - present and YYYY-present

        """
        return re.sub(
            r"copyright(?:ed)?|\(c\)|\b\d{4}(?:\s?-\s?(?:\d{4}|present))?\b",
            "",
            copyright_text,
            flags=re.IGNORECASE,
        )

    def _process_metadata(self, meta: Metadata) -> Metadata:
        if not meta.copyright:
            return meta

        cleaned_copyrights = []
        for copyright_item in meta.copyright:

            if not copyright_item:
                continue

            one_processed_item = self.remove_unnecessary_strings(copyright_item)
            one_processed_item = " ".join(one_processed_item.split())

            if one_processed_item:
                cleaned_copyrights.append(one_processed_item)

        cleaned_copyrights = sorted(list(set(cleaned_copyrights)))
        meta.copyright = cleaned_copyrights
        return meta

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        return [self._process_metadata(meta) for meta in metadata]
