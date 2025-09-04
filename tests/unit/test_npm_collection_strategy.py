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
    assert mock_exists.call_count == 2
    assert mock_path_join.call_count == 2
    assert mock_open.call_count == 2
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
    assert mock_exists.call_count == 2
    assert mock_path_join.call_count == 2
    assert mock_open.call_count == 2
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
    assert mock_exists.call_count == 2
    assert mock_path_join.call_count == 2
    assert mock_open.call_count == 2
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
    assert mock_exists.call_count == 2
    assert mock_path_join.call_count == 2
    assert mock_open.call_count == 2
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
    assert mock_exists.call_count == 2
    assert mock_path_join.call_count == 2
    assert mock_open.call_count == 2
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
    assert mock_exists.call_count == 2
    assert mock_path_join.call_count == 2
    assert mock_open.call_count == 2
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
    assert mock_exists.call_count == 2
    assert mock_path_join.call_count == 2
    assert mock_open.call_count == 2
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
    mock_exists.assert_called_once()
    mock_path_join.assert_called_once_with("cache_dir/org_package1", "package.json")
    mock_open.assert_called_once()
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
