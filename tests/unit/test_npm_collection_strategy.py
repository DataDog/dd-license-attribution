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
            "": {"dependencies": {"dep1": "1.0.0", "dep2": "2.0.0"}},
            "node_modules/dep1": {"version": "1.0.0", "dependencies": {}},
            "node_modules/dep2": {"version": "2.0.0", "dependencies": {}},
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
            version="1.0.0",
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
        Metadata(
            name="dep2",
            version="2.0.0",
            origin="npm:dep2",
            local_src_path=None,
            license=["Apache-2.0"],
            copyright=["Bob"],
        ),
    ]
    assert result == expected_metadata
    mock_output_from_command.assert_called_once_with(
        f"CWD=`pwd`; cd cache_dir/org_package1 && npm install --package-lock-only --force; cd $CWD"
    )
    assert mock_exists.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_path_join.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_open.call_count == 2  # package.json, package-lock.json
    assert mock_requests.call_count == 2


def test_npm_collection_strategy_extracts_transitive_dependencies(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {"dep1": "1.0.0"}},
            "node_modules/dep1": {
                "version": "1.0.0",
                "dependencies": {"transitive1": "1.1.0", "transitive2": "1.2.0"},
            },
            "node_modules/transitive1": {
                "version": "1.1.0",
                "dependencies": {"deep1": "2.0.0"},
            },
            "node_modules/transitive2": {"version": "1.2.0", "dependencies": {}},
            "node_modules/deep1": {"version": "2.0.0", "dependencies": {}},
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
            version="1.0.0",
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
        Metadata(
            name="transitive1",
            version="1.1.0",
            origin="npm:transitive1",
            local_src_path=None,
            license=["Apache-2.0"],
            copyright=["Bob"],
        ),
        Metadata(
            name="transitive2",
            version="1.2.0",
            origin="npm:transitive2",
            local_src_path=None,
            license=["BSD-3-Clause"],
            copyright=["Charlie"],
        ),
        Metadata(
            name="deep1",
            version="2.0.0",
            origin="npm:deep1",
            local_src_path=None,
            license=["GPL-3.0"],
            copyright=["David"],
        ),
    ]
    assert result == expected_metadata
    mock_output_from_command.assert_called_once_with(
        f"CWD=`pwd`; cd cache_dir/org_package1 && npm install --package-lock-only --force; cd $CWD"
    )
    assert mock_exists.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_path_join.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_open.call_count == 2  # package.json, package-lock.json
    assert mock_requests.call_count == 4


def test_npm_collection_strategy_avoids_duplicates_and_respects_only_transitive(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_json: dict[str, Any] = {}
    package_lock = {
        "packages": {
            "": {"dependencies": {"dep1": "1.0.0"}},
            "node_modules/dep1": {"version": "1.0.0", "dependencies": {}},
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
            version="1.0.0",
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
            version="1.0.0",
            origin="npm:dep1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Alice"],
        ),
    ]
    assert result == expected_metadata
    mock_output_from_command.assert_called_once_with(
        f"CWD=`pwd`; cd cache_dir/org_package1 && npm install --package-lock-only --force; cd $CWD"
    )
    assert mock_exists.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_path_join.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_open.call_count == 2  # package.json, package-lock.json
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
    # Should return original metadata when packages key is missing
    mock_output_from_command.assert_called_once_with(
        f"CWD=`pwd`; cd cache_dir/org_package1 && npm install --package-lock-only --force; cd $CWD"
    )
    assert mock_exists.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_path_join.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_open.call_count == 2  # package.json, package-lock.json
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
    # Should return original metadata when root package is missing
    assert result == initial_metadata
    mock_output_from_command.assert_called_once_with(
        f"CWD=`pwd`; cd cache_dir/org_package1 && npm install --package-lock-only --force; cd $CWD"
    )
    assert mock_exists.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_path_join.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_open.call_count == 2  # package.json, package-lock.json
    mock_requests.assert_not_called()


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
    mock_output_from_command.assert_called_once_with(
        f"CWD=`pwd`; cd cache_dir/org_package1 && npm install --package-lock-only --force; cd $CWD"
    )
    assert mock_exists.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_path_join.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_open.call_count == 2  # package.json, package-lock.json
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
    mock_output_from_command.assert_called_once_with(
        f"CWD=`pwd`; cd cache_dir/org_package1 && npm install --package-lock-only --force; cd $CWD"
    )
    assert mock_exists.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_path_join.call_count == 3  # package.json, yarn.lock, package-lock.json
    assert mock_open.call_count == 2  # package.json, package-lock.json
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

    expected_warning = "Failed to run npm install for package1: npm not found"
    assert any(expected_warning in record.message for record in caplog.records)

    assert result == initial_metadata
    mock_output_from_command.assert_called_once_with(
        "CWD=`pwd`; cd cache_dir/org_package1 && npm install --package-lock-only --force; cd $CWD"
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


def test_clean_version_string() -> None:
    """Test _clean_version_string with various version string formats."""
    source_code_manager_mock = create_source_code_manager_mock()
    strategy = NpmMetadataCollectionStrategy(
        "package1", source_code_manager_mock, ProjectScope.ALL
    )

    test_cases = {
        # Basic prefix removals
        "^1.2.3": "1.2.3",
        "~1.2.3": "1.2.3",
        ">1.2.3": "1.2.3",
        ">=1.2.3": "1.2.3",
        # Plain version unchanged
        "1.2.3": "1.2.3",
        # Empty string
        "": "",
        # Pre-release versions
        "^1.2.3-alpha.1": "1.2.3-alpha.1",
        "~2.0.0-beta": "2.0.0-beta",
        # Build metadata
        ">=1.0.0+build.1": "1.0.0+build.1",
        # Edge cases with only prefixes
        "^": "",
        "~": "",
        ">": "",
        ">=": "",
        # Priority test - >= should be handled first, not just >
        ">=1.0.0": "1.0.0",
    }

    for input_version, expected_output in test_cases.items():
        result = strategy._clean_version_string(input_version)
        assert (
            result == expected_output
        ), f"Failed for '{input_version}': expected '{expected_output}', got '{result}'"


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
