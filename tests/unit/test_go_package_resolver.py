# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from typing import Any

import pytest_mock

from dd_license_attribution.artifact_management.go_package_resolver import (
    SYNTHETIC_MODULE_NAME,
    GoPackageResolver,
)


class TestParseGoSpec:
    def test_simple_module_returns_empty_version(self) -> None:
        resolver = GoPackageResolver("/cache")
        import_path, version = resolver._parse_go_spec("github.com/stretchr/testify")
        assert import_path == "github.com/stretchr/testify"
        assert version == ""

    def test_module_with_version(self) -> None:
        resolver = GoPackageResolver("/cache")
        import_path, version = resolver._parse_go_spec(
            "github.com/stretchr/testify@v1.9.0"
        )
        assert import_path == "github.com/stretchr/testify"
        assert version == "v1.9.0"

    def test_module_with_major_version_suffix(self) -> None:
        resolver = GoPackageResolver("/cache")
        import_path, version = resolver._parse_go_spec(
            "github.com/DataDog/dd-trace-go/v2"
        )
        assert import_path == "github.com/DataDog/dd-trace-go/v2"
        assert version == ""

    def test_package_path_within_module(self) -> None:
        resolver = GoPackageResolver("/cache")
        import_path, version = resolver._parse_go_spec(
            "github.com/DataDog/dd-trace-go/v2/ddtrace/tracer"
        )
        assert import_path == "github.com/DataDog/dd-trace-go/v2/ddtrace/tracer"
        assert version == ""

    def test_module_with_major_version_and_pinned_version(self) -> None:
        resolver = GoPackageResolver("/cache")
        import_path, version = resolver._parse_go_spec(
            "github.com/DataDog/dd-trace-go/v2@v2.0.0"
        )
        assert import_path == "github.com/DataDog/dd-trace-go/v2"
        assert version == "v2.0.0"

    def test_version_without_v_prefix_gets_normalized(self) -> None:
        resolver = GoPackageResolver("/cache")
        import_path, version = resolver._parse_go_spec(
            "github.com/stretchr/testify@1.9.0"
        )
        assert import_path == "github.com/stretchr/testify"
        assert version == "v1.9.0"

    def test_non_github_module(self) -> None:
        resolver = GoPackageResolver("/cache")
        import_path, version = resolver._parse_go_spec("golang.org/x/net")
        assert import_path == "golang.org/x/net"
        assert version == ""

    def test_non_github_module_with_version(self) -> None:
        resolver = GoPackageResolver("/cache")
        import_path, version = resolver._parse_go_spec("golang.org/x/net@v0.25.0")
        assert import_path == "golang.org/x/net"
        assert version == "v0.25.0"

    def test_empty_version_after_at_returns_empty(self) -> None:
        resolver = GoPackageResolver("/cache")
        import_path, version = resolver._parse_go_spec("github.com/stretchr/testify@")
        assert import_path == "github.com/stretchr/testify"
        assert version == ""


class TestDetectGoVersion:
    def test_parses_go_env_output(self, mocker: pytest_mock.MockFixture) -> None:
        mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.output_from_command",
            return_value="go1.22.5\n",
        )
        resolver = GoPackageResolver("/cache")
        assert resolver._detect_go_version() == "1.22"

    def test_parses_major_minor_only(self, mocker: pytest_mock.MockFixture) -> None:
        mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.output_from_command",
            return_value="go1.23\n",
        )
        resolver = GoPackageResolver("/cache")
        assert resolver._detect_go_version() == "1.23"

    def test_falls_back_on_unexpected_output(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.output_from_command",
            return_value="unexpected",
        )
        resolver = GoPackageResolver("/cache")
        assert resolver._detect_go_version() == "1.22"

    def test_falls_back_on_exception(self, mocker: pytest_mock.MockFixture) -> None:
        mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.output_from_command",
            side_effect=Exception("go not found"),
        )
        resolver = GoPackageResolver("/cache")
        assert resolver._detect_go_version() == "1.22"


class TestResolvePackage:
    def setup_method(self) -> None:
        self.resolver = GoPackageResolver("/cache")

    def _setup_mocks(
        self,
        mocker: pytest_mock.MockFixture,
        run_command_return: tuple[int, str] = (0, "go mod tidy completed"),
        path_exists_return: bool = True,
    ) -> tuple[Any, Any, Any, Any, Any]:
        def fake_path_join(*args: Any) -> str:
            return "/".join(args)

        mock_create_dirs = mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.create_dirs"
        )
        mock_write_file = mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.write_file"
        )
        mock_run_command = mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.run_command_with_check",
            return_value=run_command_return,
        )
        mock_path_exists = mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.path_exists",
            return_value=path_exists_return,
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.path_join",
            side_effect=fake_path_join,
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.go_package_resolver.output_from_command",
            return_value="go1.23.5\n",
        )

        return (
            mock_create_dirs,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            fake_path_join,
        )

    def test_happy_path_creates_dir_and_runs_go_mod_tidy(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, mock_write_file, mock_run_command, mock_path_exists, _ = (
            self._setup_mocks(mocker)
        )

        result = self.resolver.resolve_package("github.com/stretchr/testify@v1.9.0")

        assert result == "/cache/github_com_stretchr_testify"
        mock_create_dirs.assert_called_once_with("/cache/github_com_stretchr_testify")

        # Verify go.mod was written with correct content
        go_mod_call = mock_write_file.call_args_list[0]
        assert go_mod_call[0][0] == "/cache/github_com_stretchr_testify/go.mod"
        go_mod_content = go_mod_call[0][1]
        assert SYNTHETIC_MODULE_NAME in go_mod_content
        assert "go 1.23" in go_mod_content
        assert "require github.com/stretchr/testify v1.9.0" in go_mod_content

        # Verify main.go was written with correct import
        main_go_call = mock_write_file.call_args_list[1]
        assert main_go_call[0][0] == "/cache/github_com_stretchr_testify/main.go"
        main_go_content = main_go_call[0][1]
        assert 'import _ "github.com/stretchr/testify"' in main_go_content

        # Verify go mod tidy was called
        mock_run_command.assert_called_once_with(
            "GOTOOLCHAIN=auto go mod tidy",
            cwd="/cache/github_com_stretchr_testify",
        )

        # Verify go.sum existence was checked
        mock_path_exists.assert_called_once_with(
            "/cache/github_com_stretchr_testify/go.sum"
        )

    def test_package_path_sanitizes_dir_name(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, _, _, _, _ = self._setup_mocks(mocker)

        result = self.resolver.resolve_package(
            "github.com/DataDog/dd-trace-go/v2/ddtrace/tracer"
        )

        assert result is not None
        # . and / are sanitized to _
        mock_create_dirs.assert_called_once_with(
            "/cache/github_com_DataDog_dd-trace-go_v2_ddtrace_tracer"
        )

    def test_no_version_omits_require_line(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, _, _, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("github.com/stretchr/testify")

        go_mod_content = mock_write_file.call_args_list[0][0][1]
        assert "require" not in go_mod_content
        assert SYNTHETIC_MODULE_NAME in go_mod_content
        assert "go 1.23" in go_mod_content

    def test_version_included_in_require_when_specified(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, _, _, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("github.com/stretchr/testify@v1.9.0")

        go_mod_content = mock_write_file.call_args_list[0][0][1]
        assert "require github.com/stretchr/testify v1.9.0" in go_mod_content

    def test_go_mod_tidy_failure_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(
            mocker,
            run_command_return=(1, "go: module not found"),
        )

        result = self.resolver.resolve_package("github.com/nonexistent/pkg")

        assert result is None
        mock_run_command.assert_called_once()

    def test_go_mod_tidy_exception_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(mocker)
        mock_run_command.side_effect = Exception("go not found")

        result = self.resolver.resolve_package("github.com/stretchr/testify")

        assert result is None
        mock_run_command.assert_called_once()

    def test_missing_go_sum_returns_none(self, mocker: pytest_mock.MockFixture) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(
            mocker, path_exists_return=False
        )

        result = self.resolver.resolve_package("github.com/stretchr/testify@v1.9.0")

        assert result is None
        # go mod tidy was called successfully
        mock_run_command.assert_called_once()

    def test_main_go_imports_full_package_path(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, _, _, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package(
            "github.com/DataDog/dd-trace-go/v2/ddtrace/tracer"
        )

        main_go_content = mock_write_file.call_args_list[1][0][1]
        assert (
            'import _ "github.com/DataDog/dd-trace-go/v2/ddtrace/tracer"'
            in main_go_content
        )

    def test_version_without_v_prefix_gets_normalized_in_require(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, _, _, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("github.com/stretchr/testify@1.9.0")

        go_mod_content = mock_write_file.call_args_list[0][0][1]
        assert "require github.com/stretchr/testify v1.9.0" in go_mod_content
