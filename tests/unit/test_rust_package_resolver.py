# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import json
import logging
import tomllib
from typing import Any
from unittest.mock import Mock, call

import pytest_mock
from pytest import LogCaptureFixture, mark

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.rust_package_resolver import (
    CRATES_IO_USER_AGENT,
    SYNTHETIC_PACKAGE_NAME,
    RustPackageResolver,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    NonAccessibleRepository,
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

    def test_version_may_contain_at_symbol(self) -> None:
        resolver = RustPackageResolver("/cache")

        name, version = resolver._parse_rust_spec("crate@1.0@metadata")

        assert name == "crate"
        assert version == "1.0@metadata"


class TestResolvePackage:
    def setup_method(self) -> None:
        self.resolver = RustPackageResolver("/cache")

    def _binary_metadata_return(self, crate_name: str) -> tuple[int, str, str]:
        return (
            0,
            json.dumps({"packages": [{"name": SYNTHETIC_PACKAGE_NAME}]}),
            (
                f"warning: {SYNTHETIC_PACKAGE_NAME} v0.0.0 "
                f"ignoring invalid dependency `{crate_name}` which is missing "
                "a lib target"
            ),
        )

    def _cargo_lock_with_package(self, crate_name: str, version: str) -> str:
        return (
            "version = 4\n"
            "\n"
            "[[package]]\n"
            f'name = "{crate_name}"\n'
            f'version = "{version}"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
            "\n"
            "[[package]]\n"
            f'name = "{SYNTHETIC_PACKAGE_NAME}"\n'
            'version = "0.0.0"\n'
            "dependencies = [\n"
            f' "{crate_name}",\n'
            "]\n"
        )

    def _setup_mocks(
        self,
        mocker: pytest_mock.MockFixture,
        generate_lockfile_return: tuple[int, str, str] = (
            0,
            "cargo generate-lockfile completed",
            "",
        ),
        metadata_return: tuple[int, str, str] | None = None,
        path_exists_return: bool | list[bool] = True,
        cargo_lock_content: str = "",
        extracted_members: list[str] | None = None,
    ) -> tuple[Any, Any, Any, Any, Any, Any, Any]:
        def fake_path_join(*args: str) -> str:
            return "/".join(args)

        if metadata_return is None:
            metadata_return = (
                0,
                json.dumps({"packages": [{"name": "serde"}]}),
                "",
            )

        resolved_crate_name = "serde"
        try:
            metadata_packages = json.loads(metadata_return[1])["packages"]
            resolved_crate_name = next(
                package["name"]
                for package in metadata_packages
                if isinstance(package, dict)
                and package.get("name") != SYNTHETIC_PACKAGE_NAME
            )
        except (json.JSONDecodeError, KeyError, StopIteration, TypeError):
            pass
        if not cargo_lock_content:
            cargo_lock_content = self._cargo_lock_with_package(
                resolved_crate_name,
                "1.0.0",
            )

        mock_create_dirs = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.create_dirs"
        )
        mock_write_file = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.write_file"
        )
        mock_run_command = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.run_command_with_check",
            side_effect=[generate_lockfile_return, metadata_return],
        )
        path_exists_side_effect: bool | list[bool]
        path_exists_side_effect = path_exists_return
        mock_path_exists = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.path_exists",
        )
        if isinstance(path_exists_side_effect, list):
            mock_path_exists.side_effect = path_exists_side_effect
        else:
            mock_path_exists.return_value = path_exists_side_effect
        mock_open_file = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.open_file",
            return_value=cargo_lock_content,
        )
        mock_download_url = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.download_url",
            return_value=b"crate archive",
        )
        mock_extract_tar_gz = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.extract_tar_gz",
            return_value=(
                extracted_members
                if extracted_members is not None
                else [f"{resolved_crate_name}-1.0.0/Cargo.toml"]
            ),
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
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        )

    @mark.parametrize(
        ("rust_package_spec", "expected_requirement"),
        [
            ("serde", "*"),
            ("serde@1.0", "=1.0"),
            ("serde@1.0.0", "=1.0.0"),
            ("serde@^1.0", "^1.0"),
        ],
    )
    def test_happy_path_creates_project_and_runs_cargo(
        self,
        mocker: pytest_mock.MockFixture,
        rust_package_spec: str,
        expected_requirement: str,
    ) -> None:
        (
            mock_create_dirs,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(mocker)

        result = self.resolver.resolve_package(rust_package_spec)

        assert result == "/cache/serde/crate-source/serde-1.0.0"
        mock_create_dirs.assert_has_calls(
            [
                call("/cache/serde"),
                call("/cache/serde/src"),
                call("/cache/serde/crate-source"),
            ]
        )
        assert mock_create_dirs.call_count == 3

        assert mock_write_file.call_count == 2
        cargo_toml_path, cargo_toml_content = mock_write_file.call_args_list[0][0]
        assert cargo_toml_path == "/cache/serde/Cargo.toml"
        cargo_toml = tomllib.loads(cargo_toml_content)
        assert cargo_toml["package"]["name"] == SYNTHETIC_PACKAGE_NAME
        assert cargo_toml["package"]["publish"] is False
        assert cargo_toml["dependencies"] == {"serde": expected_requirement}

        main_rs_path, main_rs_content = mock_write_file.call_args_list[1][0]
        assert main_rs_path == "/cache/serde/src/main.rs"
        assert main_rs_content == "fn main() {}\n"

        mock_run_command.assert_has_calls(
            [
                call(["cargo", "generate-lockfile"], cwd="/cache/serde"),
                call(
                    ["cargo", "metadata", "--format-version", "1"], cwd="/cache/serde"
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_has_calls(
            [
                call("/cache/serde/Cargo.lock"),
                call("/cache/serde/crate-source/serde-1.0.0/Cargo.toml"),
            ]
        )
        assert mock_path_exists.call_count == 2
        mock_open_file.assert_called_once_with("/cache/serde/Cargo.lock")
        mock_download_url.assert_called_once_with(
            "https://crates.io/api/v1/crates/serde/1.0.0/download",
            user_agent=CRATES_IO_USER_AGENT,
        )
        mock_extract_tar_gz.assert_called_once_with(
            b"crate archive",
            "/cache/serde/crate-source",
        )

    def test_repository_license_tool_config_is_copied_to_published_crate(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        source_code_manager = Mock()
        source_code_manager.get_code.return_value = SourceCodeReference(
            repo_url="https://github.com/DataDog/datadog-api-client-rust",
            branch="master",
            local_root_path="/cache/repositories/datadog-api-client-rust",
            local_full_path="/cache/repositories/datadog-api-client-rust",
        )
        resolver = RustPackageResolver("/cache", source_code_manager)
        metadata_output = json.dumps(
            {
                "packages": [
                    {
                        "name": "datadog-api-client",
                        "repository": (
                            "https://github.com/DataDog/datadog-api-client-rust"
                        ),
                    }
                ]
            }
        )
        config_content = (
            "[overrides]\n"
            '"openssl-macros" = '
            '{ origin = "https://github.com/sfackler/rust-openssl" }\n'
        )
        cargo_lock_content = self._cargo_lock_with_package(
            "datadog-api-client",
            "1.0.0",
        )
        (
            mock_create_dirs,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(0, metadata_output, ""),
            path_exists_return=[True, True, True],
            cargo_lock_content=cargo_lock_content,
        )
        mock_open_file.side_effect = [cargo_lock_content, config_content]

        result = resolver.resolve_package("datadog-api-client")

        assert (
            result == "/cache/datadog-api-client/crate-source/datadog-api-client-1.0.0"
        )
        source_code_manager.get_code.assert_called_once_with(
            "https://github.com/DataDog/datadog-api-client-rust"
        )
        mock_create_dirs.assert_has_calls(
            [
                call("/cache/datadog-api-client"),
                call("/cache/datadog-api-client/src"),
                call("/cache/datadog-api-client/crate-source"),
            ]
        )
        assert mock_create_dirs.call_count == 3
        cargo_toml_content = mock_write_file.call_args_list[0].args[1]
        mock_write_file.assert_has_calls(
            [
                call(
                    "/cache/datadog-api-client/Cargo.toml",
                    cargo_toml_content,
                ),
                call("/cache/datadog-api-client/src/main.rs", "fn main() {}\n"),
                call(
                    "/cache/datadog-api-client/crate-source/"
                    "datadog-api-client-1.0.0/license-tool.toml",
                    config_content,
                ),
            ]
        )
        assert mock_write_file.call_count == 3
        mock_run_command.assert_has_calls(
            [
                call(
                    ["cargo", "generate-lockfile"],
                    cwd="/cache/datadog-api-client",
                ),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/datadog-api-client",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_has_calls(
            [
                call("/cache/datadog-api-client/Cargo.lock"),
                call(
                    "/cache/datadog-api-client/crate-source/"
                    "datadog-api-client-1.0.0/Cargo.toml"
                ),
                call(
                    "/cache/repositories/datadog-api-client-rust/" "license-tool.toml"
                ),
            ]
        )
        assert mock_path_exists.call_count == 3
        mock_open_file.assert_has_calls(
            [
                call("/cache/datadog-api-client/Cargo.lock"),
                call(
                    "/cache/repositories/datadog-api-client-rust/" "license-tool.toml"
                ),
            ]
        )
        assert mock_open_file.call_count == 2
        mock_download_url.assert_called_once_with(
            "https://crates.io/api/v1/crates/datadog-api-client/1.0.0/download",
            user_agent=CRATES_IO_USER_AGENT,
        )
        mock_extract_tar_gz.assert_called_once_with(
            b"crate archive",
            "/cache/datadog-api-client/crate-source",
        )

    def test_missing_crate_repository_skips_license_tool_config_lookup(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        source_code_manager = Mock()
        resolver = RustPackageResolver("/cache", source_code_manager)
        (
            _,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(
                0,
                json.dumps({"packages": [{"name": "serde"}]}),
                "",
            ),
        )

        result = resolver.resolve_package("serde")

        assert result == "/cache/serde/crate-source/serde-1.0.0"
        source_code_manager.get_code.assert_not_called()
        assert mock_write_file.call_count == 2
        assert mock_run_command.call_count == 2
        assert mock_path_exists.call_count == 2
        mock_open_file.assert_called_once_with("/cache/serde/Cargo.lock")
        mock_download_url.assert_called_once()
        mock_extract_tar_gz.assert_called_once()

    def test_inaccessible_crate_repository_skips_license_tool_config(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        source_code_manager = Mock()
        source_code_manager.get_code.side_effect = NonAccessibleRepository(
            "repository unavailable"
        )
        resolver = RustPackageResolver("/cache", source_code_manager)
        metadata_output = json.dumps(
            {
                "packages": [
                    {
                        "name": "serde",
                        "repository": "https://github.com/serde-rs/serde",
                    }
                ]
            }
        )
        (
            _,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(0, metadata_output, ""),
        )

        with caplog.at_level(logging.WARNING):
            result = resolver.resolve_package("serde")

        assert result == "/cache/serde/crate-source/serde-1.0.0"
        assert "Could not retrieve repository configuration" in caplog.text
        source_code_manager.get_code.assert_called_once_with(
            "https://github.com/serde-rs/serde"
        )
        assert mock_write_file.call_count == 2
        assert mock_run_command.call_count == 2
        assert mock_path_exists.call_count == 2
        mock_open_file.assert_called_once_with("/cache/serde/Cargo.lock")
        mock_download_url.assert_called_once()
        mock_extract_tar_gz.assert_called_once()

    def test_repository_without_license_tool_config_is_ignored(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        source_code_manager = Mock()
        source_code_manager.get_code.return_value = SourceCodeReference(
            repo_url="https://github.com/serde-rs/serde",
            branch="master",
            local_root_path="/cache/repositories/serde",
            local_full_path="/cache/repositories/serde",
        )
        resolver = RustPackageResolver("/cache", source_code_manager)
        metadata_output = json.dumps(
            {
                "packages": [
                    {
                        "name": "serde",
                        "repository": "https://github.com/serde-rs/serde",
                    }
                ]
            }
        )
        (
            _,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(0, metadata_output, ""),
            path_exists_return=[True, True, False],
        )

        result = resolver.resolve_package("serde")

        assert result == "/cache/serde/crate-source/serde-1.0.0"
        source_code_manager.get_code.assert_called_once_with(
            "https://github.com/serde-rs/serde"
        )
        assert mock_write_file.call_count == 2
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_has_calls(
            [
                call("/cache/serde/Cargo.lock"),
                call("/cache/serde/crate-source/serde-1.0.0/Cargo.toml"),
                call("/cache/repositories/serde/license-tool.toml"),
            ]
        )
        assert mock_path_exists.call_count == 3
        mock_open_file.assert_called_once_with("/cache/serde/Cargo.lock")
        mock_download_url.assert_called_once()
        mock_extract_tar_gz.assert_called_once()

    def test_license_tool_config_read_failure_does_not_fail_resolution(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        source_code_manager = Mock()
        source_code_manager.get_code.return_value = SourceCodeReference(
            repo_url="https://github.com/serde-rs/serde",
            branch="master",
            local_root_path="/cache/repositories/serde",
            local_full_path="/cache/repositories/serde",
        )
        resolver = RustPackageResolver("/cache", source_code_manager)
        metadata_output = json.dumps(
            {
                "packages": [
                    {
                        "name": "serde",
                        "repository": "https://github.com/serde-rs/serde",
                    }
                ]
            }
        )
        (
            _,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(0, metadata_output, ""),
            path_exists_return=[True, True, True],
        )
        cargo_lock_content = self._cargo_lock_with_package("serde", "1.0.0")
        mock_open_file.side_effect = [
            cargo_lock_content,
            OSError("permission denied"),
        ]

        with caplog.at_level(logging.WARNING):
            result = resolver.resolve_package("serde")

        assert result == "/cache/serde/crate-source/serde-1.0.0"
        assert "Could not copy license-tool.toml" in caplog.text
        source_code_manager.get_code.assert_called_once_with(
            "https://github.com/serde-rs/serde"
        )
        assert mock_write_file.call_count == 2
        assert mock_run_command.call_count == 2
        assert mock_path_exists.call_count == 3
        mock_open_file.assert_has_calls(
            [
                call("/cache/serde/Cargo.lock"),
                call("/cache/repositories/serde/license-tool.toml"),
            ]
        )
        assert mock_open_file.call_count == 2
        mock_download_url.assert_called_once()
        mock_extract_tar_gz.assert_called_once()

    def test_unavailable_repository_checkout_skips_license_tool_config(self) -> None:
        source_code_manager = Mock()
        source_code_manager.get_code.return_value = None
        resolver = RustPackageResolver("/cache", source_code_manager)

        resolver._copy_license_tool_config(
            "https://github.com/serde-rs/serde",
            "serde",
            "/cache/serde",
        )

        source_code_manager.get_code.assert_called_once_with(
            "https://github.com/serde-rs/serde"
        )

    def test_get_crate_repository_ignores_unrelated_packages(self) -> None:
        metadata_output = json.dumps(
            {
                "packages": [
                    "invalid-package",
                    {
                        "name": "serde-json",
                        "repository": "https://github.com/serde-rs/json",
                    },
                ]
            }
        )

        result = self.resolver._get_crate_repository(metadata_output, "serde")

        assert result is None

    def test_name_without_version_uses_wildcard_dependency(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        (
            _,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(0, json.dumps({"packages": [{"name": "anyhow"}]}), ""),
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
        mock_run_command.assert_has_calls(
            [
                call(["cargo", "generate-lockfile"], cwd="/cache/anyhow"),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/anyhow",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        assert mock_path_exists.call_count == 2
        mock_open_file.assert_called_once_with("/cache/anyhow/Cargo.lock")
        mock_download_url.assert_called_once()
        mock_extract_tar_gz.assert_called_once()

    def test_package_name_sanitizes_dir_name(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        (
            mock_create_dirs,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(
                0,
                json.dumps({"packages": [{"name": "serde-json"}]}),
                "",
            ),
        )

        result = self.resolver.resolve_package("serde-json@1.0")

        assert result == "/cache/serde-json/crate-source/serde-json-1.0.0"
        mock_create_dirs.assert_has_calls(
            [
                call("/cache/serde-json"),
                call("/cache/serde-json/src"),
                call("/cache/serde-json/crate-source"),
            ]
        )
        assert mock_create_dirs.call_count == 3
        mock_run_command.assert_has_calls(
            [
                call(["cargo", "generate-lockfile"], cwd="/cache/serde-json"),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/serde-json",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        assert mock_path_exists.call_count == 2
        mock_open_file.assert_called_once_with("/cache/serde-json/Cargo.lock")
        mock_download_url.assert_called_once()
        mock_extract_tar_gz.assert_called_once()

    def test_cargo_failure_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            generate_lockfile_return=(1, "cargo stdout", "cargo error"),
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
        mock_open_file.assert_not_called()
        mock_download_url.assert_not_called()
        mock_extract_tar_gz.assert_not_called()

    def test_cargo_exception_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(mocker)
        mock_run_command.side_effect = OSError("cargo not found")

        result = self.resolver.resolve_package("serde")

        assert result is None
        mock_run_command.assert_called_once_with(
            ["cargo", "generate-lockfile"],
            cwd="/cache/serde",
        )
        mock_path_exists.assert_not_called()
        mock_open_file.assert_not_called()
        mock_download_url.assert_not_called()
        mock_extract_tar_gz.assert_not_called()

    def test_missing_cargo_lock_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
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
        mock_open_file.assert_not_called()
        mock_download_url.assert_not_called()
        mock_extract_tar_gz.assert_not_called()

    def test_write_file_exception_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        (
            mock_create_dirs,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(mocker)
        mock_write_file.side_effect = OSError("read-only")

        result = self.resolver.resolve_package("serde")

        assert result is None
        mock_create_dirs.assert_called_once_with("/cache/serde")
        mock_write_file.assert_called_once()
        mock_run_command.assert_not_called()
        mock_path_exists.assert_not_called()
        mock_open_file.assert_not_called()
        mock_download_url.assert_not_called()
        mock_extract_tar_gz.assert_not_called()

    def test_binary_only_crate_falls_back_to_published_source(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        (
            mock_create_dirs,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=self._binary_metadata_return("dd-rust-license-tool"),
            path_exists_return=[True, True],
            cargo_lock_content=self._cargo_lock_with_package(
                "dd-rust-license-tool",
                "1.0.6",
            ),
            extracted_members=["dd-rust-license-tool-1.0.6/Cargo.toml"],
        )

        result = self.resolver.resolve_package("dd-rust-license-tool")

        assert (
            result
            == "/cache/dd-rust-license-tool/crate-source/dd-rust-license-tool-1.0.6"
        )
        mock_create_dirs.assert_has_calls(
            [
                call("/cache/dd-rust-license-tool"),
                call("/cache/dd-rust-license-tool/src"),
                call("/cache/dd-rust-license-tool/crate-source"),
            ]
        )
        assert mock_create_dirs.call_count == 3
        mock_run_command.assert_has_calls(
            [
                call(
                    ["cargo", "generate-lockfile"],
                    cwd="/cache/dd-rust-license-tool",
                ),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/dd-rust-license-tool",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_has_calls(
            [
                call("/cache/dd-rust-license-tool/Cargo.lock"),
                call(
                    "/cache/dd-rust-license-tool/crate-source/"
                    "dd-rust-license-tool-1.0.6/Cargo.toml"
                ),
            ]
        )
        assert mock_path_exists.call_count == 2
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")
        mock_download_url.assert_called_once_with(
            "https://crates.io/api/v1/crates/dd-rust-license-tool/1.0.6/download",
            user_agent=CRATES_IO_USER_AGENT,
        )
        mock_extract_tar_gz.assert_called_once_with(
            b"crate archive",
            "/cache/dd-rust-license-tool/crate-source",
        )

    def test_binary_only_crate_copies_repository_license_tool_config(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        source_code_manager = Mock()
        source_code_manager.get_code.return_value = SourceCodeReference(
            repo_url="https://github.com/DataDog/dd-rust-license-tool",
            branch="main",
            local_root_path="/cache/repositories/dd-rust-license-tool",
            local_full_path="/cache/repositories/dd-rust-license-tool",
        )
        resolver = RustPackageResolver("/cache", source_code_manager)
        config_content = (
            "[overrides]\n"
            '"openssl-macros" = '
            '{ origin = "https://github.com/sfackler/rust-openssl" }\n'
        )
        cargo_lock_content = self._cargo_lock_with_package(
            "dd-rust-license-tool",
            "1.0.6",
        )
        (
            _,
            mock_write_file,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=self._binary_metadata_return("dd-rust-license-tool"),
            path_exists_return=[True, True, True],
            cargo_lock_content=cargo_lock_content,
            extracted_members=["dd-rust-license-tool-1.0.6/Cargo.toml"],
        )
        mock_open_file.side_effect = [cargo_lock_content, config_content]
        mock_download_url.side_effect = [
            json.dumps(
                {
                    "version": {
                        "num": "1.0.6",
                        "repository": (
                            "https://github.com/DataDog/dd-rust-license-tool"
                        ),
                    },
                }
            ).encode(),
            b"crate archive",
        ]

        result = resolver.resolve_package("dd-rust-license-tool")

        assert (
            result
            == "/cache/dd-rust-license-tool/crate-source/dd-rust-license-tool-1.0.6"
        )
        source_code_manager.get_code.assert_called_once_with(
            "https://github.com/DataDog/dd-rust-license-tool"
        )
        assert mock_write_file.call_count == 3
        mock_write_file.assert_called_with(
            "/cache/dd-rust-license-tool/crate-source/"
            "dd-rust-license-tool-1.0.6/license-tool.toml",
            config_content,
        )
        mock_run_command.assert_has_calls(
            [
                call(
                    ["cargo", "generate-lockfile"],
                    cwd="/cache/dd-rust-license-tool",
                ),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/dd-rust-license-tool",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_has_calls(
            [
                call("/cache/dd-rust-license-tool/Cargo.lock"),
                call(
                    "/cache/dd-rust-license-tool/crate-source/"
                    "dd-rust-license-tool-1.0.6/Cargo.toml"
                ),
                call(
                    "/cache/repositories/dd-rust-license-tool/license-tool.toml",
                ),
            ]
        )
        assert mock_path_exists.call_count == 3
        mock_open_file.assert_has_calls(
            [
                call("/cache/dd-rust-license-tool/Cargo.lock"),
                call("/cache/repositories/dd-rust-license-tool/license-tool.toml"),
            ]
        )
        assert mock_open_file.call_count == 2
        mock_download_url.assert_has_calls(
            [
                call(
                    "https://crates.io/api/v1/crates/dd-rust-license-tool/1.0.6",
                    user_agent=CRATES_IO_USER_AGENT,
                ),
                call(
                    "https://crates.io/api/v1/crates/dd-rust-license-tool/1.0.6/download",
                    user_agent=CRATES_IO_USER_AGENT,
                ),
            ]
        )
        assert mock_download_url.call_count == 2
        mock_extract_tar_gz.assert_called_once_with(
            b"crate archive",
            "/cache/dd-rust-license-tool/crate-source",
        )

    def test_crates_io_repository_metadata_failure_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        mock_download_url = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.download_url",
            side_effect=OSError("network unavailable"),
        )

        with caplog.at_level(logging.WARNING):
            result = self.resolver._get_crates_io_repository("serde", "1.0.0")

        assert result is None
        assert "Could not retrieve crates.io metadata" in caplog.text
        mock_download_url.assert_called_once_with(
            "https://crates.io/api/v1/crates/serde/1.0.0",
            user_agent=CRATES_IO_USER_AGENT,
        )

    def test_get_resolved_crate_version_reads_cargo_lock(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_open_file = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.open_file",
            return_value=self._cargo_lock_with_package("dd-rust-license-tool", "1.0.6"),
        )

        result = self.resolver._get_resolved_crate_version(
            "/cache/dd-rust-license-tool/Cargo.lock",
            "dd-rust-license-tool",
        )

        assert result == "1.0.6"
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")

    def test_metadata_failure_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(1, "metadata stdout", "metadata stderr"),
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("serde")

        assert result is None
        assert any(
            "cargo metadata failed" in record.message for record in caplog.records
        )
        mock_run_command.assert_has_calls(
            [
                call(["cargo", "generate-lockfile"], cwd="/cache/serde"),
                call(
                    ["cargo", "metadata", "--format-version", "1"], cwd="/cache/serde"
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_called_once_with("/cache/serde/Cargo.lock")
        mock_open_file.assert_not_called()
        mock_download_url.assert_not_called()
        mock_extract_tar_gz.assert_not_called()

    def test_metadata_exception_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(mocker)
        mock_run_command.side_effect = [
            (0, "cargo generate-lockfile completed", ""),
            OSError("cargo metadata failed"),
        ]

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("serde")

        assert result is None
        assert any(
            "Failed to inspect resolved Rust crate" in record.message
            for record in caplog.records
        )
        mock_run_command.assert_has_calls(
            [
                call(["cargo", "generate-lockfile"], cwd="/cache/serde"),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/serde",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_called_once_with("/cache/serde/Cargo.lock")
        mock_open_file.assert_not_called()
        mock_download_url.assert_not_called()
        mock_extract_tar_gz.assert_not_called()

    def test_invalid_metadata_json_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(0, "not json", ""),
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("serde")

        assert result is None
        assert any(
            "Failed to parse cargo metadata" in record.message
            for record in caplog.records
        )
        mock_run_command.assert_has_calls(
            [
                call(["cargo", "generate-lockfile"], cwd="/cache/serde"),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/serde",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_called_once_with("/cache/serde/Cargo.lock")
        mock_open_file.assert_not_called()
        mock_download_url.assert_not_called()
        mock_extract_tar_gz.assert_not_called()

    def test_metadata_non_object_returns_none(self, caplog: LogCaptureFixture) -> None:
        with caplog.at_level(logging.ERROR):
            result = self.resolver._metadata_contains_crate("[]", "serde")

        assert result is None
        assert any(
            "was not a JSON object" in record.message for record in caplog.records
        )

    def test_metadata_without_packages_returns_none(
        self, caplog: LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.ERROR):
            result = self.resolver._metadata_contains_crate(
                json.dumps({"workspace_members": []}),
                "serde",
            )

        assert result is None
        assert any(
            "did not contain a packages list" in record.message
            for record in caplog.records
        )

    def test_metadata_missing_crate_without_lib_warning_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=(
                0,
                json.dumps({"packages": [{"name": SYNTHETIC_PACKAGE_NAME}]}),
                "warning: unrelated cargo warning",
            ),
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("serde")

        assert result is None
        assert any(
            "did not report a missing lib target" in record.message
            for record in caplog.records
        )
        mock_run_command.assert_has_calls(
            [
                call(["cargo", "generate-lockfile"], cwd="/cache/serde"),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/serde",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_called_once_with("/cache/serde/Cargo.lock")
        mock_open_file.assert_not_called()
        mock_download_url.assert_not_called()
        mock_extract_tar_gz.assert_not_called()

    def test_missing_lib_target_warning_detection_requires_all_terms(self) -> None:
        assert self.resolver._metadata_reports_missing_lib_target(
            "warning: Ignoring invalid dependency `serde` which is missing a lib target",
            "serde",
        )
        assert not self.resolver._metadata_reports_missing_lib_target(
            "warning: ignoring invalid dependency `serde`",
            "serde",
        )
        assert not self.resolver._metadata_reports_missing_lib_target(
            "warning: missing a lib target for unrelated",
            "serde",
        )
        assert not self.resolver._metadata_reports_missing_lib_target(
            "warning: ignoring invalid dependency `serde` which is missing a lib target",
            "tokio",
        )

    def test_metadata_contains_crate_ignores_non_object_packages(self) -> None:
        result = self.resolver._metadata_contains_crate(
            json.dumps(
                {
                    "packages": [
                        "serde",
                        {"name": "serde_json"},
                        {"name": "serde"},
                    ]
                }
            ),
            "serde",
        )

        assert result is True

    def test_metadata_contains_crate_returns_false_when_absent(self) -> None:
        result = self.resolver._metadata_contains_crate(
            json.dumps({"packages": [{"name": "serde_json"}]}),
            "serde",
        )

        assert result is False

    def test_missing_package_in_lockfile_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=self._binary_metadata_return("dd-rust-license-tool"),
            cargo_lock_content=self._cargo_lock_with_package("other", "1.0.0"),
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("dd-rust-license-tool")

        assert result is None
        assert any(
            "Could not find resolved version" in record.message
            for record in caplog.records
        )
        mock_run_command.assert_has_calls(
            [
                call(
                    ["cargo", "generate-lockfile"],
                    cwd="/cache/dd-rust-license-tool",
                ),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/dd-rust-license-tool",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_called_once_with(
            "/cache/dd-rust-license-tool/Cargo.lock"
        )
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")
        mock_download_url.assert_not_called()
        mock_extract_tar_gz.assert_not_called()

    def test_lockfile_read_failure_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        mock_open_file = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.open_file",
            side_effect=OSError("permission denied"),
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver._get_resolved_crate_version(
                "/cache/dd-rust-license-tool/Cargo.lock",
                "dd-rust-license-tool",
            )

        assert result is None
        assert any(
            "Failed to read Cargo.lock" in record.message for record in caplog.records
        )
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")

    def test_lockfile_parse_failure_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        mock_open_file = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.open_file",
            return_value="[[package]",
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver._get_resolved_crate_version(
                "/cache/dd-rust-license-tool/Cargo.lock",
                "dd-rust-license-tool",
            )

        assert result is None
        assert any(
            "Failed to parse Cargo.lock" in record.message for record in caplog.records
        )
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")

    def test_lockfile_without_packages_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        mock_open_file = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.open_file",
            return_value="version = 4\n",
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver._get_resolved_crate_version(
                "/cache/dd-rust-license-tool/Cargo.lock",
                "dd-rust-license-tool",
            )

        assert result is None
        assert any(
            "did not contain packages" in record.message for record in caplog.records
        )
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")

    def test_lockfile_ignores_non_object_packages_and_missing_versions(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_open_file = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.open_file",
            return_value=(
                "[[package]]\n"
                'name = "other"\n'
                'version = "1.0.0"\n'
                "\n"
                "[[package]]\n"
                'name = "serde"\n'
                "version = 123\n"
            ),
        )

        result = self.resolver._get_resolved_crate_version(
            "/cache/serde/Cargo.lock",
            "serde",
        )

        assert result is None
        mock_open_file.assert_called_once_with("/cache/serde/Cargo.lock")

    def test_lockfile_non_table_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        mock_open_file = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.open_file",
            return_value="version = 4\n",
        )
        mock_tomllib_loads = mocker.patch(
            "dd_license_attribution.artifact_management.rust_package_resolver.tomllib.loads",
            return_value=[],
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver._get_resolved_crate_version(
                "/cache/dd-rust-license-tool/Cargo.lock",
                "dd-rust-license-tool",
            )

        assert result is None
        assert any(
            "was not a TOML table" in record.message for record in caplog.records
        )
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")
        mock_tomllib_loads.assert_called_once_with("version = 4\n")

    def test_download_failure_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=self._binary_metadata_return("dd-rust-license-tool"),
            cargo_lock_content=self._cargo_lock_with_package(
                "dd-rust-license-tool",
                "1.0.6",
            ),
        )
        mock_download_url.side_effect = OSError("network unavailable")

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("dd-rust-license-tool")

        assert result is None
        assert any(
            "Failed to download or extract Rust crate source" in record.message
            for record in caplog.records
        )
        mock_run_command.assert_has_calls(
            [
                call(
                    ["cargo", "generate-lockfile"],
                    cwd="/cache/dd-rust-license-tool",
                ),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/dd-rust-license-tool",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_called_once_with(
            "/cache/dd-rust-license-tool/Cargo.lock"
        )
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")
        mock_download_url.assert_called_once_with(
            "https://crates.io/api/v1/crates/dd-rust-license-tool/1.0.6/download",
            user_agent=CRATES_IO_USER_AGENT,
        )
        mock_extract_tar_gz.assert_not_called()

    def test_unsafe_archive_path_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=self._binary_metadata_return("dd-rust-license-tool"),
            cargo_lock_content=self._cargo_lock_with_package(
                "dd-rust-license-tool",
                "1.0.6",
            ),
        )
        mock_extract_tar_gz.side_effect = ValueError("Unsafe archive path: ../x")

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("dd-rust-license-tool")

        assert result is None
        assert any("Unsafe archive path" in record.message for record in caplog.records)
        mock_run_command.assert_has_calls(
            [
                call(
                    ["cargo", "generate-lockfile"],
                    cwd="/cache/dd-rust-license-tool",
                ),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/dd-rust-license-tool",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_called_once_with(
            "/cache/dd-rust-license-tool/Cargo.lock"
        )
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")
        mock_download_url.assert_called_once_with(
            "https://crates.io/api/v1/crates/dd-rust-license-tool/1.0.6/download",
            user_agent=CRATES_IO_USER_AGENT,
        )
        mock_extract_tar_gz.assert_called_once_with(
            b"crate archive",
            "/cache/dd-rust-license-tool/crate-source",
        )

    def test_unexpected_extracted_members_return_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=self._binary_metadata_return("dd-rust-license-tool"),
            cargo_lock_content=self._cargo_lock_with_package(
                "dd-rust-license-tool",
                "1.0.6",
            ),
            extracted_members=["one/Cargo.toml", "two/Cargo.toml"],
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("dd-rust-license-tool")

        assert result is None
        assert any(
            "Could not identify extracted source root" in record.message
            for record in caplog.records
        )
        mock_run_command.assert_has_calls(
            [
                call(
                    ["cargo", "generate-lockfile"],
                    cwd="/cache/dd-rust-license-tool",
                ),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/dd-rust-license-tool",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_called_once_with(
            "/cache/dd-rust-license-tool/Cargo.lock"
        )
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")
        mock_download_url.assert_called_once_with(
            "https://crates.io/api/v1/crates/dd-rust-license-tool/1.0.6/download",
            user_agent=CRATES_IO_USER_AGENT,
        )
        mock_extract_tar_gz.assert_called_once_with(
            b"crate archive",
            "/cache/dd-rust-license-tool/crate-source",
        )

    def test_extracted_root_falls_back_to_single_top_level_member(self) -> None:
        result = self.resolver._get_extracted_crate_root(
            "/cache/source",
            ["renamed-root/Cargo.toml", "renamed-root/Cargo.lock"],
            "dd-rust-license-tool",
            "1.0.6",
        )

        assert result == "/cache/source/renamed-root"

    def test_extracted_root_prefers_expected_root_when_present(self) -> None:
        result = self.resolver._get_extracted_crate_root(
            "/cache/source",
            ["other-root/Cargo.toml", "dd-rust-license-tool-1.0.6/src/main.rs"],
            "dd-rust-license-tool",
            "1.0.6",
        )

        assert result == "/cache/source/dd-rust-license-tool-1.0.6"

    def test_extracted_root_returns_none_for_multiple_top_level_members(self) -> None:
        result = self.resolver._get_extracted_crate_root(
            "/cache/source",
            ["one/Cargo.toml", "two/Cargo.toml"],
            "dd-rust-license-tool",
            "1.0.6",
        )

        assert result is None

    def test_extracted_root_returns_none_for_empty_member_list(self) -> None:
        result = self.resolver._get_extracted_crate_root(
            "/cache/source",
            [],
            "dd-rust-license-tool",
            "1.0.6",
        )

        assert result is None

    def test_missing_extracted_cargo_toml_returns_none(
        self, mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
    ) -> None:
        (
            _,
            _,
            mock_run_command,
            mock_path_exists,
            mock_open_file,
            mock_download_url,
            mock_extract_tar_gz,
        ) = self._setup_mocks(
            mocker,
            metadata_return=self._binary_metadata_return("dd-rust-license-tool"),
            path_exists_return=[True, False],
            cargo_lock_content=self._cargo_lock_with_package(
                "dd-rust-license-tool",
                "1.0.6",
            ),
            extracted_members=["dd-rust-license-tool-1.0.6/README.md"],
        )

        with caplog.at_level(logging.ERROR):
            result = self.resolver.resolve_package("dd-rust-license-tool")

        assert result is None
        assert any(
            "did not contain Cargo.toml" in record.message for record in caplog.records
        )
        mock_run_command.assert_has_calls(
            [
                call(
                    ["cargo", "generate-lockfile"],
                    cwd="/cache/dd-rust-license-tool",
                ),
                call(
                    ["cargo", "metadata", "--format-version", "1"],
                    cwd="/cache/dd-rust-license-tool",
                ),
            ]
        )
        assert mock_run_command.call_count == 2
        mock_path_exists.assert_has_calls(
            [
                call("/cache/dd-rust-license-tool/Cargo.lock"),
                call(
                    "/cache/dd-rust-license-tool/crate-source/"
                    "dd-rust-license-tool-1.0.6/Cargo.toml"
                ),
            ]
        )
        assert mock_path_exists.call_count == 2
        mock_open_file.assert_called_once_with("/cache/dd-rust-license-tool/Cargo.lock")
        mock_download_url.assert_called_once_with(
            "https://crates.io/api/v1/crates/dd-rust-license-tool/1.0.6/download",
            user_agent=CRATES_IO_USER_AGENT,
        )
        mock_extract_tar_gz.assert_called_once_with(
            b"crate archive",
            "/cache/dd-rust-license-tool/crate-source",
        )
