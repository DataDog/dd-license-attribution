# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import json
from typing import Any

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

    def test_scoped_package_with_trailing_at(self) -> None:
        resolver = NpmPackageResolver("/cache")
        name, version = resolver._parse_npm_spec("@scope/pkg@")
        assert name == "@scope/pkg"
        assert version == "latest"


class TestResolvePackage:
    def setup_method(self) -> None:
        self.resolver = NpmPackageResolver("/cache")

    def _setup_mocks(
        self,
        mocker: pytest_mock.MockFixture,
        run_command_return: tuple[int, str] = (0, "npm install completed"),
        path_exists_return: bool = True,
    ) -> tuple[Any, Any, Any, Any, Any]:
        def fake_path_join(*args: Any) -> str:
            return "/".join(args)

        mock_create_dirs = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.create_dirs"
        )
        mock_write_file = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.write_file"
        )
        mock_run_command = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.run_command_with_check",
            return_value=run_command_return,
        )
        mock_path_exists = mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.path_exists",
            return_value=path_exists_return,
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.npm_package_resolver.path_join",
            side_effect=fake_path_join,
        )

        return (
            mock_create_dirs,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            fake_path_join,
        )

    def test_happy_path_creates_dir_and_runs_npm(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, mock_write_file, mock_run_command, mock_path_exists, _ = (
            self._setup_mocks(mocker)
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

        # Verify run_command_with_check was called with --ignore-scripts and cwd
        mock_run_command.assert_called_once_with(
            "npm install --package-lock-only --force --ignore-scripts",
            cwd="/cache/express",
        )

        # Verify package-lock.json existence was checked
        mock_path_exists.assert_called_once_with("/cache/express/package-lock.json")

    def test_scoped_package_sanitizes_dir_name(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, _, _, _, _ = self._setup_mocks(mocker)

        result = self.resolver.resolve_package("@datadog/browser-sdk@4.0.0")

        assert result is not None
        # @ and / are sanitized to _
        mock_create_dirs.assert_called_once_with("/cache/_datadog_browser-sdk")

    def test_npm_failure_returns_none(self, mocker: pytest_mock.MockFixture) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(
            mocker, run_command_return=(1, "npm ERR! not found")
        )

        result = self.resolver.resolve_package("nonexistent-pkg")

        assert result is None
        mock_run_command.assert_called_once()

    def test_npm_exception_returns_none(self, mocker: pytest_mock.MockFixture) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(mocker)
        mock_run_command.side_effect = Exception("npm not found")

        result = self.resolver.resolve_package("nonexistent-pkg")

        assert result is None
        mock_run_command.assert_called_once()

    def test_latest_version_when_no_version_specified(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, _, _, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("express")

        written_json = json.loads(mock_write_file.call_args[0][1])
        assert written_json["dependencies"] == {"express": "latest"}

    def test_missing_package_lock_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(
            mocker, path_exists_return=False
        )

        result = self.resolver.resolve_package("express@4.18.2")

        assert result is None
        # npm install was called successfully
        mock_run_command.assert_called_once()

    def test_ignore_scripts_flag_present(self, mocker: pytest_mock.MockFixture) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("express")

        command = mock_run_command.call_args[0][0]
        assert "--ignore-scripts" in command
