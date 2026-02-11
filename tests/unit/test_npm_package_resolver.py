# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import json
from typing import Any
from unittest.mock import call

import pytest
import pytest_mock

from dd_license_attribution.artifact_management.npm_package_resolver import (
    NpmPackageResolver,
)


class TestParseNpmSpec:
    def test_simple_name_returns_latest(self) -> None:
        resolver = NpmPackageResolver("/cache")
        name, version = resolver._parse_npm_spec("express")
        assert name == "express"
        assert version == "latest"

    def test_name_with_version(self) -> None:
        resolver = NpmPackageResolver("/cache")
        name, version = resolver._parse_npm_spec("express@4.18.2")
        assert name == "express"
        assert version == "4.18.2"

    def test_scoped_package_returns_latest(self) -> None:
        resolver = NpmPackageResolver("/cache")
        name, version = resolver._parse_npm_spec("@datadog/browser-sdk")
        assert name == "@datadog/browser-sdk"
        assert version == "latest"

    def test_scoped_package_with_version(self) -> None:
        resolver = NpmPackageResolver("/cache")
        name, version = resolver._parse_npm_spec("@datadog/browser-sdk@4.0.0")
        assert name == "@datadog/browser-sdk"
        assert version == "4.0.0"

    def test_scoped_package_with_semver_range(self) -> None:
        resolver = NpmPackageResolver("/cache")
        name, version = resolver._parse_npm_spec("@scope/pkg@^1.0.0")
        assert name == "@scope/pkg"
        assert version == "^1.0.0"

    def test_name_with_empty_version_returns_latest(self) -> None:
        resolver = NpmPackageResolver("/cache")
        name, version = resolver._parse_npm_spec("express@")
        assert name == "express"
        assert version == "latest"


class TestResolvePackage:
    def setup_method(self) -> None:
        self.resolver = NpmPackageResolver("/cache")

    def test_happy_path_creates_dir_and_runs_npm(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        def fake_path_join(*args: Any) -> str:
            return "/".join(args)

        mock_create_dirs = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.create_dirs"
        )
        mock_write_file = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.write_file"
        )
        mock_output = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.output_from_command",
            return_value="npm install completed",
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.path_join",
            side_effect=fake_path_join,
        )

        result = self.resolver.resolve_package("express@4.18.2")

        assert result == "/cache/express"
        mock_create_dirs.assert_called_once_with("/cache/express")

        # Verify package.json was written with correct content
        write_call_args = mock_write_file.call_args
        assert write_call_args[0][0] == "/cache/express/package.json"
        written_json = json.loads(write_call_args[0][1])
        assert written_json["name"] == "ddla-npm-resolve"
        assert written_json["private"] is True
        assert written_json["dependencies"] == {"express": "4.18.2"}

        mock_output.assert_called_once()
        assert "npm install --package-lock-only --force" in mock_output.call_args[0][0]

    def test_scoped_package_sanitizes_dir_name(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        def fake_path_join(*args: Any) -> str:
            return "/".join(args)

        mock_create_dirs = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.create_dirs"
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.write_file"
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.output_from_command",
            return_value="ok",
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.path_join",
            side_effect=fake_path_join,
        )

        result = self.resolver.resolve_package("@datadog/browser-sdk@4.0.0")

        assert result is not None
        # @ and / are sanitized to _
        mock_create_dirs.assert_called_once_with(
            "/cache/_datadog_browser-sdk"
        )

    def test_npm_failure_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        def fake_path_join(*args: Any) -> str:
            return "/".join(args)

        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.create_dirs"
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.write_file"
        )
        mock_output = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.output_from_command",
            side_effect=Exception("npm not found"),
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.path_join",
            side_effect=fake_path_join,
        )

        result = self.resolver.resolve_package("nonexistent-pkg")

        assert result is None
        mock_output.assert_called_once()

    def test_latest_version_when_no_version_specified(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        def fake_path_join(*args: Any) -> str:
            return "/".join(args)

        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.create_dirs"
        )
        mock_write_file = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.write_file"
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.output_from_command",
            return_value="ok",
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.path_join",
            side_effect=fake_path_join,
        )

        self.resolver.resolve_package("express")

        written_json = json.loads(mock_write_file.call_args[0][1])
        assert written_json["dependencies"] == {"express": "latest"}
