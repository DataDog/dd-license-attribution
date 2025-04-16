# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import typing

import pytest_mock

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.pypi_collection_strategy import (
    PypiMetadataCollectionStrategy,
)


class MockedRequestsResponse:
    def __init__(
        self, status_code: int, json_ret: dict[str, dict[str, typing.Any]]
    ) -> None:
        self.status_code = status_code
        self.json_ret = json_ret

    def json(self) -> dict[str, dict[str, str]]:
        return self.json_ret


def test_pypi_collection_strategy_do_not_decrement_list_of_dependencies_if_not_python_related(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    python_env_manager_mock = mocker.Mock()

    strategy = PypiMetadataCollectionStrategy(
        "package1", source_code_manager_mock, python_env_manager_mock, ProjectScope.ALL
    )

    initial_metadata = [
        Metadata(
            name="package1",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package3",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == initial_metadata


def test_pypi_collection_strategy_is_bypassed_if_only_root_project_is_required(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    python_env_manager_mock = mocker.Mock()
    strategy = PypiMetadataCollectionStrategy(
        "package1",
        source_code_manager_mock,
        python_env_manager_mock,
        ProjectScope.ONLY_ROOT_PROJECT,
    )

    initial_metadata = [
        Metadata(
            name="package1",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package3",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == initial_metadata


def test_pypi_collection_strategy_adds_pypi_metadata_to_list_of_dependencies(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/20220101_000000Z/org-package1/main",
        local_full_path="cache_dir/20220101_000000Z/org-package1/main",
    )
    python_env_manager_mock = mocker.Mock()
    python_env_manager_mock.get_environment.return_value = (
        "cache_dir/20220101_000000Z/org_package1_virtualenv"
    )
    get_dependencies_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.PythonEnvManager.get_dependencies",
        return_value=[
            ("package3", "1.2.3"),
            ("package4", "2.3.4"),
            ("package5", "3.4.5"),
        ],
    )

    mock_request = mocker.patch("requests.get")
    mock_request.side_effect = [
        MockedRequestsResponse(
            200,
            {
                "info": {
                    "license": "MIT",
                    "author": "Datadog Inc.",
                    "name": "package3",
                    "version": "1.2.3",
                }
            },
        ),
        MockedRequestsResponse(
            200,
            {
                "info": {
                    "license": "APACHE-2.0",
                    "author": "Datadog Inc.",
                    "name": "package4",
                    "version": "2.3.4",
                }
            },
        ),
        MockedRequestsResponse(
            200,
            {
                "info": {
                    "license": "MIT",
                    "author": "Datadog",
                    "name": "package5",
                    "version": "3.4.5",
                }
            },
        ),
    ]

    strategy = PypiMetadataCollectionStrategy(
        "github.com/org/package1",
        source_code_manager_mock,
        python_env_manager_mock,
        ProjectScope.ALL,
    )

    initial_metadata = [
        Metadata(
            name="github.com/org/package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="github.com/org/package1",
            origin="https://github.com/org/package1",
            local_src_path="cache_dir/20220101_000000Z/org-package1/main",
            version=None,
            license=[],
            copyright=[],
        ),
        Metadata(
            name="package3",
            origin="pypi:package3",
            local_src_path=None,
            version="1.2.3",
            license=["MIT"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package4",
            origin="pypi:package4",
            local_src_path=None,
            version="2.3.4",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package5",
            origin="pypi:package5",
            local_src_path=None,
            version="3.4.5",
            license=["MIT"],
            copyright=["Datadog"],
        ),
    ]

    assert result == expected_metadata

    source_code_manager_mock.get_code.assert_called_once_with(
        "https://github.com/org/package1"
    )
    python_env_manager_mock.get_environment.assert_called_once_with(
        "cache_dir/20220101_000000Z/org-package1/main"
    )
    get_dependencies_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/org_package1_virtualenv"
    )
    mock_request.assert_has_calls(
        [
            mocker.call("https://pypi.org/pypi/package3/1.2.3/json"),
            mocker.call("https://pypi.org/pypi/package4/2.3.4/json"),
            mocker.call("https://pypi.org/pypi/package5/3.4.5/json"),
        ]
    )


def test_dependency_in_initial_metadata_is_augmented_and_not_duplicated_when_found_in_pyenv(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    python_env_manager_mock = mocker.Mock()
    python_env_manager_mock.get_environment.return_value = (
        "cache_dir/20220101_000000Z/org_top_package_virtualenv"
    )
    get_dependencies_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.PythonEnvManager.get_dependencies",
        return_value=[
            ("pytest", "21.4.0"),
        ],
    )
    mock_request = mocker.patch("requests.get")
    mock_request.return_value = MockedRequestsResponse(
        200,
        {
            "info": {
                "license": "MIT",
                "author": "Datadog Inc.",
                "name": "pytest",
                "version": "21.4.0",
                "project_urls": {"Source": "https://github.com/org2/pytest"},
            }
        },
    )

    strategy = PypiMetadataCollectionStrategy(
        "top_package",
        source_code_manager_mock,
        python_env_manager_mock,
        ProjectScope.ONLY_ROOT_PROJECT,
    )

    initial_metadata = [
        Metadata(
            name="top_package",
            version="1.0.1",
            origin="https://github.com/org/top_package",
            local_src_path="/path/to/top_package",
            license=[],
            copyright=[],
        ),
        Metadata(
            name="pytest",
            version=None,
            origin=None,
            local_src_path=None,
            license=[],
            copyright=[],
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="top_package",
            version="1.0.1",
            origin="https://github.com/org/top_package",
            local_src_path="/path/to/top_package",
            license=[],
            copyright=[],
        ),
        Metadata(
            name="pytest",
            version="21.4.0",
            origin="https://github.com/org2/pytest",
            local_src_path=None,
            license=["MIT"],
            copyright=["Datadog Inc."],
        ),
    ]
    assert updated_metadata == expected_metadata
    get_dependencies_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/org_top_package_virtualenv"
    )
    mock_request.assert_called_once_with("https://pypi.org/pypi/pytest/21.4.0/json")
    source_code_manager_mock.get_code.assert_not_called()
    python_env_manager_mock.get_environment.assert_called_once_with(
        "/path/to/top_package"
    )
    mock_request.assert_called_once_with("https://pypi.org/pypi/pytest/21.4.0/json")


def test_dependency_in_initial_metadata_is_augmented_and_github_origin_is_preferred_over_a_non_github_origin(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    python_env_manager_mock = mocker.Mock()
    python_env_manager_mock.get_environment.return_value = (
        "cache_dir/20220101_000000Z/org_top_package_virtualenv"
    )
    get_dependencies_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.PythonEnvManager.get_dependencies",
        return_value=[
            ("pytest", "21.4.0"),
        ],
    )
    mock_request = mocker.patch("requests.get")
    mock_request.return_value = MockedRequestsResponse(
        200,
        {
            "info": {
                "license": "MIT",
                "author": "Datadog Inc.",
                "name": "pytest",
                "version": "21.4.0",
                "project_urls": {"Source Code": "not_a_github_url"},
            }
        },
    )

    strategy = PypiMetadataCollectionStrategy(
        "top_package",
        source_code_manager_mock,
        python_env_manager_mock,
        ProjectScope.ALL,
    )

    initial_metadata = [
        Metadata(
            name="top_package",
            version="1.0.1",
            origin="https://github.com/org/top_package",
            local_src_path="/path/to/top_package",
            license=[],
            copyright=[],
        ),
        Metadata(
            name="pytest",
            version=None,
            origin="https://github.com/org2/pytest",
            local_src_path=None,
            license=[],
            copyright=[],
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="top_package",
            version="1.0.1",
            origin="https://github.com/org/top_package",
            local_src_path="/path/to/top_package",
            license=[],
            copyright=[],
        ),
        Metadata(
            name="pytest",
            version="21.4.0",
            origin="https://github.com/org2/pytest",
            local_src_path=None,
            license=["MIT"],
            copyright=["Datadog Inc."],
        ),
    ]
    assert updated_metadata == expected_metadata
    get_dependencies_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/org_top_package_virtualenv"
    )
    mock_request.assert_called_once_with("https://pypi.org/pypi/pytest/21.4.0/json")
    source_code_manager_mock.get_code.assert_not_called()
    python_env_manager_mock.get_environment.assert_called_once_with(
        "/path/to/top_package"
    )
    mock_request.assert_called_once_with("https://pypi.org/pypi/pytest/21.4.0/json")


def test_dependency_in_initial_metadata_is_augmented_the_right_github_url_is_found(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    python_env_manager_mock = mocker.Mock()
    python_env_manager_mock.get_environment.return_value = (
        "cache_dir/20220101_000000Z/org_top_package_virtualenv"
    )
    get_dependencies_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.PythonEnvManager.get_dependencies",
        return_value=[
            ("pytest", "21.4.0"),
        ],
    )
    mock_request = mocker.patch("requests.get")
    mock_request.return_value = MockedRequestsResponse(
        200,
        {
            "info": {
                "license": "MIT",
                "author": "Datadog Inc.",
                "name": "pytest",
                "version": "21.4.0",
                "project_urls": {
                    "Source Code": "not_a_github_url",
                    "GitHub": "https://github.com/org2/pytest",
                },
            }
        },
    )

    strategy = PypiMetadataCollectionStrategy(
        "top_package",
        source_code_manager_mock,
        python_env_manager_mock,
        ProjectScope.ALL,
    )

    initial_metadata = [
        Metadata(
            name="top_package",
            version="1.0.1",
            origin="https://github.com/org/top_package",
            local_src_path="/path/to/top_package",
            license=[],
            copyright=[],
        ),
        Metadata(
            name="pytest",
            version=None,
            origin="",
            local_src_path=None,
            license=[],
            copyright=[],
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="top_package",
            version="1.0.1",
            origin="https://github.com/org/top_package",
            local_src_path="/path/to/top_package",
            license=[],
            copyright=[],
        ),
        Metadata(
            name="pytest",
            version="21.4.0",
            origin="https://github.com/org2/pytest",
            local_src_path=None,
            license=["MIT"],
            copyright=["Datadog Inc."],
        ),
    ]
    assert updated_metadata == expected_metadata
    get_dependencies_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/org_top_package_virtualenv"
    )
    mock_request.assert_called_once_with("https://pypi.org/pypi/pytest/21.4.0/json")
    source_code_manager_mock.get_code.assert_not_called()
    python_env_manager_mock.get_environment.assert_called_once_with(
        "/path/to/top_package"
    )
    mock_request.assert_called_once_with("https://pypi.org/pypi/pytest/21.4.0/json")
