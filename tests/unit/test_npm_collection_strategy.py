# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import json
import pytest_mock
from unittest import mock
from typing import Any
from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.npm_collection_strategy import (
    NpmMetadataCollectionStrategy,
)


def test_npm_collection_strategy_no_package_lock(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    mocker.patch("dd_license_attribution.adaptors.os.path_exists", return_value=False)
    mocker.patch("dd_license_attribution.adaptors.os.output_from_command")
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
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    mocker.patch("dd_license_attribution.adaptors.os.path_exists", return_value=True)
    mocker.patch("dd_license_attribution.adaptors.os.output_from_command")
    mocker.patch(
        "dd_license_attribution.adaptors.os.open_file",
        mock.mock_open(read_data=json.dumps({"packages": {"": {"dependencies": {}}}})),
    )
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
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    package_lock = {
        "packages": {
            "": {"dependencies": {"dep1": "1.0.0", "dep2": "2.0.0"}},
            "node_modules/dep1": {"version": "1.0.0", "dependencies": {}},
            "node_modules/dep2": {"version": "2.0.0", "dependencies": {}},
        }
    }

    def fake_exists(path: str) -> bool:
        if path.endswith("package-lock.json"):
            return True
        return False

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return package_lock
        raise FileNotFoundError

    def fake_path_join(*args):
        result = "/".join(args)
        return result

    def fake_output_from_command(command: str) -> str:
        return "npm install completed successfully"

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
        side_effect=fake_output_from_command,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "npm_collection_strategy.open_file",
        side_effect=fake_open,
    )
    mocker.patch(
        "requests.get",
        side_effect=[
            mock.Mock(
                status_code=200, json=lambda: {"license": "MIT", "author": "Alice"}
            ),
            mock.Mock(
                status_code=200, json=lambda: {"license": "Apache-2.0", "author": "Bob"}
            ),
        ],
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
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    package_lock = {
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

    def fake_exists(path: str) -> bool:
        if "package-lock.json" in path:
            return True
        return False

    def fake_path_join(*args):
        result = "/".join(args)
        return result

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return package_lock
        raise FileNotFoundError

    def fake_output_from_command(command: str) -> str:
        return "npm install completed successfully"

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
    mocker.patch(
        "requests.get",
        side_effect=[
            mock.Mock(
                status_code=200, json=lambda: {"license": "MIT", "author": "Alice"}
            ),
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
        ],
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
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    package_lock = {
        "packages": {
            "": {"dependencies": {"dep1": "1.0.0"}},
            "node_modules/dep1": {"version": "1.0.0", "dependencies": {}},
        }
    }

    def fake_exists(path: str) -> bool:
        if "package-lock.json" in path:
            return True
        return False

    def fake_path_join(*args):
        result = "/".join(args)
        return result

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return package_lock
        raise FileNotFoundError

    def fake_output_from_command(command: str) -> str:
        return "npm install completed successfully"

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
    mocker.patch(
        "requests.get",
        side_effect=[
            mock.Mock(
                status_code=200, json=lambda: {"license": "MIT", "author": "Alice"}
            )
        ],
    )

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
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    package_lock = {
        "dependencies": {
            "dep1": {"version": "1.0.0", "resolved": "https://npmjs.com/dep1"},
        }
    }

    def fake_exists(path: str) -> bool:
        if "package-lock.json" in path:
            return True
        return False

    def fake_path_join(*args):
        result = "/".join(args)
        return result

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return package_lock
        raise FileNotFoundError

    def fake_output_from_command(command: str) -> str:
        return "npm install completed successfully"

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
    result = strategy.augment_metadata(initial_metadata)
    # Should return original metadata when packages key is missing
    assert result == initial_metadata


def test_npm_collection_strategy_handles_missing_root_package(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    package_lock = {
        "packages": {"node_modules/dep1": {"version": "1.0.0", "dependencies": {}}}
    }

    def fake_exists(path: str) -> bool:
        if "package-lock.json" in path:
            return True
        return False

    def fake_path_join(*args):
        result = "/".join(args)
        return result

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return package_lock
        raise FileNotFoundError

    def fake_output_from_command(command: str) -> str:
        return "npm install completed successfully"

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

    mocker.patch("dd_license_attribution.adaptors.os.output_from_command")
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
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    package_lock = {
        "packages": {
            "": {"dependencies": {"dep1": "1.0.0", "dep2": "2.0.0"}},
            "node_modules/dep1": {"version": "1.0.0", "dependencies": {}},
            "node_modules/dep2": {"version": "2.0.0", "dependencies": {}},
        }
    }

    def fake_exists(path: str) -> bool:
        if "package-lock.json" in path:
            return True
        return False

    def fake_path_join(*args):
        result = "/".join(args)
        return result

    def fake_open(path: str, *args: Any, **kwargs: Any) -> Any:
        if "package-lock.json" in path:
            return package_lock
        raise FileNotFoundError

    def fake_output_from_command(command: str) -> str:
        return "npm install completed successfully"

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

    mocker.patch(
        "requests.get",
        side_effect=[
            mock.Mock(status_code=404),  # dep1 not found
            mock.Mock(
                status_code=200, json=lambda: {"license": "Apache-2.0", "author": "Bob"}
            ),
        ],
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
    result = strategy.augment_metadata(initial_metadata)

    # Should have both dependencies, but dep1 with empty license/copyright
    assert len(result) == 3  # package1 + dep1 + dep2

    # Find dep1 and dep2 in results
    dep1_meta = next((m for m in result if m.name == "dep1"), None)
    dep2_meta = next((m for m in result if m.name == "dep2"), None)

    assert dep1_meta is not None
    assert dep2_meta is not None
    assert dep1_meta.license == []  # Should be empty due to 404
    assert dep2_meta.license == ["Apache-2.0"]  # Should have license
