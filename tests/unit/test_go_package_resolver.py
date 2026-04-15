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
            side_effect=OSError("go not found"),
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

    def test_happy_path_creates_dir_and_runs_go_get_and_mod_tidy(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, mock_write_file, mock_run_command, mock_path_exists, _ = (
            self._setup_mocks(mocker)
        )

        result = self.resolver.resolve_package("github.com/stretchr/testify@v1.9.0")

        assert result == "/cache/github_com_stretchr_testify"
        mock_create_dirs.assert_called_once_with("/cache/github_com_stretchr_testify")

        # Verify go.mod was written without require (go get handles that)
        go_mod_call = mock_write_file.call_args_list[0]
        assert go_mod_call[0][0] == "/cache/github_com_stretchr_testify/go.mod"
        go_mod_content = go_mod_call[0][1]
        assert SYNTHETIC_MODULE_NAME in go_mod_content
        assert "go 1.23" in go_mod_content
        assert "require" not in go_mod_content

        # Verify main.go was written with correct import
        main_go_call = mock_write_file.call_args_list[1]
        assert main_go_call[0][0] == "/cache/github_com_stretchr_testify/main.go"
        main_go_content = main_go_call[0][1]
        assert 'import _ "github.com/stretchr/testify"' in main_go_content

        # Verify go get was called to add the dependency, then go mod tidy
        assert mock_run_command.call_count == 2
        mock_run_command.assert_any_call(
            ["go", "get", "github.com/stretchr/testify@v1.9.0"],
            cwd="/cache/github_com_stretchr_testify",
            env={"GOTOOLCHAIN": "auto"},
        )
        mock_run_command.assert_any_call(
            ["go", "mod", "tidy"],
            cwd="/cache/github_com_stretchr_testify",
            env={"GOTOOLCHAIN": "auto"},
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

    def test_no_version_uses_go_get_without_version(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, mock_run_command, _, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("github.com/stretchr/testify")

        go_mod_content = mock_write_file.call_args_list[0][0][1]
        assert "require" not in go_mod_content
        assert SYNTHETIC_MODULE_NAME in go_mod_content
        assert "go 1.23" in go_mod_content

        # go get without version fetches latest
        mock_run_command.assert_any_call(
            ["go", "get", "github.com/stretchr/testify"],
            cwd="/cache/github_com_stretchr_testify",
            env={"GOTOOLCHAIN": "auto"},
        )

    def test_version_passed_to_go_get(self, mocker: pytest_mock.MockFixture) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("github.com/stretchr/testify@v1.9.0")

        mock_run_command.assert_any_call(
            ["go", "get", "github.com/stretchr/testify@v1.9.0"],
            cwd="/cache/github_com_stretchr_testify",
            env={"GOTOOLCHAIN": "auto"},
        )

    def test_go_get_failure_returns_none(self, mocker: pytest_mock.MockFixture) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(
            mocker,
            run_command_return=(1, "go: module not found"),
        )

        result = self.resolver.resolve_package("github.com/nonexistent/pkg")

        assert result is None
        # Only go get is called; it fails so go mod tidy is never reached
        mock_run_command.assert_called_once()

    def test_go_get_exception_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(mocker)
        mock_run_command.side_effect = OSError("go not found")

        result = self.resolver.resolve_package("github.com/stretchr/testify")

        assert result is None
        mock_run_command.assert_called_once()

    def test_go_mod_tidy_failure_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(mocker)
        # go get succeeds, go mod tidy fails
        mock_run_command.side_effect = [
            (0, "go get completed"),
            (1, "go mod tidy failed"),
        ]

        result = self.resolver.resolve_package("github.com/stretchr/testify@v1.9.0")

        assert result is None
        assert mock_run_command.call_count == 2

    def test_missing_go_sum_returns_none(self, mocker: pytest_mock.MockFixture) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(
            mocker, path_exists_return=False
        )

        result = self.resolver.resolve_package("github.com/stretchr/testify@v1.9.0")

        assert result is None
        # Both go get and go mod tidy were called successfully
        assert mock_run_command.call_count == 2

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

    def test_version_without_v_prefix_gets_normalized_in_go_get(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, _, mock_run_command, _, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("github.com/stretchr/testify@1.9.0")

        # Version should be normalized to v1.9.0 in the go get command
        mock_run_command.assert_any_call(
            ["go", "get", "github.com/stretchr/testify@v1.9.0"],
            cwd="/cache/github_com_stretchr_testify",
            env={"GOTOOLCHAIN": "auto"},
        )

    def test_import_path_with_shell_metacharacters_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, _, mock_run_command, _, _ = self._setup_mocks(mocker)

        result = self.resolver.resolve_package("github.com/foo; rm -rf /")

        assert result is None
        mock_run_command.assert_not_called()
        mock_create_dirs.assert_not_called()

    def test_import_path_with_tilde_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, _, mock_run_command, _, _ = self._setup_mocks(mocker)

        result = self.resolver.resolve_package("~/malicious/path")

        assert result is None
        mock_run_command.assert_not_called()
        mock_create_dirs.assert_not_called()

    def test_version_with_shell_metacharacters_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, _, mock_run_command, _, _ = self._setup_mocks(mocker)

        result = self.resolver.resolve_package("github.com/stretchr/testify@v1.0; evil")

        assert result is None
        mock_run_command.assert_not_called()
        mock_create_dirs.assert_not_called()
