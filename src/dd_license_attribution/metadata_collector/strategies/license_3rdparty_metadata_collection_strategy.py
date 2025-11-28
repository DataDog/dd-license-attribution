# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import ast
import csv

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (  # noqa: E501
    MetadataCollectionStrategy,
)


class License3rdPartyMetadataCollectionStrategy(MetadataCollectionStrategy):
    """
    A metadata collection strategy that reads LICENSE-3rdparty.csv files
    and converts them to Metadata objects.
    """

    def __init__(self, csv_file_path: str):
        self.csv_file_path = csv_file_path

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        with open(self.csv_file_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        if not rows:
            return metadata

        if None in rows[0].keys():
            raise ValueError("Invalid CSV format")
        # Create a case-insensitive mapping of column names to actual
        # column names. This allows CSV files with columns like
        # "Component", "LICENSE", etc. to work
        column_mapping = {col.lower(): col for col in rows[0].keys()}

        required_columns = {"component", "origin", "license", "copyright"}
        missing_columns = required_columns - column_mapping.keys()

        if missing_columns:
            columns_str = ", ".join(required_columns)
            raise ValueError(f"CSV file must contain columns: {columns_str}")

        # Get the actual column names from the mapping
        license_col = column_mapping["license"]
        copyright_col = column_mapping["copyright"]
        component_col = column_mapping["component"]
        origin_col = column_mapping["origin"]

        updated_metadata = metadata.copy()
        for row in rows:
            # Parse the license and copyright fields
            # (they are string representations of lists)
            try:
                license_list = (
                    ast.literal_eval(row[license_col]) if row[license_col] else []
                )
                copyright_list = (
                    ast.literal_eval(row[copyright_col]) if row[copyright_col] else []
                )
            except (ValueError, SyntaxError):
                # If parsing fails, treat as empty
                license_list = []
                copyright_list = []

            # Check if metadata with this name already exists to augment existing metadata
            existing = next(
                (m for m in metadata if m.name == row[component_col]),
                None,
            )

            if existing is not None:
                # Merge with existing metadata, keeping existing
                # non-empty values
                if not existing.origin:
                    existing.origin = row[origin_col]
                if not existing.license:
                    existing.license = license_list
                if not existing.copyright:
                    existing.copyright = copyright_list
            else:
                # Create new Metadata object
                meta = Metadata(
                    name=row[component_col],
                    origin=row[origin_col],
                    local_src_path=None,
                    version=None,
                    license=license_list,
                    copyright=copyright_list,
                )
                updated_metadata.append(meta)

        return updated_metadata
