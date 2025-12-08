# SPDX-License-Identifier: Apache-2.0
#
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
from dd_license_attribution.metadata_collector.strategies.cleanup_copyright_metadata_strategy import (
    CleanupCopyrightMetadataStrategy,
)
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
    source_code_manager_mock.get_canonical_urls.return_value = ("package1", None)
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
    source_code_manager_mock.get_canonical_urls.return_value = ("package1", None)
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
    source_code_manager_mock.get_canonical_urls.return_value = (
        "github.com/org/package1",
        None,
    )
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


def test_pypi_collection_strategy_handles_company_names_in_copyright_when_dependency_in_initial_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = ("test-package", None)
    python_env_manager_mock = mocker.Mock()
    python_env_manager_mock.get_environment.return_value = "dummy_env"
    mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.PythonEnvManager.get_dependencies",
        return_value=[("test-package", "1.0.0")],
    )

    mock_request = mocker.patch("requests.get")
    mock_request.return_value = MockedRequestsResponse(
        200,
        {
            "info": {
                "name": "test-package",
                "version": "1.0.0",
                "author": "Company A, Copyright 2024 Company B, Inc. and its affiliates, Company C, llc, Company Datadog",
            }
        },
    )

    strategy = PypiMetadataCollectionStrategy(
        "test-package",
        source_code_manager_mock,
        python_env_manager_mock,
        ProjectScope.ALL,
    )
    cleanup_copyright_metadata_strategy = CleanupCopyrightMetadataStrategy()

    result = strategy.augment_metadata(
        [
            Metadata(
                name="test-package",
                version=None,
                origin=None,
                local_src_path="/dummy/path",
                license=[],
                copyright=[],
            )
        ]
    )
    cleaned_result = cleanup_copyright_metadata_strategy.augment_metadata(result)

    assert cleaned_result[0].copyright == [
        "Company A",
        "Company B, Inc. and its affiliates",
        "Company C, llc",
        "Company Datadog",
    ]


def test_pypi_collection_strategy_handles_company_names_in_new_metadata_entry(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = ("top-package", None)
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/test-org/top-package",
        branch="main",
        local_root_path="cache_dir/test-package",
        local_full_path="cache_dir/test-package",
    )
    python_env_manager_mock = mocker.Mock()
    python_env_manager_mock.get_environment.return_value = "dummy_env"
    mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.PythonEnvManager.get_dependencies",
        return_value=[("test-package", "1.0.0")],
    )

    mock_request = mocker.patch("requests.get")
    mock_request.return_value = MockedRequestsResponse(
        200,
        {
            "info": {
                "name": "test-package",
                "version": "1.0.0",
                "author": "Company A, Copyright 2024 Company B, Inc. and its affiliates, Company C, llc, Company Datadog",
            }
        },
    )

    strategy = PypiMetadataCollectionStrategy(
        "top-package",
        source_code_manager_mock,
        python_env_manager_mock,
        ProjectScope.ALL,
    )
    cleanup_copyright_metadata_strategy = CleanupCopyrightMetadataStrategy()

    initial_metadata_only_contains_top_package = [
        Metadata(
            name="top-package",
            version=None,
            origin="https://github.com/test-org/top-package",
            local_src_path=None,
            license=[],
            copyright=[],
        )
    ]
    result = strategy.augment_metadata(initial_metadata_only_contains_top_package)
    cleaned_result = cleanup_copyright_metadata_strategy.augment_metadata(result)

    assert len(cleaned_result) == 2
    assert cleaned_result[0].name == "top-package"
    assert cleaned_result[1].copyright == [
        "Company A",
        "Company B, Inc. and its affiliates",
        "Company C, llc",
        "Company Datadog",
    ]


def test_dependency_in_initial_metadata_is_augmented_and_not_duplicated_when_found_in_pyenv(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = ("top_package", None)
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
    source_code_manager_mock.get_canonical_urls.return_value = ("top_package", None)
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
    source_code_manager_mock.get_canonical_urls.return_value = ("top_package", None)
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


def test_pypi_collection_strategy_ignores_none_project_urls(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "github.com/org/package1",
        None,
    )
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
                    "project_urls": {
                        "Homepage": "https://example.com",
                        "Source": None,
                        "Repository": "https://github.com/org/package3",
                    },
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
            origin="https://github.com/org/package3",
            local_src_path=None,
            version="1.2.3",
            license=["MIT"],
            copyright=["Datadog Inc."],
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
    mock_request.assert_called_once_with("https://pypi.org/pypi/package3/1.2.3/json")


def test_pypi_collection_strategy_handles_case_insensitive_project_url_keys(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that project_urls keys are matched case-insensitively.

    This test verifies that keys like 'Homepage', 'HOMEPAGE', 'homepage',
    'GitHub', 'GITHUB', 'github', etc. are all recognized and handled correctly.
    """
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "github.com/org/package1",
        None,
    )
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
            ("package_with_uppercase_homepage", "1.0.0"),
            ("package_with_lowercase_github", "2.0.0"),
            ("package_with_mixedcase_repository", "3.0.0"),
            ("package_with_uppercase_source_code", "4.0.0"),
        ],
    )

    mock_request = mocker.patch("requests.get")
    mock_request.side_effect = [
        # Test 1: HOMEPAGE in all caps
        MockedRequestsResponse(
            200,
            {
                "info": {
                    "license": "MIT",
                    "author": "Author A",
                    "name": "package_with_uppercase_homepage",
                    "version": "1.0.0",
                    "project_urls": {
                        "HOMEPAGE": "https://github.com/org/package_uppercase_homepage"
                    },
                }
            },
        ),
        # Test 2: github in all lowercase
        MockedRequestsResponse(
            200,
            {
                "info": {
                    "license": "Apache-2.0",
                    "author": "Author B",
                    "name": "package_with_lowercase_github",
                    "version": "2.0.0",
                    "project_urls": {
                        "homepage": "not_a_valid_url",
                        "github": "https://github.com/org/package_lowercase_github",
                    },
                }
            },
        ),
        # Test 3: RePoSiToRy in mixed case
        MockedRequestsResponse(
            200,
            {
                "info": {
                    "license": "BSD-3-Clause",
                    "author": "Author C",
                    "name": "package_with_mixedcase_repository",
                    "version": "3.0.0",
                    "project_urls": {
                        "RePoSiToRy": "https://github.com/org/package_mixedcase_repo"
                    },
                }
            },
        ),
        # Test 4: SOURCE CODE in all caps (tests multi-word key)
        MockedRequestsResponse(
            200,
            {
                "info": {
                    "license": "GPL-3.0",
                    "author": "Author D",
                    "name": "package_with_uppercase_source_code",
                    "version": "4.0.0",
                    "project_urls": {
                        "SOURCE CODE": "https://github.com/org/package_uppercase_source"
                    },
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

    # Verify that all packages were found and their GitHub URLs were extracted correctly
    # despite different capitalizations of the project_urls keys
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
            name="package_with_uppercase_homepage",
            origin="https://github.com/org/package_uppercase_homepage",
            local_src_path=None,
            version="1.0.0",
            license=["MIT"],
            copyright=["Author A"],
        ),
        Metadata(
            name="package_with_lowercase_github",
            origin="https://github.com/org/package_lowercase_github",
            local_src_path=None,
            version="2.0.0",
            license=["Apache-2.0"],
            copyright=["Author B"],
        ),
        Metadata(
            name="package_with_mixedcase_repository",
            origin="https://github.com/org/package_mixedcase_repo",
            local_src_path=None,
            version="3.0.0",
            license=["BSD-3-Clause"],
            copyright=["Author C"],
        ),
        Metadata(
            name="package_with_uppercase_source_code",
            origin="https://github.com/org/package_uppercase_source",
            local_src_path=None,
            version="4.0.0",
            license=["GPL-3.0"],
            copyright=["Author D"],
        ),
    ]

    assert result == expected_metadata

    # Verify all mocks were called correctly
    source_code_manager_mock.get_code.assert_called_once_with(
        "https://github.com/org/package1"
    )
    python_env_manager_mock.get_environment.assert_called_once_with(
        "cache_dir/20220101_000000Z/org-package1/main"
    )
    get_dependencies_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/org_package1_virtualenv"
    )
    assert mock_request.call_count == 4
    mock_request.assert_has_calls(
        [
            mocker.call(
                "https://pypi.org/pypi/package_with_uppercase_homepage/1.0.0/json"
            ),
            mocker.call(
                "https://pypi.org/pypi/package_with_lowercase_github/2.0.0/json"
            ),
            mocker.call(
                "https://pypi.org/pypi/package_with_mixedcase_repository/3.0.0/json"
            ),
            mocker.call(
                "https://pypi.org/pypi/package_with_uppercase_source_code/4.0.0/json"
            ),
        ]
    )
