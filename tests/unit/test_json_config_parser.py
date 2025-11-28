# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json
import tempfile
from unittest.mock import Mock, patch

import pytest

from dd_license_attribution.artifact_management.source_code_manager import RefType
from dd_license_attribution.config.json_config_parser import JsonConfigParser
from dd_license_attribution.metadata_collector.strategies.override_strategy import (
    OverrideRule,
    OverrideTargetField,
    OverrideType,
)


class TestJsonConfigParser:
    def test_parse_ref_mapping_valid(self) -> None:
        """Test parsing valid ref mapping."""
        ref_mapping_dict = {
            "branch:main": "branch:stephofx_eval-scripts",
            "tag:v1.0": "branch:development",
        }

        result = JsonConfigParser.parse_ref_mapping(ref_mapping_dict)

        expected = {
            (RefType.BRANCH, "main"): (RefType.BRANCH, "stephofx_eval-scripts"),
            (RefType.TAG, "v1.0"): (RefType.BRANCH, "development"),
        }
        assert result == expected

    def test_parse_ref_mapping_invalid_key_format(self) -> None:
        """Test parsing ref mapping with invalid key format."""
        ref_mapping_dict = {"invalid_key": "branch:main"}

        with pytest.raises(ValueError, match="Invalid ref mapping key format"):
            JsonConfigParser.parse_ref_mapping(ref_mapping_dict)

    def test_parse_ref_mapping_invalid_value_format(self) -> None:
        """Test parsing ref mapping with invalid value format."""
        ref_mapping_dict = {"branch:main": "invalid_value"}

        with pytest.raises(ValueError, match="Invalid ref mapping value format"):
            JsonConfigParser.parse_ref_mapping(ref_mapping_dict)

    def test_parse_ref_mapping_invalid_ref_type(self) -> None:
        """Test parsing ref mapping with invalid ref type."""
        ref_mapping_dict = {"invalid:main": "branch:main"}

        with pytest.raises(ValueError, match="Invalid ref type in key"):
            JsonConfigParser.parse_ref_mapping(ref_mapping_dict)

    @patch("dd_license_attribution.config.json_config_parser.open_file")
    def test_load_mirror_configs_valid(self, mock_open_file: Mock) -> None:
        """Test loading valid mirror configurations."""
        mock_open_file.return_value = json.dumps(
            [
                {
                    "original_url": "https://github.com/DataDog/test",
                    "mirror_url": "https://github.com/mirror/test",
                    "ref_mapping": {"branch:main": "branch:development"},
                }
            ]
        )

        mirrors = JsonConfigParser.load_mirror_configs("test.json")

        assert len(mirrors) == 1
        mirror = mirrors[0]
        assert mirror.original_url == "https://github.com/DataDog/test"
        assert mirror.mirror_url == "https://github.com/mirror/test"
        assert mirror.ref_mapping == {
            (RefType.BRANCH, "main"): (RefType.BRANCH, "development")
        }

    @patch("dd_license_attribution.config.json_config_parser.open_file")
    def test_load_mirror_configs_no_ref_mapping(self, mock_open_file: Mock) -> None:
        """Test loading mirror configurations without ref mapping."""
        mock_open_file.return_value = json.dumps(
            [
                {
                    "original_url": "https://github.com/DataDog/test",
                    "mirror_url": "https://github.com/mirror/test",
                }
            ]
        )

        mirrors = JsonConfigParser.load_mirror_configs("test.json")

        assert len(mirrors) == 1
        mirror = mirrors[0]
        assert mirror.original_url == "https://github.com/DataDog/test"
        assert mirror.mirror_url == "https://github.com/mirror/test"
        assert mirror.ref_mapping is None

    @patch("dd_license_attribution.config.json_config_parser.open_file")
    def test_load_mirror_configs_file_not_found(self, mock_open_file: Mock) -> None:
        """Test loading mirror configurations with file not found."""
        mock_open_file.side_effect = FileNotFoundError("File not found")

        with pytest.raises(FileNotFoundError):
            JsonConfigParser.load_mirror_configs("nonexistent.json")

    @patch("dd_license_attribution.config.json_config_parser.open_file")
    def test_load_mirror_configs_invalid_json(self, mock_open_file: Mock) -> None:
        """Test loading mirror configurations with invalid JSON."""
        mock_open_file.return_value = "invalid json"

        with pytest.raises(json.JSONDecodeError):
            JsonConfigParser.load_mirror_configs("test.json")

    @patch("dd_license_attribution.config.json_config_parser.open_file")
    def test_load_override_configs_valid(self, mock_open_file: Mock) -> None:
        """Test loading valid override configurations."""
        mock_open_file.return_value = json.dumps(
            [
                {
                    "override_type": "add",
                    "target": {"component": "test-component"},
                    "replacement": {
                        "name": "new-component",
                        "origin": "new-origin",
                        "version": "1.0.0",
                        "license": ["MIT"],
                        "copyright": ["Copyright 2024"],
                    },
                }
            ]
        )

        override_rules = JsonConfigParser.load_override_configs("test.json")

        assert len(override_rules) == 1
        rule = override_rules[0]
        assert isinstance(rule, OverrideRule)
        assert rule.override_type == OverrideType.ADD
        assert rule.target[OverrideTargetField.COMPONENT] == "test-component"
        assert rule.replacement is not None
        assert rule.replacement.name == "new-component"

    @patch("dd_license_attribution.config.json_config_parser.open_file")
    def test_load_override_configs_file_not_found(self, mock_open_file: Mock) -> None:
        """Test loading override configurations with file not found."""
        mock_open_file.side_effect = FileNotFoundError("File not found")

        with pytest.raises(FileNotFoundError):
            JsonConfigParser.load_override_configs("nonexistent.json")

    @patch("dd_license_attribution.config.json_config_parser.open_file")
    def test_load_override_configs_invalid_json(self, mock_open_file: Mock) -> None:
        """Test loading override configurations with invalid JSON."""
        mock_open_file.return_value = "invalid json"

        with pytest.raises(json.JSONDecodeError):
            JsonConfigParser.load_override_configs("test.json")
