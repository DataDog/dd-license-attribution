# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import logging
import tomllib
from typing import Any
from unittest.mock import call

import pytest_mock
from pytest import LogCaptureFixture

from dd_license_attribution.artifact_management.rust_package_resolver import (
    SYNTHETIC_PACKAGE_NAME,
    RustPackageResolver,
)


class TestParseRustSpec:
    def test_simple_name_returns_wildcard_version(self) -> None:
        resolver = RustPackageResolver("/cache")

        name, version = resolver._parse_rust_spec("serde")

        assert name == "serde"
        assert version == "*"

    def test_name_with_version(self) -> None:
        resolver = RustPackageResolver("/cache")

        name, version = resolver._parse_rust_spec("serde@1.0")

        assert name == "serde"
        assert version == "1.0"

    def test_name_with_semver_range(self) -> None:
        resolver = RustPackageResolver("/cache")

        name, version = resolver._parse_rust_spec("tokio@^1.37")

        assert name == "tokio"
        assert version == "^1.37"

    def test_empty_version_returns_wildcard_version(self) -> None:
        resolver = RustPackageResolver("/cache")

        name, version = resolver._parse_rust_spec("serde@")

        assert name == "serde"
        assert version == "*"


class TestResolvePackage:
    def setup_method(self) -> None:
        self.resolver = RustPackageResolver("/cache")

    def _setup_mocks(
        self,
        mocker: pytest_mock.MockFixture,
        run_command_return: tuple[int, str, str] = (
            0,
            "cargo generate-lockfile completed",
            "",
        ),
        path_exists_return: bool = True,
    ) -> tuple[Any, Any, Any, Any]:
        def fake_path_join(*args: str) -> str:
            return "/".join(args)

        mock_create_dirs = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.create_dirs"
        )
        mock_write_file = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.write_file"
        )
        mock_run_command = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.run_command_with_check",
            return_value=run_command_return,
        )
        mock_path_exists = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.path_exists",
            return_value=path_exists_return,
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.path_join",
            side_effect=fake_path_join,
        )

        return (
            mock_create_dirs,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
        )

    def test_happy_path_creates_project_and_runs_cargo(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, mock_write_file, mock_run_command, mock_path_exists = (
            self._setup_mocks(mocker)
        )

        result = self.resolver.resolve_package("serde@1.0")

        assert result == "/cache/serde"
        mock_create_dirs.assert_has_calls(
            [call("/cache/serde"), call("/cache/serde/src")]
        )
        assert mock_create_dirs.call_count == 2

        assert mock_write_file.call_count == 2
        cargo_toml_path, cargo_toml_content = mock_write_file.call_args_list[0][0]
        assert cargo_toml_path == "/cache/serde/Cargo.toml"
        cargo_toml = tomllib.loads(cargo_toml_content)
        assert cargo_toml["package"]["name"] == SYNTHETIC_PACKAGE_NAME
        assert cargo_toml["package"]["publish"] is False
        assert cargo_toml["dependencies"] == {"serde": "1.0"}

        main_rs_path, main_rs_content = mock_write_file.call_args_list[1][0]
        assert main_rs_path == "/cache/serde/src/main.rs"
        assert main_rs_content == "fn main() {}\n"

        mock_run_command.assert_called_once_with(
            ["cargo", "generate-lockfile"],
            cwd="/cache/serde",
        )
        mock_path_exists.assert_called_once_with("/cache/serde/Cargo.lock")

    def test_name_without_version_uses_wildcard_dependency(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, mock_run_command, mock_path_exists = self._setup_mocks(
            mocker
        )

        self.resolver.resolve_package("anyhow")

        cargo_toml = tomllib.loads(mock_write_file.call_args_list[0][0][1])
        assert cargo_toml["dependencies"] == {"anyhow": "*"}
        cargo_toml_content = mock_write_file.call_args_list[0][0][1]
        mock_write_file.assert_has_calls(
            [
                call("/cache/anyhow/Cargo.toml", cargo_toml_content),
                call("/cache/anyhow/src/main.rs", "fn main() {}\n"),
            ]
        )
        mock_run_command.assert_called_once_with(
            ["cargo", "generate-lockfile"],
            cwd="/cache/anyhow",
        )
        mock_path_exists.assert_called_once_with("/cache/anyhow/Cargo.lock")

    def test_package_name_sanitizes_dir_name(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, _, mock_run_command, mock_path_exists = self._setup_mocks(
            mocker
        )

        result = self.resolver.resolve_package("serde-json@1.0")

        assert result == "/cache/serde-json"
        mock_create_dirs.assert_has_calls(
            [call("/cache/serde-json"), call("/cache/serde-json/src")]
        )
        assert mock_create_dirs.call_count == 2
        mock_run_command.assert_called_once_with(
            ["cargo", "generate-lockfile"],
            cwd="/cache/serde-json",
        )
        mock_path_exists.assert_called_once_with("/cache/serde-json/Cargo.lock")

    def test_cargo_failure_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        _, _, mock_run_command, mock_path_exists = self._setup_mocks(
            mocker,
            run_command_return=(1, "cargo stdout", "cargo error"),
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("missing-crate")

        assert result is None
        assert any(
            "stdout:\ncargo stdout\nstderr:\ncargo error" in record.message
            for record in caplog.records
        )
        mock_run_command.assert_called_once_with(
            ["cargo", "generate-lockfile"],
            cwd="/cache/missing-crate",
        )
        mock_path_exists.assert_not_called()

    def test_cargo_exception_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, _, mock_run_command, mock_path_exists = self._setup_mocks(mocker)
        mock_run_command.side_effect = OSError("cargo not found")

        result = self.resolver.resolve_package("serde")

        assert result is None
        mock_run_command.assert_called_once_with(
            ["cargo", "generate-lockfile"],
            cwd="/cache/serde",
        )
        mock_path_exists.assert_not_called()

    def test_missing_cargo_lock_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, _, mock_run_command, mock_path_exists = self._setup_mocks(
            mocker,
            path_exists_return=False,
        )

        result = self.resolver.resolve_package("serde")

        assert result is None
        mock_run_command.assert_called_once_with(
            ["cargo", "generate-lockfile"],
            cwd="/cache/serde",
        )
        mock_path_exists.assert_called_once_with("/cache/serde/Cargo.lock")

    def test_write_file_exception_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, mock_write_file, mock_run_command, mock_path_exists = (
            self._setup_mocks(mocker)
        )
        mock_write_file.side_effect = OSError("read-only")

        result = self.resolver.resolve_package("serde")

        assert result is None
        mock_create_dirs.assert_called_once_with("/cache/serde")
        mock_write_file.assert_called_once()
        mock_run_command.assert_not_called()
        mock_path_exists.assert_not_called()
