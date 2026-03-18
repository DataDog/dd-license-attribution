# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from typing import Any

import pytest_mock

from dd_license_attribution.artifact_management.pypi_package_resolver import (
    PypiPackageResolver,
)


class TestParsePypiSpec:
    def test_simple_name_returns_empty_version(self) -> None:
        resolver = PypiPackageResolver("/cache")
        name, version = resolver._parse_pypi_spec("requests")
        assert name == "requests"
        assert version == ""

    def test_exact_version(self) -> None:
        resolver = PypiPackageResolver("/cache")
        name, version = resolver._parse_pypi_spec("requests==2.31.0")
        assert name == "requests"
        assert version == "==2.31.0"

    def test_gte_version(self) -> None:
        resolver = PypiPackageResolver("/cache")
        name, version = resolver._parse_pypi_spec("requests>=2.0")
        assert name == "requests"
        assert version == ">=2.0"

    def test_compatible_version(self) -> None:
        resolver = PypiPackageResolver("/cache")
        name, version = resolver._parse_pypi_spec("package~=1.0")
        assert name == "package"
        assert version == "~=1.0"

    def test_lt_version(self) -> None:
        resolver = PypiPackageResolver("/cache")
        name, version = resolver._parse_pypi_spec("package<2.0")
        assert name == "package"
        assert version == "<2.0"

    def test_ne_version(self) -> None:
        resolver = PypiPackageResolver("/cache")
        name, version = resolver._parse_pypi_spec("package!=1.5")
        assert name == "package"
        assert version == "!=1.5"

    def test_extras(self) -> None:
        resolver = PypiPackageResolver("/cache")
        name, version = resolver._parse_pypi_spec("Flask[async]")
        assert name == "Flask[async]"
        assert version == ""

    def test_extras_with_version(self) -> None:
        resolver = PypiPackageResolver("/cache")
        name, version = resolver._parse_pypi_spec("Flask[async]==2.0.0")
        assert name == "Flask[async]"
        assert version == "==2.0.0"

    def test_non_matching_spec_returns_spec_as_name(self) -> None:
        resolver = PypiPackageResolver("/cache")
        # A spec with characters that don't match the regex falls back to (spec, "")
        spec = "!!!invalid!!!"
        name, version = resolver._parse_pypi_spec(spec)
        assert name == spec
        assert version == ""


class TestResolvePackage:
    def setup_method(self) -> None:
        self.resolver = PypiPackageResolver("/cache")

    def _setup_mocks(
        self,
        mocker: pytest_mock.MockFixture,
        path_exists_return: bool = True,
        write_file_side_effect: Exception | None = None,
    ) -> tuple[Any, Any, Any]:
        def fake_path_join(*args: Any) -> str:
            return "/".join(args)

        mock_create_dirs = mocker.patch(
            "dd_license_attribution.artifact_management.pypi_package_resolver.create_dirs"
        )
        mock_write_file = mocker.patch(
            "dd_license_attribution.artifact_management.pypi_package_resolver.write_file"
        )
        if write_file_side_effect is not None:
            mock_write_file.side_effect = write_file_side_effect
        mock_path_exists = mocker.patch(
            "dd_license_attribution.artifact_management.pypi_package_resolver.path_exists",
            return_value=path_exists_return,
        )
        mocker.patch(
            "dd_license_attribution.artifact_management.pypi_package_resolver.path_join",
            side_effect=fake_path_join,
        )

        return mock_create_dirs, mock_write_file, mock_path_exists

    def test_happy_path_creates_dir_and_pyproject_toml(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, mock_write_file, mock_path_exists = self._setup_mocks(mocker)

        result = self.resolver.resolve_package("requests==2.31.0")

        assert result == "/cache/requests"
        mock_create_dirs.assert_called_once_with("/cache/requests")

        write_call_args = mock_write_file.call_args
        assert write_call_args[0][0] == "/cache/requests/pyproject.toml"
        written_content = write_call_args[0][1]
        assert "ddla-pypi-resolve" in written_content
        assert "requests==2.31.0" in written_content

        mock_path_exists.assert_called_once_with("/cache/requests/pyproject.toml")

    def test_sanitizes_package_name_for_directory(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        mock_create_dirs, _, _ = self._setup_mocks(mocker)

        result = self.resolver.resolve_package("Flask[async]==2.0.0")

        assert result is not None
        mock_create_dirs.assert_called_once_with("/cache/Flask_async_")

    def test_returns_none_when_write_fails(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, _ = self._setup_mocks(
            mocker, write_file_side_effect=OSError("disk full")
        )

        result = self.resolver.resolve_package("requests")

        assert result is None
        mock_write_file.assert_called_once()

    def test_unpinned_dependency_creates_correct_install_requires(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("requests")

        written_content = mock_write_file.call_args[0][1]
        assert "requests" in written_content
        assert "==" not in written_content

    def test_versioned_dependency_creates_correct_install_requires(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, mock_write_file, _ = self._setup_mocks(mocker)

        self.resolver.resolve_package("requests>=2.0,<3.0")

        written_content = mock_write_file.call_args[0][1]
        assert "requests>=2.0,<3.0" in written_content

    def test_path_exists_false_returns_none(
        self, mocker: pytest_mock.MockFixture
    ) -> None:
        _, _, mock_path_exists = self._setup_mocks(mocker, path_exists_return=False)

        result = self.resolver.resolve_package("requests==2.31.0")

        assert result is None
        mock_path_exists.assert_called_once_with("/cache/requests/pyproject.toml")
