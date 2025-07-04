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
    requests_responses: list[mock.Mock],
) -> None:
    """Setup common mocks for npm collection strategy tests."""

    def fake_exists(path: str) -> bool:
        if path.endswith("package-lock.json"):
            return True
        return False

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return json.dumps(package_lock)
        raise FileNotFoundError

    def fake_path_join(*args: Any) -> str:
        result = "/".join(args)
        return result

    def fake_output_from_command(command: str) -> str:
        return "npm install completed successfully"

    # Mock all the required functions
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
    mocker.patch("requests.get", side_effect=requests_responses)


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
    package_lock: dict[str, Any] = {
        "packages": {
            "": {"dependencies": {}},
        }
    }
    requests_responses: list[mock.Mock] = []
    setup_npm_strategy_mocks(mocker, package_lock, requests_responses)
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


def test_npm_collection_strategy_adds_npm_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
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

    setup_npm_strategy_mocks(mocker, package_lock, requests_responses)

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


def test_npm_collection_strategy_extracts_transitive_dependencies(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
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

    setup_npm_strategy_mocks(mocker, package_lock, requests_responses)

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


def test_npm_collection_strategy_avoids_duplicates_and_respects_only_transitive(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_lock = {
        "packages": {
            "": {"dependencies": {"dep1": "1.0.0"}},
            "node_modules/dep1": {"version": "1.0.0", "dependencies": {}},
        }
    }

    requests_responses = [
        mock.Mock(status_code=200, json=lambda: {"license": "MIT", "author": "Alice"})
    ]

    setup_npm_strategy_mocks(mocker, package_lock, requests_responses)

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


def test_npm_collection_strategy_handles_missing_packages_key(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_lock: dict[str, Any] = {
        "dependencies": {
            "dep1": {"version": "1.0.0", "resolved": "https://npmjs.com/dep1"},
        }
    }

    requests_responses: list[mock.Mock] = []

    setup_npm_strategy_mocks(mocker, package_lock, requests_responses)

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
    assert result == initial_metadata


def test_npm_collection_strategy_handles_missing_root_package(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_lock: dict[str, Any] = {
        "packages": {"node_modules/dep1": {"version": "1.0.0", "dependencies": {}}}
    }

    requests_responses: list[mock.Mock] = []

    setup_npm_strategy_mocks(mocker, package_lock, requests_responses)

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


def test_npm_collection_strategy_handles_registry_api_failures(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
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

    setup_npm_strategy_mocks(mocker, package_lock, requests_responses)

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


def test_npm_collection_strategy_logs_warning_on_non_200_response(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()
    package_lock = {
        "packages": {
            "": {"dependencies": {"dep1": "1.0.0"}},
            "node_modules/dep1": {"version": "1.0.0", "dependencies": {}},
        }
    }

    requests_responses = [mock.Mock(status_code=404, text="Not Found")]

    setup_npm_strategy_mocks(mocker, package_lock, requests_responses)

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


def test_npm_collection_strategy_handles_npm_install_failure(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    source_code_manager_mock = create_source_code_manager_mock()

    # Mock output_from_command to raise an exception
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.output_from_command",
        side_effect=Exception("npm not found"),
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

    with caplog.at_level(logging.WARNING):
        result = strategy.augment_metadata(initial_metadata)

    expected_warning = "Failed to run npm install for package1: npm not found"
    assert any(expected_warning in record.message for record in caplog.records)

    assert result == initial_metadata
