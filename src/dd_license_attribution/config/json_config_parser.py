# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json
import logging
from typing import Optional

from dd_license_attribution.adaptors.os import open_file
from dd_license_attribution.artifact_management.source_code_manager import (
    MirrorSpec,
    RefType,
)
from dd_license_attribution.metadata_collector.strategies.override_strategy import (
    OverrideCollectionStrategy,
    OverrideRule,
)


class JsonConfigParser:
    """Parser for JSON configuration files used by dd-license-attribution."""

    @staticmethod
    def parse_ref_mapping(
        ref_mapping_dict: dict[str, str],
    ) -> dict[tuple[RefType, str], tuple[RefType, str]]:
        """Parse ref_mapping from JSON format to the expected tuple format.

        JSON format: {"branch:main": "branch:stephofx_eval-scripts"}
        Expected format: {(RefType.BRANCH, "main"): (RefType.BRANCH, "stephofx_eval-scripts")}

        Args:
            ref_mapping_dict: Dictionary with string keys and values in format "type:name"

        Returns:
            Dictionary with tuple keys and values representing (RefType, name) pairs

        Raises:
            ValueError: If the format is invalid or RefType is not recognized
        """
        parsed_mapping = {}
        for key, value in ref_mapping_dict.items():
            # Parse key: "branch:main" -> (RefType.BRANCH, "main")
            key_parts = key.split(":", 1)
            if len(key_parts) != 2:
                raise ValueError(
                    f"Invalid ref mapping key format: {key}. Expected format: 'type:name'"
                )
            key_type_str, key_name = key_parts
            try:
                key_type = RefType(key_type_str)
            except ValueError:
                raise ValueError(
                    f"Invalid ref type in key: {key_type_str}. Valid types: {[t.value for t in RefType]}"
                )

            # Parse value: "branch:stephofx_eval-scripts" -> (RefType.BRANCH, "stephofx_eval-scripts")
            value_parts = value.split(":", 1)
            if len(value_parts) != 2:
                raise ValueError(
                    f"Invalid ref mapping value format: {value}. Expected format: 'type:name'"
                )
            value_type_str, value_name = value_parts
            try:
                value_type = RefType(value_type_str)
            except ValueError:
                raise ValueError(
                    f"Invalid ref type in value: {value_type_str}. Valid types: {[t.value for t in RefType]}"
                )

            parsed_mapping[(key_type, key_name)] = (value_type, value_name)

        return parsed_mapping

    @staticmethod
    def load_mirror_configs(mirror_file_path: str) -> list[MirrorSpec]:
        """Load mirror configurations from a JSON file.

        Args:
            mirror_file_path: Path to the JSON file containing mirror specifications

        Returns:
            List of MirrorSpec objects

        Raises:
            FileNotFoundError: If the mirror configuration file is not found
            json.JSONDecodeError: If the JSON file is invalid
            ValueError: If the mirror configuration format is invalid
        """
        try:
            mirror_configs = json.loads(open_file(mirror_file_path))
            mirrors = []
            for config in mirror_configs:
                ref_mapping = None
                if config.get("ref_mapping"):
                    ref_mapping = JsonConfigParser.parse_ref_mapping(
                        config["ref_mapping"]
                    )
                mirrors.append(
                    MirrorSpec(
                        original_url=config["original_url"],
                        mirror_url=config["mirror_url"],
                        ref_mapping=ref_mapping,
                    )
                )
            return mirrors
        except FileNotFoundError:
            logging.error(f"Mirror configuration file not found: {mirror_file_path}")
            raise
        except json.JSONDecodeError:
            logging.error(
                f"Invalid JSON in mirror configuration file: {mirror_file_path}"
            )
            raise
        except Exception as e:
            logging.error(f"Failed to load mirror configurations: {str(e)}")
            raise

    @staticmethod
    def load_override_configs(override_file_path: str) -> list[OverrideRule]:
        """Load override configurations from a JSON file.

        Args:
            override_file_path: Path to the JSON file containing override specifications

        Returns:
            List of override rules

        Raises:
            FileNotFoundError: If the override configuration file is not found
            json.JSONDecodeError: If the JSON file is invalid
            ValueError: If the override configuration format is invalid
        """
        try:
            override_rules_json = json.loads(open_file(override_file_path))
            override_rules = OverrideCollectionStrategy.json_to_override_rules(
                override_rules_json
            )
            return override_rules
        except FileNotFoundError:
            logging.error(f"Override spec file not found: {override_file_path}")
            raise
        except json.JSONDecodeError:
            logging.error(f"Invalid JSON in override spec file: {override_file_path}")
            raise
        except Exception as e:
            logging.error(f"Error reading override spec file: {e}")
            raise
