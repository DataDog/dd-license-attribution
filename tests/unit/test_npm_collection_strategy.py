# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import json
import logging
from typing import Any
from unittest import mock

import pytest_mock
from pytest import LogCaptureFixture

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.npm_collection_strategy import (
    NpmMetadataCollectionStrategy,
)


def create_source_code_manager_mock() -> mock.Mock:
    """Create a mock source code manager with standard return values."""
    source_code_manager_mock = mock.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = ("package1", None)
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    return source_code_manager_mock


def setup_npm_strategy_mocks(
    mocker: pytest_mock.MockFixture,
    package_lock: dict[str, Any],
    package_json: dict[str, Any],
    requests_responses: list[mock.Mock],
) -> tuple[mock.Mock, mock.Mock, mock.Mock, mock.Mock, mock.Mock]:
    """Setup common mocks for npm collection strategy tests."""

    def fake_exists(path: str) -> bool:
        # Return False for yarn.lock to ensure npm path is taken
        if "yarn.lock" in path:
            return False
        return True

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return json.dumps(package_lock)
        elif "package.json" in path:
            return json.dumps(package_json)
        raise FileNotFoundError

    def fake_path_join(*args: Any) -> str:
        result = "/".join(args)
        return result

    def fake_output_from_command(command: str) -> str:
        # Handle npm list commands
        if "npm list" in command:
            # Convert package_lock structure to npm list format
            npm_list_output: dict[str, Any] = {
                "version": "1.0.0",
                "name": "test-project",
                "dependencies": {},
            }

            # Extract dependencies from package_lock
            packages = package_lock.get("packages", {})
            for key, pkg_data in packages.items():
                if key.startswith("node_modules/") and isinstance(pkg_data, dict):
                    pkg_name = key.rsplit("node_modules/", 1)[-1]
                    if "version" in pkg_data and not pkg_data.get("dev", False):
                        npm_list_output["dependencies"][pkg_name] = {
                            "version": pkg_data["version"]
                        }

            return json.dumps(npm_list_output)

        # Handle npm install commands
        return "npm install completed successfully"

    # Mock all the required functions
    mock_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mock_path_join = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mock_open = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output_from_command,
    )
    mock_requests = mocker.patch("requests.get", side_effect=requests_responses)

    return (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    )


def test_npm_collection_strategy_no_package_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        return_value=False,
    )
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
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
    ]
    result = strategy.augment_metadata(initial_metadata)
    assert result == initial_metadata


def test_npm_collection_strategy_is_bypassed_if_only_root_project(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {}},
        }
    }
    requests_responses: list[mock.Mock] = []
    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ONLY_ROOT_PROJECT
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
    ]
    result = strategy.augment_metadata(initial_metadata)
    assert result == initial_metadata
    mock_output_from_command.assert_not_called()
    assert mock_exists.call_count == 1
    assert mock_path_join.call_count == 1
    assert mock_open.call_count == 1
    mock_requests.assert_not_called()


def test_npm_collection_strategy_adds_npm_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {"dep1": "^1.0.0", "dep2": "~2.0.0"}},
            "node_modules/dep1": {"version": "1.0.5", "dependencies": {}},
            "node_modules/dep2": {"version": "2.0.3", "dependencies": {}},
        }
    }

    requests_responses: list[mock.Mock] = [
        mock.Mock(status_code=200, json=lambda: {"license": "MIT", "author": "Alice"}),
        mock.Mock(
            status_code=200, json=lambda: {"license": "Apache-2.0", "author": "Bob"}
        ),
    ]

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
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
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="dep1",
            version="1.0.5",
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
        Metadata(
            name="dep2",
            version="2.0.3",
            origin="npm:dep2",
            local_src_path=None,
            license=["Apache-2.0"],
            copyright=["Bob"],
        ),
    ]
    assert result == expected_metadata
    # Verify npm install and npm list were called
    assert mock_output_from_command.call_count == 2
    mock_output_from_command.assert_any_call(
        "CWD=`pwd`; cd cache_dir/org_package1 && npm install --production; cd $CWD"
    )
    mock_output_from_command.assert_any_call(
        "cd cache_dir/org_package1 && npm list --json --production --all 2>/dev/null"
    )
    assert mock_exists.call_count == 2  # package.json, yarn.lock
    assert mock_path_join.call_count == 2  # package.json, yarn.lock
    assert mock_open.call_count == 1  # package.json
    assert mock_requests.call_count == 2


def test_npm_collection_strategy_extracts_transitive_dependencies(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {"dep1": "^1.0.0"}},
            "node_modules/dep1": {
                "version": "1.0.8",
                "dependencies": {"transitive1": ">=1.1.0", "transitive2": "~1.2.0"},
            },
            "node_modules/transitive1": {
                "version": "1.1.3",
                "dependencies": {"deep1": "^2.0.0"},
            },
            "node_modules/transitive2": {"version": "1.2.5", "dependencies": {}},
            "node_modules/deep1": {"version": "2.0.1", "dependencies": {}},
        }
    }

    requests_responses: list[mock.Mock] = [
        mock.Mock(status_code=200, json=lambda: {"license": "MIT", "author": "Alice"}),
        mock.Mock(
            status_code=200, json=lambda: {"license": "Apache-2.0", "author": "Bob"}
        ),
        mock.Mock(
            status_code=200,
            json=lambda: {"license": "BSD-3-Clause", "author": "Charlie"},
        ),
        mock.Mock(
            status_code=200, json=lambda: {"license": "GPL-3.0", "author": "David"}
        ),
    ]

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
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
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="dep1",
            version="1.0.8",
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
        Metadata(
            name="transitive1",
            version="1.1.3",
            origin="npm:transitive1",
            local_src_path=None,
            license=["Apache-2.0"],
            copyright=["Bob"],
        ),
        Metadata(
            name="transitive2",
            version="1.2.5",
            origin="npm:transitive2",
            local_src_path=None,
            license=["BSD-3-Clause"],
            copyright=["Charlie"],
        ),
        Metadata(
            name="deep1",
            version="2.0.1",
            origin="npm:deep1",
            local_src_path=None,
            license=["GPL-3.0"],
            copyright=["David"],
        ),
    ]
    assert result == expected_metadata
    # Verify npm install and npm list were called
    assert mock_output_from_command.call_count == 2
    mock_output_from_command.assert_any_call(
        "CWD=`pwd`; cd cache_dir/org_package1 && npm install --production; cd $CWD"
    )
    mock_output_from_command.assert_any_call(
        "cd cache_dir/org_package1 && npm list --json --production --all 2>/dev/null"
    )
    assert mock_exists.call_count == 2  # package.json, yarn.lock
    assert mock_path_join.call_count == 2  # package.json, yarn.lock
    assert mock_open.call_count == 1  # package.json
    assert mock_requests.call_count == 4


def test_npm_collection_strategy_avoids_duplicates_and_respects_only_transitive(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock = {
        "packages": {
            "": {"dependencies": {"dep1": "^1.0.0"}},
            "node_modules/dep1": {"version": "1.0.2", "dependencies": {}},
        }
    }

    requests_responses = [
        mock.Mock(status_code=200, json=lambda: {"license": "MIT", "author": "Alice"})
    ]

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="dep1",
            version="1.0.2",
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
    ]
    result = strategy.augment_metadata(initial_metadata)
    expected_metadata = [
        Metadata(
            name="dep1",
            version="1.0.2",
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
    ]
    assert result == expected_metadata
    # Verify npm install and npm list were called
    assert mock_output_from_command.call_count == 2
    mock_output_from_command.assert_any_call(
        "CWD=`pwd`; cd cache_dir/org_package1 && npm install --production; cd $CWD"
    )
    mock_output_from_command.assert_any_call(
        "cd cache_dir/org_package1 && npm list --json --production --all 2>/dev/null"
    )
    assert mock_exists.call_count == 2  # package.json, yarn.lock
    assert mock_path_join.call_count == 2  # package.json, yarn.lock
    assert mock_open.call_count == 1  # package.json
    assert mock_requests.call_count == 1


def test_npm_collection_strategy_handles_missing_packages_key(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock: dict[str, Any] = {
        "dependencies": {
            "dep1": {"version": "1.0.0", "resolved": "https://npmjs.com/dep1"},
        }
    }

    requests_responses: list[mock.Mock] = []

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]
    result = strategy.augment_metadata(initial_metadata)
    # Should return original metadata when packages key is missing (npm list returns no deps)
    # Verify npm install and npm list were called
    assert mock_output_from_command.call_count == 2
    mock_output_from_command.assert_any_call(
        "CWD=`pwd`; cd cache_dir/org_package1 && npm install --production; cd $CWD"
    )
    mock_output_from_command.assert_any_call(
        "cd cache_dir/org_package1 && npm list --json --production --all 2>/dev/null"
    )
    assert mock_exists.call_count == 2  # package.json, yarn.lock
    assert mock_path_join.call_count == 2  # package.json, yarn.lock
    assert mock_open.call_count == 1  # package.json
    mock_requests.assert_not_called()
    assert result == initial_metadata


def test_npm_collection_strategy_handles_missing_root_package(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock: dict[str, Any] = {
        "packages": {"node_modules/dep1": {"version": "1.0.0", "dependencies": {}}}
    }

    requests_responses: list[mock.Mock] = [
        mock.Mock(status_code=200, json=lambda: {"license": "MIT", "author": "Alice"}),
    ]

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]
    result = strategy.augment_metadata(initial_metadata)
    # Flat iteration discovers dep1 even without a root package key
    expected_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="dep1",
            version="1.0.0",
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
    ]
    assert result == expected_metadata
    # Verify npm install and npm list were called
    assert mock_output_from_command.call_count == 2
    mock_output_from_command.assert_any_call(
        "CWD=`pwd`; cd cache_dir/org_package1 && npm install --production; cd $CWD"
    )
    mock_output_from_command.assert_any_call(
        "cd cache_dir/org_package1 && npm list --json --production --all 2>/dev/null"
    )
    assert mock_exists.call_count == 2  # package.json, yarn.lock
    assert mock_path_join.call_count == 2  # package.json, yarn.lock
    assert mock_open.call_count == 1  # package.json
    assert mock_requests.call_count == 1


def test_npm_collection_strategy_handles_registry_api_failures(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock = {
        "packages": {
            "": {"dependencies": {"dep1": "1.0.0", "dep2": "2.0.0"}},
            "node_modules/dep1": {"version": "1.0.0", "dependencies": {}},
            "node_modules/dep2": {"version": "2.0.0", "dependencies": {}},
        }
    }

    requests_responses = [
        mock.Mock(status_code=404),  # dep1 not found
        mock.Mock(
            status_code=200, json=lambda: {"license": "Apache-2.0", "author": "Bob"}
        ),
    ]

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]
    result = strategy.augment_metadata(initial_metadata)

    assert len(result) == 3

    dep1_meta = next((m for m in result if m.name == "dep1"), None)
    dep2_meta = next((m for m in result if m.name == "dep2"), None)

    assert dep1_meta is not None
    assert dep2_meta is not None
    assert dep1_meta.license == []  # Should be empty due to 404
    assert dep2_meta.license == ["Apache-2.0"]  # Should have license
    # Verify npm install and npm list were called
    assert mock_output_from_command.call_count == 2
    mock_output_from_command.assert_any_call(
        "CWD=`pwd`; cd cache_dir/org_package1 && npm install --production; cd $CWD"
    )
    mock_output_from_command.assert_any_call(
        "cd cache_dir/org_package1 && npm list --json --production --all 2>/dev/null"
    )
    assert mock_exists.call_count == 2  # package.json, yarn.lock
    assert mock_path_join.call_count == 2  # package.json, yarn.lock
    assert mock_open.call_count == 1  # package.json
    assert mock_requests.call_count == 2


def test_npm_collection_strategy_logs_warning_on_non_200_response(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock = {
        "packages": {
            "": {"dependencies": {"dep1": "1.0.0"}},
            "node_modules/dep1": {"version": "1.0.0", "dependencies": {}},
        }
    }
    requests_responses = [mock.Mock(status_code=404, text="Not Found")]

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    with caplog.at_level(logging.WARNING):
        result = strategy.augment_metadata(initial_metadata)

    expected_warning = (
        "Failed to fetch npm registry metadata for dep1@1.0.0: 404, Not Found"
    )
    assert any(expected_warning in record.message for record in caplog.records)

    assert len(result) == 2
    dep_meta = next((m for m in result if m.name == "dep1"), None)
    assert dep_meta is not None
    assert dep_meta.version == "1.0.0"
    assert dep_meta.license == []
    assert dep_meta.copyright == []
    # Verify npm install and npm list were called
    assert mock_output_from_command.call_count == 2
    mock_output_from_command.assert_any_call(
        "CWD=`pwd`; cd cache_dir/org_package1 && npm install --production; cd $CWD"
    )
    mock_output_from_command.assert_any_call(
        "cd cache_dir/org_package1 && npm list --json --production --all 2>/dev/null"
    )
    assert mock_exists.call_count == 2  # package.json, yarn.lock
    assert mock_path_join.call_count == 2  # package.json, yarn.lock
    assert mock_open.call_count == 1  # package.json
    assert mock_requests.call_count == 1


def test_npm_collection_strategy_handles_npm_install_failure(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {"name": "test-project", "version": "1.0.0"}
    package_lock: dict[str, Any] = {}
    requests_responses: list[mock.Mock] = []

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    # Override output_from_command to raise an exception
    mock_output_from_command.side_effect = Exception("npm not found")

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    with caplog.at_level(logging.WARNING):
        result = strategy.augment_metadata(initial_metadata)

    expected_warning = "Failed to run npm install/list for package1: npm not found"
    assert any(expected_warning in record.message for record in caplog.records)

    assert result == initial_metadata
    # Verify npm install was attempted (npm list wouldn't run if install fails)
    mock_output_from_command.assert_called_once_with(
        "CWD=`pwd`; cd cache_dir/org_package1 && npm install --production; cd $CWD"
    )
    assert mock_exists.call_count == 2  # package.json, yarn.lock
    assert mock_path_join.call_count == 2  # package.json, yarn.lock
    mock_open.assert_called_once()  # Only package.json
    mock_requests.assert_not_called()


def test_npm_collection_strategy_no_package_json(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that strategy returns original metadata when package.json is not found."""
    source_code_manager_mock = create_source_code_manager_mock()
    package_lock: dict[str, Any] = {}
    package_json: dict[str, Any] = {}
    requests_responses: list[mock.Mock] = []

    def fake_exists(path: str) -> bool:
        return False

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    mock_exists.side_effect = fake_exists

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
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
    ]
    result = strategy.augment_metadata(initial_metadata)
    assert result == initial_metadata

    # Verify path_exists was called with package.json path
    mock_path_join.assert_called_once_with("cache_dir/org_package1", "package.json")
    mock_exists.assert_called_once()
    mock_output_from_command.assert_not_called()
    mock_open.assert_not_called()
    mock_requests.assert_not_called()


def test_npm_collection_strategy_handles_workspaces(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Test strategy handles workspaces with warning and unchanged metadata."""
    source_code_manager_mock = create_source_code_manager_mock()

    package_json: dict[str, Any] = {
        "name": "test-workspace-project",
        "version": "1.0.0",
        "workspaces": ["packages/*", "apps/*"],
    }

    package_lock: dict[str, Any] = {}
    requests_responses: list[mock.Mock] = []

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    with caplog.at_level(logging.WARNING):
        result = strategy.augment_metadata(initial_metadata)

    # Verify warning is logged
    expected_warning = "Node projects using workspaces are not supported yet by the NPM collection strategy."
    assert any(expected_warning in record.message for record in caplog.records)

    # Verify original metadata is returned unchanged
    assert result == initial_metadata

    # Verify early return - npm install should not be called
    mock_exists.assert_called_once()
    mock_path_join.assert_called_once_with("cache_dir/org_package1", "package.json")
    mock_open.assert_called_once()
    mock_output_from_command.assert_not_called()
    mock_requests.assert_not_called()


def test_npm_handles_complex_semver_ranges(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that complex semver ranges in dependencies are ignored and resolved versions are used."""
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock: dict[str, Any] = {
        "packages": {
            "": {
                "dependencies": {
                    "dep1": ">=1.0.0 <2.0.0",  # Complex range
                    "dep2": "<1.5.0",  # Less than
                    "dep3": "1.0.0 - 2.0.0",  # Hyphen range
                }
            },
            "node_modules/dep1": {"version": "1.5.3", "dependencies": {}},
            "node_modules/dep2": {"version": "1.4.2", "dependencies": {}},
            "node_modules/dep3": {"version": "1.8.0", "dependencies": {}},
        }
    }

    requests_responses: list[mock.Mock] = [
        mock.Mock(status_code=200, json=lambda: {"license": "MIT", "author": "Alice"}),
        mock.Mock(
            status_code=200, json=lambda: {"license": "Apache-2.0", "author": "Bob"}
        ),
        mock.Mock(status_code=200, json=lambda: {"license": "ISC", "author": "Carol"}),
    ]

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]
    result = strategy.augment_metadata(initial_metadata)

    # Verify that resolved versions from the version field are used, not the complex ranges
    expected_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="dep1",
            version="1.5.3",  # Resolved version, not the range
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
        Metadata(
            name="dep2",
            version="1.4.2",  # Resolved version, not the range
            origin="npm:dep2",
            local_src_path=None,
            license=["Apache-2.0"],
            copyright=["Bob"],
        ),
        Metadata(
            name="dep3",
            version="1.8.0",  # Resolved version, not the range
            origin="npm:dep3",
            local_src_path=None,
            license=["ISC"],
            copyright=["Carol"],
        ),
    ]
    assert result == expected_metadata
    assert mock_requests.call_count == 3


def test_npm_handles_missing_node_modules_entry(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that packages without node_modules entries are silently skipped."""
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock: dict[str, Any] = {
        "packages": {
            "": {
                "dependencies": {
                    "dep1": "^1.0.0",
                    "dep2": "^2.0.0",  # This one is missing from node_modules
                    "dep3": "^3.0.0",
                }
            },
            "node_modules/dep1": {"version": "1.0.5", "dependencies": {}},
            # dep2 is intentionally missing
            "node_modules/dep3": {
                "version": "3.1.0",
                "dependencies": {
                    "transitive1": "^1.0.0"  # This transitive is also missing
                },
            },
        }
    }

    requests_responses: list[mock.Mock] = [
        mock.Mock(status_code=200, json=lambda: {"license": "MIT", "author": "Alice"}),
        mock.Mock(status_code=200, json=lambda: {"license": "ISC", "author": "Carol"}),
    ]

    (
        mock_exists,
        mock_path_join,
        mock_open,
        mock_output_from_command,
        mock_requests,
    ) = setup_npm_strategy_mocks(mocker, package_lock, package_json, requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Verify that only dependencies with node_modules entries are added
    expected_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="dep1",
            version="1.0.5",
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
        Metadata(
            name="dep3",
            version="3.1.0",
            origin="npm:dep3",
            local_src_path=None,
            license=["ISC"],
            copyright=["Carol"],
        ),
    ]
    assert result == expected_metadata

    # Only 2 requests should be made (for dep1 and dep3)
    # dep2 and transitive1 are silently skipped since they have no node_modules entries
    assert mock_requests.call_count == 2


def test_extract_copyright_from_pkg_data() -> None:
    """Test _extract_copyright_from_pkg_data with various author formats."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    test_cases = {
        # Author as string
        '{"author": "John Doe"}': ["John Doe"],
        '{"author": "Jane Smith <jane@example.com>"}': [
            "Jane Smith <jane@example.com>"
        ],
        # Author as dict with name
        '{"author": {"name": "Alice Cooper"}}': ["Alice Cooper"],
        '{"author": {"name": "Bob Wilson", "email": "bob@example.com"}}': [
            "Bob Wilson"
        ],
        # Missing author key
        "{}": [],
        '{"license": "MIT"}': [],
        # Author is None or empty
        '{"author": null}': [],
        '{"author": ""}': [],
        # Author as dict without name
        '{"author": {"email": "test@example.com"}}': [],
        '{"author": {"url": "https://example.com"}}': [],
        # Author as other types
        '{"author": []}': [],
        '{"author": 123}': [],
        '{"author": true}': [],
    }

    for test_input, expected_output in test_cases.items():
        pkg_data = json.loads(test_input)
        result = strategy._extract_copyright_from_pkg_data(pkg_data)
        assert (
            result == expected_output
        ), f"Failed for '{test_input}': expected '{expected_output}', got '{result}'"


# ============================================================================
# Tests for Yarn support
# ============================================================================


def test_detect_package_manager_with_yarn_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _detect_package_manager returns 'yarn' when yarn.lock exists."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    def fake_exists(path: str) -> bool:
        return "yarn.lock" in path

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )

    result = strategy._detect_package_manager("/project/path")
    assert result == "yarn"


def test_detect_package_manager_without_yarn_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _detect_package_manager returns 'npm' when yarn.lock doesn't exist."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    def fake_exists(path: str) -> bool:
        return False

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )

    result = strategy._detect_package_manager("/project/path")
    assert result == "npm"


def test_extract_yarn_aliases_from_tree_with_aliases() -> None:
    """Test _extract_yarn_aliases_from_tree extracts aliases correctly."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    trees: list[dict[str, Any]] = [
        {
            "name": "dep1@1.0.0",
            "children": [
                {"name": "string-width-cjs@npm:string-width@^4.2.0"},
                {"name": "ansi-regex@^5.0.1"},
            ],
        },
        {
            "name": "dep2@2.0.0",
            "children": [
                {"name": "wrap-ansi-cjs@npm:wrap-ansi@^7.0.0"},
                {
                    "name": "nested@1.0.0",
                    "children": [
                        {"name": "strip-ansi-cjs@npm:strip-ansi@^6.0.1"},
                    ],
                },
            ],
        },
    ]

    result = strategy._extract_yarn_aliases_from_tree(trees)
    expected = {
        "string-width-cjs": "string-width",
        "wrap-ansi-cjs": "wrap-ansi",
        "strip-ansi-cjs": "strip-ansi",
    }
    assert result == expected


def test_extract_yarn_aliases_from_tree_no_aliases() -> None:
    """Test _extract_yarn_aliases_from_tree with no aliases."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    trees = [
        {
            "name": "dep1@1.0.0",
            "children": [
                {"name": "ansi-regex@^5.0.1"},
                {"name": "another-dep@^2.0.0"},
            ],
        },
    ]

    result = strategy._extract_yarn_aliases_from_tree(trees)
    assert result == {}


def test_extract_yarn_aliases_from_tree_empty_trees() -> None:
    """Test _extract_yarn_aliases_from_tree with empty trees."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    result = strategy._extract_yarn_aliases_from_tree([])
    assert result == {}


def test_extract_yarn_aliases_from_tree_malformed_children() -> None:
    """Test _extract_yarn_aliases_from_tree handles malformed children."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    trees = [
        {
            "name": "dep1@1.0.0",
            "children": [
                {"name": ""},  # Empty name
                "not-a-dict",  # Not a dict
                {"no-name-key": "value"},  # Missing name key
            ],
        },
    ]

    result = strategy._extract_yarn_aliases_from_tree(trees)
    assert result == {}


def test_get_yarn_dependencies_success(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _get_yarn_dependencies successfully extracts dependencies."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    # Yarn output has multiple JSON objects on separate lines
    yarn_output = """{"type":"tree","data":{"type":"list","trees":[{"name":"lodash@4.17.21","children":[]},{"name":"react@18.2.0","children":[{"name":"loose-envify@1.4.0"}]},{"name":"loose-envify@1.4.0","children":[]}]}}"""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=lambda *args: "/".join(args),
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        return_value="",  # Empty yarn.lock, no aliases
    )
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        return_value=yarn_output,
    )

    result = strategy._get_yarn_dependencies("/project/path")
    expected = {
        "lodash": "4.17.21",
        "react": "18.2.0",
        "loose-envify": "1.4.0",
    }
    assert result == expected

    # Verify that the command includes --production flag to exclude dev dependencies
    mock_output_from_command.assert_called_once()
    called_command = mock_output_from_command.call_args[0][0]
    assert "--production" in called_command
    assert "yarn list" in called_command


def test_get_yarn_dependencies_with_scoped_packages(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _get_yarn_dependencies handles scoped packages."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    yarn_output = """{"type":"tree","data":{"type":"list","trees":[{"name":"@datadog/browser-core@5.0.0","children":[]},{"name":"@babel/runtime@7.22.0","children":[]}]}}"""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=lambda *args: "/".join(args),
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        return_value="",  # Empty yarn.lock, no aliases
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        return_value=yarn_output,
    )

    result = strategy._get_yarn_dependencies("/project/path")
    expected = {
        "@datadog/browser-core": "5.0.0",
        "@babel/runtime": "7.22.0",
    }
    assert result == expected


def test_get_yarn_dependencies_with_aliases(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _get_yarn_dependencies resolves aliases correctly."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    yarn_output = """{"type":"tree","data":{"type":"list","trees":[{"name":"string-width@4.2.3","children":[]},{"name":"string-width-cjs@4.2.3","children":[{"name":"string-width-cjs@npm:string-width@^4.2.0"}]}]}}"""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=lambda *args: "/".join(args),
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        return_value="",  # Empty yarn.lock, no aliases from lock file (aliases are in tree)
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        return_value=yarn_output,
    )

    result = strategy._get_yarn_dependencies("/project/path")
    # The alias should be resolved to the real package name
    assert "string-width" in result
    assert result["string-width"] == "4.2.3"


def test_get_yarn_dependencies_empty_output(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Test _get_yarn_dependencies handles empty output."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=lambda *args: "/".join(args),
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        return_value="",  # Empty yarn.lock, no aliases
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        return_value="",
    )

    with caplog.at_level(logging.ERROR):
        result = strategy._get_yarn_dependencies("/project/path")

    assert result == {}
    assert any(
        "Yarn list produced no output" in record.message for record in caplog.records
    )


def test_get_yarn_dependencies_invalid_json(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Test _get_yarn_dependencies handles invalid JSON output."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=lambda *args: "/".join(args),
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        return_value="",  # Empty yarn.lock, no aliases
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        return_value="not valid json\nanother line\n",
    )

    with caplog.at_level(logging.ERROR):
        result = strategy._get_yarn_dependencies("/project/path")

    assert result == {}
    assert any(
        "did not produce valid JSON output" in record.message
        for record in caplog.records
    )


def test_get_yarn_dependencies_command_failure(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Test _get_yarn_dependencies handles command failure."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=lambda *args: "/".join(args),
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        return_value="",  # Empty yarn.lock, no aliases
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=Exception("Yarn command failed"),
    )

    with caplog.at_level(logging.WARNING):
        result = strategy._get_yarn_dependencies("/project/path")

    assert result == {}
    assert any("Failed to run yarn list" in record.message for record in caplog.records)


def test_npm_collection_strategy_with_yarn_project(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test npm collection strategy handles Yarn projects."""
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {"name": "test-package", "version": "1.0.0"}

    yarn_output = """{"type":"tree","data":{"type":"list","trees":[{"name":"lodash@4.17.21","children":[]},{"name":"react@18.2.0","children":[]}]}}"""

    requests_responses: list[mock.Mock] = [
        mock.Mock(status_code=200, json=lambda: {"license": "MIT", "author": "John"}),
        mock.Mock(status_code=200, json=lambda: {"license": "MIT", "author": "Meta"}),
    ]

    def fake_exists(path: str) -> bool:
        return True

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package.json" in path:
            return json.dumps(package_json)
        if "yarn.lock" in path:
            return ""  # Empty yarn.lock, no aliases
        raise FileNotFoundError

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_output_from_command(command: str) -> str:
        if "yarn --version" in command:
            return "1.22.19"
        elif "yarn list" in command:
            return yarn_output
        return ""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output_from_command,
    )
    mocker.patch("requests.get", side_effect=requests_responses)

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]
    result = strategy.augment_metadata(initial_metadata)

    # Should have root package + 2 dependencies
    assert len(result) == 3

    # Check root package metadata was enriched from package.json
    assert result[0].name == "test-package"  # Enriched from package.json
    assert result[0].version == "1.0.0"  # Enriched from package.json
    assert result[0].origin == "https://github.com/org/package1"

    # Check dependencies were added
    dep_names = {m.name for m in result[1:]}
    assert "lodash" in dep_names
    assert "react" in dep_names

    # Verify that the yarn list command includes --production flag
    yarn_list_calls = [
        call
        for call in mock_output_from_command.call_args_list
        if "yarn list" in str(call)
    ]
    assert len(yarn_list_calls) > 0
    yarn_command = str(yarn_list_calls[0])
    assert "--production" in yarn_command

    # Verify yarn list was called, not npm install
    yarn_list_called = any(
        "yarn list" in str(call) for call in mock_output_from_command.call_args_list
    )
    assert yarn_list_called


def test_npm_collection_strategy_yarn_not_installed(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Test npm collection strategy handles yarn not being installed."""
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {"name": "test-package", "version": "1.0.0"}

    def fake_exists(path: str) -> bool:
        return True

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package.json" in path:
            return json.dumps(package_json)
        raise FileNotFoundError

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_output_from_command(command: str) -> str:
        if "yarn --version" in command:
            raise Exception("yarn: command not found")
        return ""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output_from_command,
    )

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )
    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    with caplog.at_level(logging.ERROR):
        result = strategy.augment_metadata(initial_metadata)

    # Should return metadata with root enriched from package.json (no dependencies)
    assert len(result) == 1
    assert result[0].name == "test-package"  # Enriched from package.json
    assert result[0].version == "1.0.0"  # Enriched from package.json
    assert any("Yarn is not installed" in record.message for record in caplog.records)


# ============================================================================
# Tests for multi-location yarn.lock support
# ============================================================================


def test_collect_yarn_deps_from_location_with_existing_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _collect_yarn_deps_from_location finds and processes yarn.lock."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    yarn_output = """
{"type":"tree","data":{"trees":[{"name":"lodash@4.17.21"},{"name":"react@17.0.0"}]}}
"""

    def fake_exists(path: str) -> bool:
        return "yarn.lock" in path

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_output(cmd: str) -> str:
        if "yarn list" in cmd:
            return yarn_output
        return "1.22.0"

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        return_value="",  # Empty yarn.lock, no aliases
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )

    result = strategy._collect_yarn_deps_from_location("/test/path", "test-location")

    assert len(result) == 2
    assert result["lodash"] == "4.17.21"
    assert result["react"] == "17.0.0"


def test_collect_yarn_deps_from_location_without_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _collect_yarn_deps_from_location returns empty dict when no yarn.lock."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    def fake_exists(path: str) -> bool:
        return False

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )

    result = strategy._collect_yarn_deps_from_location("/test/path", "test-location")

    assert len(result) == 0


def test_augment_metadata_with_single_subdirectory(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test augment_metadata collects from root and single subdirectory."""
    source_code_manager_mock = create_source_code_manager_mock()

    package_json = {
        "name": "test-package",
        "version": "1.0.0",
        "license": "MIT",
    }

    # Root has lodash and react
    root_yarn_output = """
{"type":"tree","data":{"trees":[{"name":"lodash@4.17.21"},{"name":"react@17.0.0"}]}}
"""

    # Subdir has axios and react (same version)
    subdir_yarn_output = """
{"type":"tree","data":{"trees":[{"name":"axios@1.0.0"},{"name":"react@17.0.0"}]}}
"""

    def fake_exists(path: str) -> bool:
        if "package.json" in path:
            return True
        if "yarn.lock" in path:
            return True
        if "cache_dir/org_package1/subdir" in path:
            return True
        return False

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package.json" in path:
            return json.dumps(package_json)
        return ""

    def fake_output(cmd: str) -> str:
        if "yarn --version" in cmd:
            return "1.22.0"
        if "yarn list" in cmd:
            if "/subdir" in cmd:
                return subdir_yarn_output
            return root_yarn_output
        return ""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )

    # Mock requests for npm registry
    mock_get = mocker.patch("requests.get")
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"license": "MIT"}
    mock_get.return_value = mock_response

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL, yarn_subdirs=["subdir"]
    )

    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Should have root package + lodash + react + axios (react deduplicated)
    assert len(result) == 4
    names = {m.name for m in result}
    assert "lodash" in names
    assert "react" in names
    assert "axios" in names


def test_augment_metadata_with_multiple_subdirectories(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test augment_metadata collects from root and multiple subdirectories."""
    source_code_manager_mock = create_source_code_manager_mock()

    package_json = {
        "name": "test-package",
        "version": "1.0.0",
        "license": "MIT",
    }

    root_yarn_output = """
{"type":"tree","data":{"trees":[{"name":"lodash@4.17.21"}]}}
"""

    subdir1_yarn_output = """
{"type":"tree","data":{"trees":[{"name":"react@17.0.0"}]}}
"""

    subdir2_yarn_output = """
{"type":"tree","data":{"trees":[{"name":"axios@1.0.0"}]}}
"""

    def fake_exists(path: str) -> bool:
        if "package.json" in path:
            return True
        if "yarn.lock" in path:
            return True
        if any(sub in path for sub in ["subdir1", "subdir2"]):
            return True
        return False

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package.json" in path:
            return json.dumps(package_json)
        return ""

    def fake_output(cmd: str) -> str:
        if "yarn --version" in cmd:
            return "1.22.0"
        if "yarn list" in cmd:
            if "/subdir1" in cmd:
                return subdir1_yarn_output
            elif "/subdir2" in cmd:
                return subdir2_yarn_output
            return root_yarn_output
        return ""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )

    # Mock requests for npm registry
    mock_get = mocker.patch("requests.get")
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"license": "MIT"}
    mock_get.return_value = mock_response

    strategy = NpmMetadataCollectionStrategy(
        "package1",
        source_code_manager_mock,
        ProjectScope.ALL,
        yarn_subdirs=["subdir1", "subdir2"],
    )

    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Should have root package + lodash + react + axios
    assert len(result) == 4
    names = {m.name for m in result}
    assert "lodash" in names
    assert "react" in names
    assert "axios" in names


def test_augment_metadata_with_missing_subdirectory(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Test augment_metadata handles missing subdirectory gracefully."""
    source_code_manager_mock = create_source_code_manager_mock()

    package_json = {
        "name": "test-package",
        "version": "1.0.0",
        "license": "MIT",
    }

    root_yarn_output = """
{"type":"tree","data":{"trees":[{"name":"lodash@4.17.21"}]}}
"""

    def fake_exists(path: str) -> bool:
        if "package.json" in path:
            return True
        if "yarn.lock" in path and "missing-subdir" not in path:
            return True
        if "missing-subdir" in path:
            return False
        return False

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package.json" in path:
            return json.dumps(package_json)
        return ""

    def fake_output(cmd: str) -> str:
        if "yarn --version" in cmd:
            return "1.22.0"
        if "yarn list" in cmd:
            return root_yarn_output
        return ""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )

    # Mock requests for npm registry
    mock_get = mocker.patch("requests.get")
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"license": "MIT"}
    mock_get.return_value = mock_response

    strategy = NpmMetadataCollectionStrategy(
        "package1",
        source_code_manager_mock,
        ProjectScope.ALL,
        yarn_subdirs=["missing-subdir"],
    )

    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    with caplog.at_level(logging.WARNING):
        result = strategy.augment_metadata(initial_metadata)

    # Should have root package + lodash (missing subdir skipped)
    assert len(result) == 2
    assert any("missing-subdir" in record.message for record in caplog.records)
    assert any("does not exist" in record.message for record in caplog.records)


def test_augment_metadata_with_version_conflicts(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Test augment_metadata handles multiple versions of same package."""
    source_code_manager_mock = create_source_code_manager_mock()

    package_json = {
        "name": "test-package",
        "version": "1.0.0",
        "license": "MIT",
    }

    # Root has react@17.0.0
    root_yarn_output = """
{"type":"tree","data":{"trees":[{"name":"react@17.0.0"}]}}
"""

    # Subdir has react@18.0.0
    subdir_yarn_output = """
{"type":"tree","data":{"trees":[{"name":"react@18.0.0"}]}}
"""

    def fake_exists(path: str) -> bool:
        if "package.json" in path:
            return True
        if "yarn.lock" in path:
            return True
        if "subdir" in path:
            return True
        return False

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package.json" in path:
            return json.dumps(package_json)
        return ""

    def fake_output(cmd: str) -> str:
        if "yarn --version" in cmd:
            return "1.22.0"
        if "yarn list" in cmd:
            if "/subdir" in cmd:
                return subdir_yarn_output
            return root_yarn_output
        return ""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )

    # Mock requests for npm registry
    mock_get = mocker.patch("requests.get")
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"license": "MIT"}
    mock_get.return_value = mock_response

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL, yarn_subdirs=["subdir"]
    )

    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    with caplog.at_level(logging.INFO):
        result = strategy.augment_metadata(initial_metadata)

    # Should have root package + react@17.0.0 + react@18.0.0
    assert len(result) == 3
    react_entries = [m for m in result if m.name == "react"]
    assert len(react_entries) == 2
    versions = {m.version for m in react_entries}
    assert "17.0.0" in versions
    assert "18.0.0" in versions

    # Should log that react has multiple versions
    assert any(
        "react" in record.message and "multiple versions" in record.message
        for record in caplog.records
    )


# ============================================================================
# Tests for Yarn alias support from yarn.lock
# ============================================================================


def test_extract_aliases_from_yarn_lock_with_aliases(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _extract_aliases_from_yarn_lock extracts various alias formats."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    # Mock yarn.lock content with various alias formats
    yarn_lock_content = """
# Yarn lockfile v1

"@datadog/source-map@npm:source-map@^0.6.0":
  version "0.6.1"
  resolved "https://registry.yarnpkg.com/source-map/-/source-map-0.6.1.tgz"
  integrity sha512-UjgapumWlbMhkBgzT7Ykc5YXUT46F0iKu8SGXq0bcwP5dz/h0Plj6enJqjz1Zbq2l5WaqYnrVbwWOWMyF3F47g==

"@company/lib@npm:@other/real-lib@^1.0.0":
  version "1.2.3"
  resolved "https://registry.yarnpkg.com/@other/real-lib/-/real-lib-1.2.3.tgz"

"alias@npm:real-package@^2.0.0":
  version "2.1.0"
  resolved "https://registry.yarnpkg.com/real-package/-/real-package-2.1.0.tgz"

"regular-package@^1.0.0":
  version "1.0.5"
  resolved "https://registry.yarnpkg.com/regular-package/-/regular-package-1.0.5.tgz"
"""

    def fake_exists(path: str) -> bool:
        return "yarn.lock" in path

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "yarn.lock" in path:
            return yarn_lock_content
        raise FileNotFoundError

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )

    result = strategy._extract_aliases_from_yarn_lock("/test/path")

    assert len(result) == 3
    assert result["@datadog/source-map"] == "source-map"
    assert result["@company/lib"] == "@other/real-lib"
    assert result["alias"] == "real-package"
    # Regular packages should not be in aliases
    assert "regular-package" not in result


def test_extract_aliases_from_yarn_lock_no_aliases(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _extract_aliases_from_yarn_lock with no aliases returns empty dict."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    yarn_lock_content = """
# Yarn lockfile v1

"lodash@^4.17.0":
  version "4.17.21"
  resolved "https://registry.yarnpkg.com/lodash/-/lodash-4.17.21.tgz"

"react@^18.0.0":
  version "18.2.0"
  resolved "https://registry.yarnpkg.com/react/-/react-18.2.0.tgz"
"""

    def fake_exists(path: str) -> bool:
        return "yarn.lock" in path

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "yarn.lock" in path:
            return yarn_lock_content
        raise FileNotFoundError

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )

    result = strategy._extract_aliases_from_yarn_lock("/test/path")

    assert len(result) == 0


def test_get_yarn_dependencies_resolves_aliases_from_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that _get_yarn_dependencies resolves aliases from yarn.lock."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    yarn_lock_content = """
"@datadog/source-map@npm:source-map@^0.6.0":
  version "0.6.1"
  resolved "https://registry.yarnpkg.com/source-map/-/source-map-0.6.1.tgz"
"""

    # Yarn list output shows the alias name
    yarn_output = """{"type":"tree","data":{"trees":[{"name":"@datadog/source-map@0.6.1","children":[]}]}}"""

    def fake_exists(path: str) -> bool:
        return True

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "yarn.lock" in path:
            return yarn_lock_content
        raise FileNotFoundError

    def fake_output(cmd: str) -> str:
        if "yarn list" in cmd:
            return yarn_output
        return "1.22.0"

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )

    result = strategy._get_yarn_dependencies("/test/path")

    # Should resolve @datadog/source-map to source-map
    assert "source-map" in result
    assert result["source-map"] == "0.6.1"
    # Alias name should not be in result
    assert "@datadog/source-map" not in result


def test_augment_metadata_with_yarn_aliases_from_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test end-to-end yarn alias resolution."""
    source_code_manager_mock = create_source_code_manager_mock()

    package_json = {"name": "test-package", "version": "1.0.0"}

    yarn_lock_content = """
"@datadog/source-map@npm:source-map@^0.6.0":
  version "0.6.1"
  resolved "https://registry.yarnpkg.com/source-map/-/source-map-0.6.1.tgz"
"""

    yarn_output = """{"type":"tree","data":{"trees":[{"name":"@datadog/source-map@0.6.1","children":[]}]}}"""

    def fake_exists(path: str) -> bool:
        return True

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "yarn.lock" in path:
            return yarn_lock_content
        elif "package.json" in path:
            return json.dumps(package_json)
        raise FileNotFoundError

    def fake_output(cmd: str) -> str:
        if "yarn --version" in cmd:
            return "1.22.0"
        elif "yarn list" in cmd:
            return yarn_output
        return ""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )

    # Mock npm registry response for the REAL package name
    mock_get = mocker.patch("requests.get")
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"license": "BSD-3-Clause", "author": "Mozilla"}
    mock_get.return_value = mock_response

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Should have metadata for real package name, not alias
    assert len(result) == 2
    dep_meta = next((m for m in result if m.name == "source-map"), None)
    assert dep_meta is not None
    assert dep_meta.version == "0.6.1"
    assert dep_meta.license == ["BSD-3-Clause"]

    # Verify npm registry was called with REAL package name, not alias
    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert "source-map/0.6.1" in call_url
    assert "@datadog" not in call_url


def test_yarn_lock_aliases_precedence_over_tree_aliases(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that yarn.lock aliases take precedence over tree-extracted aliases."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    # yarn.lock says alias1 -> real-package-a
    yarn_lock_content = """
"alias1@npm:real-package-a@^1.0.0":
  version "1.0.0"
  resolved "https://registry.yarnpkg.com/real-package-a/-/real-package-a-1.0.0.tgz"
"""

    # yarn list tree says alias1 -> real-package-b (different)
    yarn_output = """{"type":"tree","data":{"trees":[{"name":"alias1@1.0.0","children":[{"name":"alias1@npm:real-package-b@^1.0.0"}]}]}}"""

    def fake_exists(path: str) -> bool:
        return True

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "yarn.lock" in path:
            return yarn_lock_content
        raise FileNotFoundError

    def fake_output(cmd: str) -> str:
        if "yarn list" in cmd:
            return yarn_output
        return "1.22.0"

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )

    result = strategy._get_yarn_dependencies("/test/path")

    # yarn.lock should take precedence, so alias1 -> real-package-a
    assert "real-package-a" in result
    assert "real-package-b" not in result
    assert "alias1" not in result


# ============================================================================
# Tests for npm alias support from package-lock.json
# ============================================================================


def test_extract_aliases_from_package_lock_with_aliases(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _extract_aliases_from_package_lock extracts various alias formats."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    package_lock = {
        "packages": {
            "": {
                "dependencies": {
                    "@datadog/source-map": "npm:source-map@^0.6.0",
                    "@company/lib": "npm:@other/real-lib@^1.0.0",
                    "alias": "npm:real-package@^2.0.0",
                    "regular-dep": "^1.0.0",
                }
            },
            "node_modules/@datadog/source-map": {
                "version": "0.6.1",
                "resolved": "https://registry.npmjs.org/source-map/-/source-map-0.6.1.tgz",
                "name": "source-map",
            },
            "node_modules/@company/lib": {
                "version": "1.2.3",
                "resolved": "https://registry.npmjs.org/@other/real-lib/-/real-lib-1.2.3.tgz",
                "name": "@other/real-lib",
            },
            "node_modules/alias": {
                "version": "2.1.0",
                "resolved": "https://registry.npmjs.org/real-package/-/real-package-2.1.0.tgz",
                "name": "real-package",
            },
            "node_modules/regular-dep": {
                "version": "1.0.5",
            },
        }
    }

    def fake_exists(path: str) -> bool:
        return "package-lock.json" in path

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package-lock.json" in path:
            return json.dumps(package_lock)
        raise FileNotFoundError

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )

    result = strategy._extract_aliases_from_package_lock("/test/path")

    # Should extract aliases from both root dependencies and node_modules entries
    assert len(result) >= 3
    assert result["@datadog/source-map"] == "source-map"
    assert result["@company/lib"] == "@other/real-lib"
    assert result["alias"] == "real-package"
    # Regular dependencies should not be in aliases
    assert "regular-dep" not in result or result.get("regular-dep") == "regular-dep"


def test_extract_aliases_from_package_lock_no_aliases(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test _extract_aliases_from_package_lock with no aliases returns empty dict."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    package_lock = {
        "packages": {
            "": {
                "dependencies": {
                    "lodash": "^4.17.0",
                    "react": "^18.0.0",
                }
            },
            "node_modules/lodash": {
                "version": "4.17.21",
            },
            "node_modules/react": {
                "version": "18.2.0",
            },
        }
    }

    def fake_exists(path: str) -> bool:
        return "package-lock.json" in path

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package-lock.json" in path:
            return json.dumps(package_lock)
        raise FileNotFoundError

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )

    result = strategy._extract_aliases_from_package_lock("/test/path")

    assert len(result) == 0


def test_get_npm_dependencies_resolves_aliases_from_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that _get_npm_dependencies resolves aliases from package-lock.json."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    package_lock = {
        "packages": {
            "": {
                "dependencies": {
                    "@datadog/source-map": "npm:source-map@^0.6.0",
                }
            },
            "node_modules/@datadog/source-map": {
                "version": "0.6.1",
                "name": "source-map",
            },
        }
    }

    def fake_exists(path: str) -> bool:
        return "package-lock.json" in path

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package-lock.json" in path:
            return json.dumps(package_lock)
        raise FileNotFoundError

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )

    result = strategy._get_npm_dependencies(package_lock, "/test/path")

    # Should resolve @datadog/source-map to source-map
    assert "source-map" in result
    assert result["source-map"] == "0.6.1"
    # Alias name should not be in result
    assert "@datadog/source-map" not in result


def test_augment_metadata_with_npm_aliases_from_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test end-to-end npm alias resolution."""
    source_code_manager_mock = create_source_code_manager_mock()

    package_json: dict[str, Any] = {"name": "test-package", "version": "1.0.0"}

    package_lock: dict[str, Any] = {
        "packages": {
            "": {
                "dependencies": {
                    "@datadog/source-map": "npm:source-map@^0.6.0",
                }
            },
            "node_modules/@datadog/source-map": {
                "version": "0.6.1",
                "name": "source-map",
            },
        }
    }

    def fake_exists(path: str) -> bool:
        if "yarn.lock" in path:
            return False
        return True

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package-lock.json" in path:
            return json.dumps(package_lock)
        elif "package.json" in path:
            return json.dumps(package_json)
        raise FileNotFoundError

    def fake_output(cmd: str) -> str:
        # Handle npm list commands
        if "npm list" in cmd:
            # Return npm list output with the aliased package resolved to real name
            npm_list_output = {
                "version": "1.0.0",
                "name": "test-package",
                "dependencies": {
                    "source-map": {"version": "0.6.1"}  # Real package name, not alias
                },
            }
            return json.dumps(npm_list_output)
        return "npm install completed"

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )

    # Mock npm registry response for the REAL package name
    mock_get = mocker.patch("requests.get")
    mock_response = mock.Mock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"license": "BSD-3-Clause", "author": "Mozilla"}
    mock_get.return_value = mock_response

    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    initial_metadata = [
        Metadata(
            name="package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Should have metadata for real package name, not alias
    assert len(result) == 2
    dep_meta = next((m for m in result if m.name == "source-map"), None)
    assert dep_meta is not None
    assert dep_meta.version == "0.6.1"
    assert dep_meta.license == ["BSD-3-Clause"]

    # Verify npm registry was called with REAL package name, not alias
    mock_get.assert_called_once()
    call_url = mock_get.call_args[0][0]
    assert "source-map/0.6.1" in call_url
    assert "@datadog" not in call_url


# ============================================================================
# Tests for flat iteration of node_modules entries
# ============================================================================


def test_npm_discovers_nested_node_modules(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that packages at nested node_modules paths are discovered."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    lock_data: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {"a": "^1.0.0"}},
            "node_modules/a": {
                "version": "1.0.0",
            },
            "node_modules/a/node_modules/semver": {
                "version": "6.3.1",
            },
        }
    }

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package-lock.json" in path:
            return json.dumps(lock_data)
        raise FileNotFoundError

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        return_value=True,
    )
    mock_path_join = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mock_open = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )

    result = strategy._get_npm_dependencies(lock_data, "/test/path")

    assert "a" in result
    assert result["a"] == "1.0.0"
    # Nested semver at node_modules/a/node_modules/semver is discovered
    assert "semver" in result
    assert result["semver"] == "6.3.1"

    # Verify alias extraction was called
    mock_path_join.assert_called_once_with("/test/path", "package-lock.json")
    mock_open.assert_called_once()


def test_npm_excludes_dev_dependencies(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that entries with 'dev': true are excluded from results."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    lock_data: dict[str, Any] = {
        "packages": {
            "": {
                "dependencies": {"prod-dep": "^1.0.0"},
                "devDependencies": {"dev-dep": "^2.0.0"},
            },
            "node_modules/prod-dep": {"version": "1.0.0"},
            "node_modules/dev-dep": {"version": "2.0.0", "dev": True},
        }
    }

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package-lock.json" in path:
            return json.dumps(lock_data)
        raise FileNotFoundError

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        return_value=True,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )

    result = strategy._get_npm_dependencies(lock_data, "/test/path")

    assert "prod-dep" in result
    assert result["prod-dep"] == "1.0.0"
    assert "dev-dep" not in result


def test_npm_includes_optional_and_peer_dependencies(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that optional and peer deps (without dev flag) are included."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    lock_data: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {"dep": "^1.0.0"}},
            "node_modules/dep": {"version": "1.0.0"},
            "node_modules/optional-dep": {"version": "2.0.0", "optional": True},
            "node_modules/peer-dep": {"version": "3.0.0", "peer": True},
            "node_modules/dev-optional": {
                "version": "4.0.0",
                "dev": True,
                "optional": True,
            },
        }
    }

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_open(path: str) -> str:
        if "package-lock.json" in path:
            return json.dumps(lock_data)
        raise FileNotFoundError

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        return_value=True,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )

    result = strategy._get_npm_dependencies(lock_data, "/test/path")

    assert "dep" in result
    assert "optional-dep" in result
    assert "peer-dep" in result
    # dev flag takes precedence — dev-optional should be excluded
    assert "dev-optional" not in result


# ===== Tests for local_project_path mode (npm-package ecosystem) =====


def test_npm_local_project_path_skips_get_code(
    mocker: pytest_mock.MockFixture,
) -> None:
    """When local_project_path is set, get_code() should NOT be called."""
    source_code_manager_mock = mock.Mock()

    package_lock: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {"dep1": "^1.0.0"}},
            "node_modules/dep1": {"version": "1.0.5", "dependencies": {}},
        }
    }

    def fake_exists(path: str) -> bool:
        return True

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return json.dumps(package_lock)
        raise FileNotFoundError

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_output(cmd: str) -> str:
        # Handle npm list commands
        if "npm list" in cmd:
            npm_list_output = {
                "version": "1.0.0",
                "name": "test-project",
                "dependencies": {
                    "dep1": {"version": "1.0.5"},
                },
            }
            return json.dumps(npm_list_output)
        return "npm install completed"

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )
    mocker.patch(
        "requests.get",
        return_value=mock.Mock(
            status_code=200,
            json=lambda: {"license": "MIT", "author": "Alice"},
        ),
    )

    strategy = NpmMetadataCollectionStrategy(
        "express",
        source_code_manager_mock,
        ProjectScope.ALL,
        local_project_path="/tmp/npm_resolve/express",
    )

    result = strategy.augment_metadata([])

    # get_code should NOT be called
    source_code_manager_mock.get_code.assert_not_called()
    # get_canonical_urls should NOT be called
    source_code_manager_mock.get_canonical_urls.assert_not_called()
    # Should have the dependency
    assert len(result) == 1
    assert result[0].name == "dep1"
    assert result[0].version == "1.0.5"


def test_npm_local_project_path_only_root_project_fetches_from_registry(
    mocker: pytest_mock.MockFixture,
) -> None:
    """In ONLY_ROOT_PROJECT mode with local_project_path, fetch from npm registry."""
    source_code_manager_mock = mock.Mock()

    package_lock: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {"express": "^4.18.0"}},
            "node_modules/express": {"version": "4.18.2", "dependencies": {}},
        }
    }

    def fake_exists(path: str) -> bool:
        return True

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return json.dumps(package_lock)
        raise FileNotFoundError

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mock_requests = mocker.patch(
        "requests.get",
        return_value=mock.Mock(
            status_code=200,
            json=lambda: {
                "license": "MIT",
                "author": "TJ Holowaychuk",
                "repository": {"url": "https://github.com/expressjs/express"},
            },
        ),
    )

    strategy = NpmMetadataCollectionStrategy(
        "express",
        source_code_manager_mock,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/npm_resolve/express",
    )

    result = strategy.augment_metadata([])

    source_code_manager_mock.get_code.assert_not_called()
    assert len(result) == 1
    assert result[0].name == "express"
    assert result[0].version == "4.18.2"
    assert result[0].license == ["MIT"]
    assert result[0].copyright == ["TJ Holowaychuk"]
    assert result[0].origin == "https://github.com/expressjs/express"
    mock_requests.assert_called_once_with(
        "https://registry.npmjs.org/express/4.18.2", timeout=5
    )


def test_npm_local_project_path_all_mode_processes_lock_deps(
    mocker: pytest_mock.MockFixture,
) -> None:
    """In ALL mode with local_project_path, process package-lock.json deps normally."""
    source_code_manager_mock = mock.Mock()

    package_lock: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {"express": "^4.18.0"}},
            "node_modules/express": {
                "version": "4.18.2",
                "dependencies": {"accepts": "~1.3.8"},
            },
            "node_modules/accepts": {"version": "1.3.8", "dependencies": {}},
        }
    }

    def fake_exists(path: str) -> bool:
        return True

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return json.dumps(package_lock)
        raise FileNotFoundError

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    def fake_output(cmd: str) -> str:
        # Handle npm list commands
        if "npm list" in cmd:
            # Return npm list output matching the package_lock structure
            npm_list_output = {
                "version": "4.18.2",
                "name": "express",
                "dependencies": {
                    "express": {"version": "4.18.2"},
                    "accepts": {"version": "1.3.8"},
                },
            }
            return json.dumps(npm_list_output)
        return "npm install completed"

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        side_effect=fake_exists,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=fake_output,
    )
    mock_requests = mocker.patch(
        "requests.get",
        side_effect=[
            mock.Mock(
                status_code=200,
                json=lambda: {"license": "MIT", "author": "Express Team"},
            ),
            mock.Mock(
                status_code=200,
                json=lambda: {"license": "MIT", "author": "Accepts Author"},
            ),
        ],
    )

    strategy = NpmMetadataCollectionStrategy(
        "express",
        source_code_manager_mock,
        ProjectScope.ALL,
        local_project_path="/tmp/npm_resolve/express",
    )

    result = strategy.augment_metadata([])

    source_code_manager_mock.get_code.assert_not_called()
    assert len(result) == 2
    dep_names = {m.name for m in result}
    assert "express" in dep_names
    assert "accepts" in dep_names
    assert mock_requests.call_count == 2


def test_npm_local_project_path_no_lock_file_returns_unchanged(
    mocker: pytest_mock.MockFixture,
) -> None:
    """When lock file is missing in local_project_path mode, return metadata unchanged."""
    source_code_manager_mock = mock.Mock()

    def fake_path_join(*args: Any) -> str:
        return "/".join(args)

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_exists",
        return_value=False,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.path_join",
        side_effect=fake_path_join,
    )

    strategy = NpmMetadataCollectionStrategy(
        "express",
        source_code_manager_mock,
        ProjectScope.ALL,
        local_project_path="/tmp/npm_resolve/express",
    )

    initial = [
        Metadata(
            name="existing",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        )
    ]
    result = strategy.augment_metadata(initial)

    assert result == initial
    source_code_manager_mock.get_code.assert_not_called()


# ============================================================================
# Tests for npm list --json dependency discovery
# ============================================================================


def test_npm_list_discovers_dependencies(mocker: pytest_mock.MockFixture) -> None:
    """Test _get_npm_list_dependencies parses npm list output correctly."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    npm_list_output = {
        "version": "1.0.0",
        "name": "test-project",
        "dependencies": {
            "express": {
                "version": "4.22.1",
                "dependencies": {
                    "accepts": {
                        "version": "1.3.8",
                        "dependencies": {"mime-types": {"version": "2.1.35"}},
                    }
                },
            },
            "lodash": {"version": "4.17.21"},
        },
    }

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        return_value=json.dumps(npm_list_output),
    )

    result = strategy._get_npm_list_dependencies("/test/path")

    assert "express" in result
    assert result["express"] == "4.22.1"
    assert "accepts" in result
    assert result["accepts"] == "1.3.8"
    assert "mime-types" in result
    assert result["mime-types"] == "2.1.35"
    assert "lodash" in result
    assert result["lodash"] == "4.17.21"


def test_npm_list_handles_missing_version(mocker: pytest_mock.MockFixture) -> None:
    """Test that packages without version field are skipped."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    npm_list_output = {
        "dependencies": {"pkg1": {"version": "1.0.0"}, "pkg2": {}}  # No version field
    }

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        return_value=json.dumps(npm_list_output),
    )

    result = strategy._get_npm_list_dependencies("/test/path")

    assert "pkg1" in result
    assert "pkg2" not in result


def test_npm_list_handles_command_failure(
    mocker: pytest_mock.MockFixture, caplog: LogCaptureFixture
) -> None:
    """Test that npm list command failures are handled gracefully."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=Exception("npm not found"),
    )

    with caplog.at_level(logging.WARNING):
        result = strategy._get_npm_list_dependencies("/test/path")

    assert result == {}
    assert any("Failed to run npm list" in record.message for record in caplog.records)
