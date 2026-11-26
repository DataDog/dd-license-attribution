# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json
import logging
from unittest.mock import call

import pytest
import pytest_mock

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.go_package_resolver import (
    SYNTHETIC_MODULE_NAME,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy import (
    GoPkgMetadataCollectionStrategy,
)


def test_gopkg_collection_strategy_do_not_decrement_list_of_dependencies_if_not_go_related(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = ("package1", None)
    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "package1", mock_source_code_manager, ProjectScope.ALL
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


def test_gopkg_collection_strategy_adds_gopkg_metadata_to_list_of_dependencies(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/org/package1",
        None,
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/org/package1", mock_source_code_manager, ProjectScope.ALL
    )

    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )

    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory"
    )
    mock_walk_directory.return_value = [
        ("org_package1", ["package3", "ignore"], ["go.mod", "test"]),
        ("org_package1/package3", [], ["go.mod", "license"]),
        ("org_package1/ignore", [], ["license"]),
    ]

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command"
    )

    deps_list_json_1 = """
{
    "ImportPath": "github.com/org/package1",
    "Module": {
        "Path": "github.com/org/package1",
        "Main": true,
        "Version": "v1.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0"
    }
}
{
    "ImportPath": "github.com/org/package1/package5/foo",
    "Module": {
        "Path": "github.com/org/package1/package5",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package5"
    }
}
{
    "ImportPath": "bytes",
    "Standard": true
}"""

    deps_list_json_3 = """
{
    "ImportPath": "github.com/org/package1/package3",
    "Module": {
        "Path": "github.com/org/package1/package3",
        "Main": true,
        "Version": "v1.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0/package3"
    }
}
{
    "ImportPath": "github.com/org/package4",
    "Module": {
        "Path": "github.com/org/package4",
        "Version": "v1.2.3",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package4@v1.2.3"
    }
}"""

    branch_detection_output = (
        "ref: refs/heads/main\tHEAD\n72a11341aa684010caf1ca5dee779f0e7e84dfe9\tHEAD\n"
    )

    mock_output_from_command.side_effect = [
        deps_list_json_1,
        branch_detection_output,
        deps_list_json_3,
    ]

    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.open_file",
        return_value="module github.com/org/package1",
    )

    initial_metadata = [
        Metadata(
            name="github.com/org/package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=["Apache-2.0"],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package2",
            origin="package2_origin",
            local_src_path=None,
            license=["MIT"],
            version="1.2",
            copyright=["Datadog Inc."],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="github.com/org/package1",
            origin="https://github.com/org/package1",
            local_src_path="/tmp/go/pkg/mod/github.com/org/package1@v1.0",
            license=["Apache-2.0"],
            version="v1.0",
            copyright=[],
        ),
        Metadata(
            name="package2",
            origin="package2_origin",
            local_src_path=None,
            license=["MIT"],
            version="1.2",
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="github.com/org/package1/package5",
            version=None,
            origin="https://github.com/org/package1/tree/main/package5",
            local_src_path="/tmp/go/pkg/mod/github.com/org/package5",
            license=[],
            copyright=[],
        ),
        Metadata(
            name="github.com/org/package1/package3",
            origin="https://github.com/org/package1/tree/main/package3",
            local_src_path="/tmp/go/pkg/mod/github.com/org/package1@v1.0/package3",
            license=[],
            version="v1.0",
            copyright=[],
        ),
        Metadata(
            name="github.com/org/package4",
            origin="https://github.com/org/package4",
            local_src_path="/tmp/go/pkg/mod/github.com/org/package4@v1.2.3",
            license=[],
            version="v1.2.3",
            copyright=[],
        ),
    ]

    assert result == expected_metadata

    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/package1"
    )
    mock_walk_directory.assert_called_once_with("cache_dir/org_package1")
    mock_output_from_command.assert_has_calls(
        [
            mocker.call(
                ["go", "list", "-json", "all"],
                cwd="org_package1",
                env={"GOTOOLCHAIN": "auto"},
            ),
            mocker.call(
                [
                    "git",
                    "ls-remote",
                    "--symref",
                    "https://github.com/org/package1",
                    "HEAD",
                ]
            ),
            mocker.call(
                ["go", "list", "-json", "all"],
                cwd="org_package1/package3",
                env={"GOTOOLCHAIN": "auto"},
            ),
        ]
    )
    mock_open_file.assert_has_calls(
        [call("org_package1/go.mod"), call("org_package1/package3/go.mod")]
    )


def test_gopkg_collection_strategy_adds_gopkg_metadata_to_list_of_dependencies_but_skips_example_projects(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/org/package1",
        None,
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/org/package1", mock_source_code_manager, ProjectScope.ALL
    )

    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )

    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory"
    )
    mock_walk_directory.return_value = [
        ("org_package1", ["src", "examples"], ["go.mod"]),
        ("org_package1/src", [], ["go.mod"]),
        ("org_package1/examples", [], ["go.mod"]),
    ]

    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.open_file",
        side_effect=[
            "module github.com/org/package1",
            "module github.com/org/package1/src",
            """
module github.com/org/package1/examples
require github.com/org/package1 v1.0
""",
        ],
    )

    deps_list_json_top = """
{
    "ImportPath": "github.com/org/package1",
    "Module": {
        "Path": "github.com/org/package1",
        "Main": true,
        "Version": "v1.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0"
    }
}
{
    "ImportPath": "github.com/org/package1/src/foo",
    "Module": {
        "Path": "github.com/org/package1/src",
        "Version": "v1.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package1/src"
    }
}"""
    deps_list_json_src = """
{
    "ImportPath": "github.com/org/package1/src",
    "Module": {
        "Path": "github.com/org/package1/src",
        "Main": true,
        "Version": "v1.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package1/src"
    }
}"""

    branch_detection_output = (
        "ref: refs/heads/main\tHEAD\n72a11341aa684010caf1ca5dee779f0e7e84dfe9\tHEAD\n"
    )

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[
            deps_list_json_top,
            branch_detection_output,
            deps_list_json_src,
        ],
    )

    initial_metadata = [
        Metadata(
            name="github.com/org/package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=["Apache-2.0"],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="package2",
            origin="package2_origin",
            local_src_path=None,
            license=["MIT"],
            version="1.2",
            copyright=["Datadog Inc."],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="github.com/org/package1",
            origin="https://github.com/org/package1",
            local_src_path="/tmp/go/pkg/mod/github.com/org/package1@v1.0",
            license=["Apache-2.0"],
            version="v1.0",
            copyright=[],
        ),
        Metadata(
            name="package2",
            origin="package2_origin",
            local_src_path=None,
            license=["MIT"],
            version="1.2",
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="github.com/org/package1/src",
            origin="https://github.com/org/package1/tree/main/src",
            local_src_path="/tmp/go/pkg/mod/github.com/org/package1/src",
            license=[],
            version="v1.0",
            copyright=[],
        ),
    ]

    assert result == expected_metadata

    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/package1"
    )
    mock_walk_directory.assert_called_once_with("cache_dir/org_package1")
    mock_output_from_command.assert_has_calls(
        [
            mocker.call(
                ["go", "list", "-json", "all"],
                cwd="org_package1",
                env={"GOTOOLCHAIN": "auto"},
            ),
            mocker.call(
                [
                    "git",
                    "ls-remote",
                    "--symref",
                    "https://github.com/org/package1",
                    "HEAD",
                ]
            ),
            mocker.call(
                ["go", "list", "-json", "all"],
                cwd="org_package1/src",
                env={"GOTOOLCHAIN": "auto"},
            ),
        ]
    )

    mock_open_file.assert_has_calls(
        [
            call("org_package1/go.mod"),
            call("org_package1/src/go.mod"),
            call("org_package1/examples/go.mod"),
        ]
    )


def test_gopkg_collection_strategy_only_updates_local_source_path_when_only_root_is_passed(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/org/package1",
        None,
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/org/package1",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
    )

    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )

    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory"
    )

    mock_walk_directory.return_value = [
        ("org_package1", ["src", "examples"], ["go.mod"]),
        ("org_package1/src", [], ["go.mod"]),
    ]

    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.open_file",
        return_value="module github.com/org/package1",
    )

    deps_list_json_top = """
{
    "ImportPath": "github.com/org/package1",
    "Module": {
        "Path": "github.com/org/package1",
        "Main": true,
        "Version": "v1.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0"
    }
}
{
    "ImportPath": "github.com/org/package1/src/foo",
    "Module": {
        "Path": "github.com/org/package1/src",
        "Version": "v1.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package1/src"
    }
}
{
    "ImportPath": "github.com/org/package2/bar",
    "Module": {
        "Path": "github.com/org/package2",
        "Version": "v1.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package2"
    }
}"""

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json_top,
    )

    initial_metadata = [
        Metadata(
            name="github.com/org/package1",
            origin="https://github.com/org/package1",
            local_src_path=None,
            license=[],
            copyright=[],
            version=None,
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="github.com/org/package1",
            origin="https://github.com/org/package1",
            local_src_path="/tmp/go/pkg/mod/github.com/org/package1@v1.0",
            license=[],
            version="v1.0",
            copyright=[],
        ),
    ]

    assert result == expected_metadata

    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/package1"
    )

    mock_walk_directory.assert_called_once_with("cache_dir/org_package1")
    mock_output_from_command.assert_has_calls(
        [
            call(
                ["go", "list", "-json", "all"],
                cwd="org_package1",
                env={"GOTOOLCHAIN": "auto"},
            ),
            call(
                ["go", "list", "-json", "all"],
                cwd="org_package1/src",
                env={"GOTOOLCHAIN": "auto"},
            ),
        ]
    )
    mock_open_file.assert_has_calls(
        [call("org_package1/go.mod"), call("org_package1/src/go.mod")]
    )


def test_gopkg_local_project_path_skips_get_code_and_resolves_dependencies(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/stretchr/testify",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/github_com_stretchr_testify",
    )

    # go list -json all returns package-level data with nested Module key
    deps_list_json = """
{
    "ImportPath": "main",
    "Module": {
        "Path": "ddla-go-resolve",
        "Main": true,
        "Dir": "/tmp/go-resolve/github_com_stretchr_testify"
    }
}
{
    "ImportPath": "github.com/stretchr/testify/assert",
    "Module": {
        "Path": "github.com/stretchr/testify",
        "Version": "v1.9.0",
        "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    }
}
{
    "ImportPath": "github.com/davecgh/go-spew/spew",
    "Module": {
        "Path": "github.com/davecgh/go-spew",
        "Version": "v1.1.1",
        "Dir": "/tmp/go/pkg/mod/github.com/davecgh/go-spew@v1.1.1"
    }
}"""

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    initial_metadata = [
        Metadata(
            name="github.com/stretchr/testify",
            origin="github.com/stretchr/testify",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Seed entry should be removed (version=None), replaced by go list data
    assert len(result) == 2
    assert result[0].name == "github.com/stretchr/testify"
    assert result[0].version == "v1.9.0"
    assert (
        result[0].local_src_path == "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    )
    assert result[0].origin == "https://github.com/stretchr/testify"
    assert result[1].name == "github.com/davecgh/go-spew"
    assert result[1].version == "v1.1.1"
    assert result[1].origin == "https://github.com/davecgh/go-spew"

    # get_code should NOT be called
    mock_source_code_manager.get_code.assert_not_called()
    # get_canonical_urls should NOT be called
    mock_source_code_manager.get_canonical_urls.assert_not_called()

    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/github_com_stretchr_testify",
        env={"GOTOOLCHAIN": "auto"},
    )


def test_gopkg_local_project_path_filters_synthetic_module(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/stretchr/testify",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/testify",
    )

    # Output includes the synthetic module — it should be filtered out
    deps_list_json = """
{{
    "ImportPath": "main",
    "Module": {{
        "Path": "{synthetic}",
        "Main": true,
        "Dir": "/tmp/go-resolve/testify"
    }}
}}
{{
    "ImportPath": "github.com/stretchr/testify/assert",
    "Module": {{
        "Path": "github.com/stretchr/testify",
        "Version": "v1.9.0",
        "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    }}
}}""".format(synthetic=SYNTHETIC_MODULE_NAME)

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    initial_metadata = [
        Metadata(
            name="github.com/stretchr/testify",
            origin="github.com/stretchr/testify",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Only testify should be in the result, not the synthetic module
    assert len(result) == 1
    assert result[0].name == "github.com/stretchr/testify"
    assert result[0].version == "v1.9.0"
    # Verify no entry for synthetic module
    assert not any(m.name == SYNTHETIC_MODULE_NAME for m in result)


def test_gopkg_local_project_path_removes_seed_entry(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/stretchr/testify",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/testify",
    )

    deps_list_json = """
{
    "ImportPath": "github.com/stretchr/testify/assert",
    "Module": {
        "Path": "github.com/stretchr/testify",
        "Version": "v1.9.0",
        "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    }
}"""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    # Seed entry has version=None — should be removed and replaced by go list data
    seed_metadata = [
        Metadata(
            name="github.com/stretchr/testify",
            origin="github.com/stretchr/testify",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="other-package",
            origin="other-origin",
            local_src_path=None,
            license=["MIT"],
            version="1.0",
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(seed_metadata)

    # Seed entry removed, replaced by go list entry; other-package preserved
    assert len(result) == 2
    assert result[0].name == "other-package"
    assert result[0].version == "1.0"
    assert result[1].name == "github.com/stretchr/testify"
    assert result[1].version == "v1.9.0"


def test_gopkg_local_project_path_only_root_project(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/stretchr/testify",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/go-resolve/testify",
    )

    deps_list_json = """
{
    "ImportPath": "github.com/stretchr/testify/assert",
    "Module": {
        "Path": "github.com/stretchr/testify",
        "Version": "v1.9.0",
        "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    }
}
{
    "ImportPath": "github.com/davecgh/go-spew/spew",
    "Module": {
        "Path": "github.com/davecgh/go-spew",
        "Version": "v1.1.1",
        "Dir": "/tmp/go/pkg/mod/github.com/davecgh/go-spew@v1.1.1"
    }
}"""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    # only_root_project: only testify is in the initial metadata (after seed removal),
    # so go-spew should NOT be added
    initial_metadata = [
        Metadata(
            name="github.com/stretchr/testify",
            origin="github.com/stretchr/testify",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Seed removed, testify re-added from go list (it was in the original metadata).
    # go-spew filtered out by only_root_project since it wasn't in the seed.
    assert len(result) == 1
    assert result[0].name == "github.com/stretchr/testify"
    assert result[0].version == "v1.9.0"
    assert (
        result[0].local_src_path == "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    )


def test_gopkg_local_project_path_only_root_project_with_versioned_spec(
    mocker: pytest_mock.MockFixture,
) -> None:
    """ONLY_ROOT_PROJECT must include the root module even when the seed name has @version."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/stretchr/testify@v1.9.0",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/go-resolve/testify",
    )

    deps_list_json = """
{
    "ImportPath": "github.com/stretchr/testify/assert",
    "Module": {
        "Path": "github.com/stretchr/testify",
        "Version": "v1.9.0",
        "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    }
}
{
    "ImportPath": "github.com/davecgh/go-spew/spew",
    "Module": {
        "Path": "github.com/davecgh/go-spew",
        "Version": "v1.1.1",
        "Dir": "/tmp/go/pkg/mod/github.com/davecgh/go-spew@v1.1.1"
    }
}"""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    # Seed entry has @version in the name — previously this caused root module to be filtered out
    initial_metadata = [
        Metadata(
            name="github.com/stretchr/testify@v1.9.0",
            origin="github.com/stretchr/testify@v1.9.0",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # testify should be included; go-spew should be filtered by only_root_project
    assert len(result) == 1
    assert result[0].name == "github.com/stretchr/testify"
    assert result[0].version == "v1.9.0"


def test_gopkg_local_project_path_only_root_project_does_not_match_v1_for_v2_spec(
    mocker: pytest_mock.MockFixture,
) -> None:
    """ONLY_ROOT_PROJECT must not include the v1 module when a v2+ subpackage is requested."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/lib/v2/foo",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/go-resolve/lib_v2_foo",
    )

    deps_list_json = """
{
    "ImportPath": "github.com/org/lib/v2/foo",
    "Module": {
        "Path": "github.com/org/lib/v2",
        "Version": "v2.1.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/lib/v2@v2.1.0"
    }
}
{
    "ImportPath": "github.com/org/lib/something",
    "Module": {
        "Path": "github.com/org/lib",
        "Version": "v1.5.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/lib@v1.5.0"
    }
}"""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    # Seed is a v2 subpackage; v1 module github.com/org/lib must NOT be included
    initial_metadata = [
        Metadata(
            name="github.com/org/lib/v2/foo",
            origin="github.com/org/lib/v2/foo",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert len(result) == 1
    assert result[0].name == "github.com/org/lib/v2"
    assert result[0].version == "v2.1.0"


def test_gopkg_local_project_path_only_root_project_with_subpackage_spec(
    mocker: pytest_mock.MockFixture,
) -> None:
    """ONLY_ROOT_PROJECT must include the root module when the seed is a subpackage path."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/stretchr/testify/assert",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/go-resolve/testify_assert",
    )

    deps_list_json = """
{
    "ImportPath": "github.com/stretchr/testify/assert",
    "Module": {
        "Path": "github.com/stretchr/testify",
        "Version": "v1.9.0",
        "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    }
}
{
    "ImportPath": "github.com/davecgh/go-spew/spew",
    "Module": {
        "Path": "github.com/davecgh/go-spew",
        "Version": "v1.1.1",
        "Dir": "/tmp/go/pkg/mod/github.com/davecgh/go-spew@v1.1.1"
    }
}"""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    # Seed name is a subpackage path; the go list module path is the parent module
    initial_metadata = [
        Metadata(
            name="github.com/stretchr/testify/assert",
            origin="github.com/stretchr/testify/assert",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # The parent module should be included; go-spew filtered by only_root_project
    assert len(result) == 1
    assert result[0].name == "github.com/stretchr/testify"
    assert result[0].version == "v1.9.0"


def test_gopkg_local_project_path_empty_output_returns_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/stretchr/testify",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/testify",
    )

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value="",
    )

    initial_metadata = [
        Metadata(
            name="github.com/stretchr/testify",
            origin="github.com/stretchr/testify",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Seed removed, empty output means no deps found. An empty package
    # listing is a `go list` failure, not a module-graph fallback signal, so
    # the module graph must not be enumerated.
    assert len(result) == 0
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/testify",
        env={"GOTOOLCHAIN": "auto"},
    )


def test_gopkg_local_project_path_updates_existing_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/some/package",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/some_package",
    )

    deps_list_json = """
{
    "ImportPath": "github.com/stretchr/testify/assert",
    "Module": {
        "Path": "github.com/stretchr/testify",
        "Version": "v1.9.0",
        "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    }
}"""

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    # Pre-existing entry for testify from earlier strategy — should be updated, not duplicated
    initial_metadata = [
        Metadata(
            name="github.com/some/package",
            origin="github.com/some/package",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="github.com/stretchr/testify",
            origin="some-old-origin",
            local_src_path=None,
            license=["BSD-3-Clause"],
            version="v1.8.0",
            copyright=["stretchr"],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # testify should be updated in place, not duplicated
    assert len(result) == 1
    testify = result[0]
    assert testify.name == "github.com/stretchr/testify"
    assert testify.origin == "https://github.com/stretchr/testify"
    assert (
        testify.local_src_path == "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    )
    assert testify.version == "v1.9.0"
    # License and copyright from earlier strategy should be preserved
    assert testify.license == ["BSD-3-Clause"]
    assert testify.copyright == ["stretchr"]


def test_gopkg_local_project_path_indirect_dep_without_dir(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Modules without a Dir field in go list output should get local_src_path=None
    so downstream strategies (e.g. ScanCode) skip local scanning instead of
    crashing on an empty path.
    """
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/stretchr/testify",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/testify",
    )

    # objx module has no Dir field
    deps_list_json = """
{
    "ImportPath": "main",
    "Module": {
        "Path": "ddla-go-resolve",
        "Main": true,
        "Dir": "/tmp/go-resolve/testify"
    }
}
{
    "ImportPath": "github.com/stretchr/testify/assert",
    "Module": {
        "Path": "github.com/stretchr/testify",
        "Version": "v1.9.0",
        "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    }
}
{
    "ImportPath": "github.com/stretchr/objx",
    "Module": {
        "Path": "github.com/stretchr/objx",
        "Version": "v0.5.2"
    }
}"""

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    initial_metadata = [
        Metadata(
            name="github.com/stretchr/testify",
            origin="github.com/stretchr/testify",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert len(result) == 2
    testify = next(m for m in result if m.name == "github.com/stretchr/testify")
    objx = next(m for m in result if m.name == "github.com/stretchr/objx")

    assert testify.version == "v1.9.0"
    assert (
        testify.local_src_path == "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
    )

    assert objx.version == "v0.5.2"
    assert objx.local_src_path is None  # No Dir → None, not empty string
    assert objx.origin == "https://github.com/stretchr/objx"

    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/testify",
        env={"GOTOOLCHAIN": "auto"},
    )


def test_gopkg_local_project_path_module_graph_fallback(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/DataDog/package-blast-radius",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/github_com_DataDog_package-blast-radius",
    )

    # Package listing contains only the synthetic main package: the resolver
    # resolved a module without an importable root package.
    package_list_json = """
{
    "ImportPath": "ddla-go-resolve",
    "Module": {
        "Path": "%s",
        "Main": true,
        "Dir": "/tmp/go-resolve/github_com_DataDog_package-blast-radius"
    }
}""" % (SYNTHETIC_MODULE_NAME)

    # Module graph listing provides the transitive dependency closure.
    module_graph_json = """
{
    "Path": "%s",
    "Main": true,
    "Dir": "/tmp/go-resolve/github_com_DataDog_package-blast-radius"
}
{
    "Path": "github.com/DataDog/package-blast-radius",
    "Version": "v0.0.3",
    "Dir": "/tmp/go/pkg/mod/github.com/!data!dog/package-blast-radius@v0.0.3"
}
{
    "Path": "github.com/spf13/cobra",
    "Version": "v1.10.2"
}""" % (SYNTHETIC_MODULE_NAME)

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[package_list_json, module_graph_json],
    )

    initial_metadata = [
        Metadata(
            name="github.com/DataDog/package-blast-radius",
            origin="github.com/DataDog/package-blast-radius",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Seed entry replaced by module graph data, synthetic module filtered out
    assert len(result) == 2
    root = next(
        m for m in result if m.name == "github.com/DataDog/package-blast-radius"
    )
    cobra = next(m for m in result if m.name == "github.com/spf13/cobra")

    assert root.version == "v0.0.3"
    assert (
        root.local_src_path
        == "/tmp/go/pkg/mod/github.com/!data!dog/package-blast-radius@v0.0.3"
    )
    assert root.origin == "https://github.com/DataDog/package-blast-radius"

    assert cobra.version == "v1.10.2"
    assert cobra.local_src_path is None
    assert cobra.origin == "https://github.com/spf13/cobra"

    assert not any(m.name == SYNTHETIC_MODULE_NAME for m in result)

    mock_source_code_manager.get_code.assert_not_called()
    mock_output_from_command.assert_has_calls(
        [
            call(
                ["go", "list", "-json", "all"],
                cwd="/tmp/go-resolve/github_com_DataDog_package-blast-radius",
                env={"GOTOOLCHAIN": "auto"},
            ),
            call(
                ["go", "list", "-m", "-json", "all"],
                cwd="/tmp/go-resolve/github_com_DataDog_package-blast-radius",
                env={"GOTOOLCHAIN": "auto"},
            ),
        ]
    )


def test_gopkg_local_project_path_module_graph_fallback_only_root_project(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/DataDog/package-blast-radius",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/go-resolve/github_com_DataDog_package-blast-radius",
    )

    package_list_json = """
{
    "ImportPath": "ddla-go-resolve",
    "Module": {
        "Path": "%s",
        "Main": true,
        "Dir": "/tmp/go-resolve/github_com_DataDog_package-blast-radius"
    }
}""" % (SYNTHETIC_MODULE_NAME)

    module_graph_json = """
{
    "Path": "%s",
    "Main": true
}
{
    "Path": "github.com/DataDog/package-blast-radius",
    "Version": "v0.0.3"
}
{
    "Path": "github.com/spf13/cobra",
    "Version": "v1.10.2"
}""" % (SYNTHETIC_MODULE_NAME)

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[package_list_json, module_graph_json],
    )

    initial_metadata = [
        Metadata(
            name="github.com/DataDog/package-blast-radius",
            origin="github.com/DataDog/package-blast-radius",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Only the root module is kept in ONLY_ROOT_PROJECT scope
    assert len(result) == 1
    assert result[0].name == "github.com/DataDog/package-blast-radius"
    assert result[0].version == "v0.0.3"

    mock_source_code_manager.get_code.assert_not_called()
    mock_output_from_command.assert_has_calls(
        [
            call(
                ["go", "list", "-json", "all"],
                cwd="/tmp/go-resolve/github_com_DataDog_package-blast-radius",
                env={"GOTOOLCHAIN": "auto"},
            ),
            call(
                ["go", "list", "-m", "-json", "all"],
                cwd="/tmp/go-resolve/github_com_DataDog_package-blast-radius",
                env={"GOTOOLCHAIN": "auto"},
            ),
        ]
    )


def test_gopkg_local_project_path_module_graph_empty_output(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/DataDog/package-blast-radius",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/github_com_DataDog_package-blast-radius",
    )

    # Package listing only has the synthetic module; module graph is empty too
    package_list_json = """
{
    "ImportPath": "ddla-go-resolve",
    "Module": {
        "Path": "%s",
        "Main": true
    }
}""" % (SYNTHETIC_MODULE_NAME)

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[package_list_json, ""],
    )

    initial_metadata = [
        Metadata(
            name="github.com/DataDog/package-blast-radius",
            origin="github.com/DataDog/package-blast-radius",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    # Seed removed, no modules found via either listing
    assert len(result) == 0

    mock_source_code_manager.get_code.assert_not_called()
    mock_output_from_command.assert_has_calls(
        [
            call(
                ["go", "list", "-json", "all"],
                cwd="/tmp/go-resolve/github_com_DataDog_package-blast-radius",
                env={"GOTOOLCHAIN": "auto"},
            ),
            call(
                ["go", "list", "-m", "-json", "all"],
                cwd="/tmp/go-resolve/github_com_DataDog_package-blast-radius",
                env={"GOTOOLCHAIN": "auto"},
            ),
        ]
    )


def test_gopkg_resolves_vanity_imports_via_go_get_and_caches_exact_path(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Vanity Go module paths resolve via ?go-get=1 with redirect validation and exact-path caching."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/app",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/app",
    )
    deps_list_json = """
{
    "ImportPath": "k8s.io/api/core/v1",
    "Module": {
        "Path": "k8s.io/api",
        "Version": "v0.37.0"
    }
}
{
    "ImportPath": "go.opentelemetry.io/collector/component",
    "Module": {
        "Path": "go.opentelemetry.io/collector/component",
        "Version": "v1.52.0"
    }
}
{
    "ImportPath": "go.opentelemetry.io/collector/featuregate",
    "Module": {
        "Path": "go.opentelemetry.io/collector/featuregate",
        "Version": "v1.52.0"
    }
}
{
    "ImportPath": "sigs.k8s.io/controller-runtime/pkg/client",
    "Module": {
        "Path": "sigs.k8s.io/controller-runtime",
        "Version": "v0.25.2"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )
    k8s_html = (
        b"<html><head><!-- \xff -->"
        b'<meta name="GO-IMPORT" content="k8s.io/api\n  git https://GITHUB.COM/kubernetes/api.git">'
        b"</head><body>"
        b'<meta name="go-import" content="k8s.io/api git https://github.com/evil/in-body">'
        b"</body></html>"
    )
    otel_html = (
        b"<html><head>"
        b'<meta name="description" content="ignored">'
        b'<meta name="go-import" content="go.opentelemetry.io git https://github.com/open-telemetry/root">'
        b'<meta name="go-import" content="go.opentelemetry.io/collector git https://github.com/open-telemetry/opentelemetry-collector">'
        b'<meta name="go-import" content="go.opentelemetry.io git https://github.com/open-telemetry/shorter-later">'
        b'<meta name="go-import" content="go.opentelemetry.io/collector git https://github.com/open-telemetry/equal-later">'
        b"</head></html>"
    )
    sigs_html = (
        b"<html><head>"
        b'<meta name="go-import" content="only-two tokens">'
        b'<meta name="go-import" content="sigs.k8s.io/controller-runtime hg https://github.com/kubernetes-sigs/controller-runtime">'
        b'<meta name="go-import" content="other.example.com/pkg git https://github.com/other/repo">'
        b'<meta name="go-import" content="sigs.k8s.io/controller-runtime git https://go.googlesource.com/controller-runtime">'
        b'<meta name="go-import" content="sigs.k8s.io/controller-runtime git https://github.com/kubernetes-sigs/controller-runtime/">'
        b"</head></html>"
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.resolve_host_ips",
        return_value=["93.184.216.34"],
    )
    mock_download_bounded = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.download_bounded",
        side_effect=[k8s_html, otel_html, otel_html, otel_html, sigs_html],
    )

    initial_metadata = [
        Metadata(
            name="github.com/org/app",
            origin="github.com/org/app",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert [(m.name, m.origin) for m in result] == [
        ("k8s.io/api", "https://github.com/kubernetes/api"),
        (
            "go.opentelemetry.io/collector/component",
            "https://github.com/open-telemetry/opentelemetry-collector",
        ),
        (
            "go.opentelemetry.io/collector/featuregate",
            "https://github.com/open-telemetry/opentelemetry-collector",
        ),
        (
            "sigs.k8s.io/controller-runtime",
            "https://github.com/kubernetes-sigs/controller-runtime",
        ),
    ]
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/app",
        env={"GOTOOLCHAIN": "auto"},
    )
    # Non-exact prefix go.opentelemetry.io/collector is verified once at its authoritative URL
    assert [c.args for c in mock_download_bounded.call_args_list] == [
        ("https://k8s.io/api?go-get=1",),
        ("https://go.opentelemetry.io/collector/component?go-get=1",),
        ("https://go.opentelemetry.io/collector?go-get=1",),
        ("https://go.opentelemetry.io/collector/featuregate?go-get=1",),
        ("https://sigs.k8s.io/controller-runtime?go-get=1",),
    ]
    for c in mock_download_bounded.call_args_list:
        assert c.kwargs["max_bytes"] == 64 * 1024
        validator = c.kwargs["redirect_validator"]
        assert callable(validator)
        # Valid HTTPS redirect passes; SSRF/unsafe redirects raise ValueError
        validator("https://gomodules.xyz/jsonpatch/v2/?go-get=1")
        for bad_redirect, expected_msg in [
            ("http://127.0.0.1:8123/admin/reload", "Disallowed vanity URL"),
            ("https://169.254.169.254/latest/meta-data", "IP literal disallowed"),
            ("https://localhost/secret", "Disallowed vanity URL"),
            ("https://sub.localhost/secret", "Disallowed vanity URL"),
            ("https://user@example.com/pkg", "Disallowed vanity URL"),
            ("https://example.com:8443/pkg", "Explicit port disallowed"),
            ("https://[broken/pkg", "Invalid IPv6 URL"),
            ("https://example.com/bad url", "Disallowed whitespace"),
            ("https://%31%32%37.0.0.1/admin/reload", "Disallowed vanity URL"),
        ]:
            with pytest.raises(ValueError, match=expected_msg):
                validator(bad_redirect)
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()


def test_gopkg_vanity_import_checks_nested_modules_independently_and_handles_redirect_errors(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Parent module resolution must not shadow nested modules with distinct repos; redirect/network errors fall back and cache."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/app",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/app",
    )
    deps_list_json = """
{
    "ImportPath": "go.example.io/a",
    "Module": {"Path": "go.example.io/a", "Version": "v1.0.0"}
}
{
    "ImportPath": "go.example.io/a/b",
    "Module": {"Path": "go.example.io/a/b", "Version": "v1.0.0"}
}
{
    "ImportPath": "go.broken.io/x",
    "Module": {"Path": "go.broken.io/x", "Version": "v1.0.0"}
}
{
    "ImportPath": "go.ssrf.io/evil",
    "Module": {"Path": "go.ssrf.io/evil", "Version": "v1.0.0"}
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.resolve_host_ips",
        return_value=["93.184.216.34"],
    )
    mock_download_bounded = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.download_bounded",
        side_effect=[
            b'<meta name="go-import" content="go.example.io/a git https://github.com/example/root">',
            b'<meta name="go-import" content="go.example.io/a/b git https://github.com/Xexample/subX">',
            OSError("timeout"),
            ValueError("IP literal disallowed in vanity URL"),
        ],
    )
    initial_metadata = [
        Metadata(
            name="github.com/org/app",
            origin="github.com/org/app",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    with caplog.at_level(logging.DEBUG, logger="dd_license_attribution"):
        result = strategy.augment_metadata(initial_metadata)
        # Re-run to verify exact cache hits on both positive and negative entries
        result_again = strategy.augment_metadata(result)

    assert [(m.name, m.origin) for m in result_again] == [
        ("go.example.io/a", "https://github.com/example/root"),
        ("go.example.io/a/b", "https://github.com/Xexample/subX"),
        ("go.broken.io/x", "https://go.broken.io/x"),
        ("go.ssrf.io/evil", "https://go.ssrf.io/evil"),
    ]
    assert (
        "Could not resolve Go vanity import for go.broken.io/x: timeout"
        in caplog.messages
    )
    assert (
        "Could not resolve Go vanity import for go.ssrf.io/evil: IP literal disallowed in vanity URL"
        in caplog.messages
    )
    assert [c.args for c in mock_download_bounded.call_args_list] == [
        ("https://go.example.io/a?go-get=1",),
        ("https://go.example.io/a/b?go-get=1",),
        ("https://go.broken.io/x?go-get=1",),
        ("https://go.ssrf.io/evil?go-get=1",),
    ]
    expected_go_list_calls = [
        call(
            ["go", "list", "-json", "all"],
            cwd="/tmp/go-resolve/app",
            env={"GOTOOLCHAIN": "auto"},
        ),
        call(
            ["go", "list", "-json", "all"],
            cwd="/tmp/go-resolve/app",
            env={"GOTOOLCHAIN": "auto"},
        ),
    ]
    mock_output_from_command.assert_has_calls(expected_go_list_calls)
    assert mock_output_from_command.call_args_list == expected_go_list_calls
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()


def test_gopkg_vanity_import_rejects_unverified_non_exact_prefix_claim(
    mocker: pytest_mock.MockFixture,
) -> None:
    """A non-exact go-import prefix claim must match the authoritative prefix URL's ?go-get=1 response."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/app",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/app",
    )
    deps_list_json = """
{
    "ImportPath": "vanity.example/bob/pkg",
    "Module": {"Path": "vanity.example/bob/pkg", "Version": "v1.0.0"}
}
{
    "ImportPath": "vanity.example/alice/pkg",
    "Module": {"Path": "vanity.example/alice/pkg", "Version": "v1.0.0"}
}
{
    "ImportPath": "badhost.example/sub/pkg",
    "Module": {"Path": "badhost.example/sub/pkg", "Version": "v1.0.0"}
}
{
    "ImportPath": "shorter.example/sub/pkg",
    "Module": {"Path": "shorter.example/sub/pkg", "Version": "v1.0.0"}
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.resolve_host_ips",
        return_value=["93.184.216.34"],
    )
    mock_download_bounded = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.download_bounded",
        side_effect=[
            b'<meta name="go-import" content="vanity.example git https://github.com/bob/evil">',
            b'<meta name="go-import" content="vanity.example git https://github.com/real/repo">',
            b'<meta name="go-import" content="vanity.example git https://github.com/real/repo">',
            b'<meta name="go-import" content="badhost.example/sub git https://github.com/org/sub">',
            OSError("prefix unreachable"),
            b'<meta name="go-import" content="shorter.example/sub git https://github.com/org/sub">',
            b'<meta name="go-import" content="shorter.example git https://github.com/org/sub">',
        ],
    )
    initial_metadata = [
        Metadata(
            name="github.com/org/app",
            origin="github.com/org/app",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)
    # Re-run to verify rejected non-exact prefix claims are negative-cached as None
    result_again = strategy.augment_metadata(result)

    assert [(m.name, m.origin) for m in result_again] == [
        ("vanity.example/bob/pkg", "https://vanity.example/bob/pkg"),
        ("vanity.example/alice/pkg", "https://github.com/real/repo"),
        ("badhost.example/sub/pkg", "https://badhost.example/sub/pkg"),
        ("shorter.example/sub/pkg", "https://shorter.example/sub/pkg"),
    ]
    assert [c.args for c in mock_download_bounded.call_args_list] == [
        ("https://vanity.example/bob/pkg?go-get=1",),
        ("https://vanity.example?go-get=1",),
        ("https://vanity.example/alice/pkg?go-get=1",),
        ("https://badhost.example/sub/pkg?go-get=1",),
        ("https://badhost.example/sub?go-get=1",),
        ("https://shorter.example/sub/pkg?go-get=1",),
        ("https://shorter.example/sub?go-get=1",),
    ]
    expected_go_list_calls = [
        call(
            ["go", "list", "-json", "all"],
            cwd="/tmp/go-resolve/app",
            env={"GOTOOLCHAIN": "auto"},
        ),
        call(
            ["go", "list", "-json", "all"],
            cwd="/tmp/go-resolve/app",
            env={"GOTOOLCHAIN": "auto"},
        ),
    ]
    mock_output_from_command.assert_has_calls(expected_go_list_calls)
    assert mock_output_from_command.call_args_list == expected_go_list_calls
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()


def test_gopkg_vanity_prefix_cache_is_isolated_from_module_cache(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Prefix verification cache and module resolution cache must not interfere in either lookup order."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/app",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/app",
    )
    deps_list_json = """
{
    "ImportPath": "shorter.example/sub/pkg",
    "Module": {"Path": "shorter.example/sub/pkg", "Version": "v1.0.0"}
}
{
    "ImportPath": "shorter.example/sub",
    "Module": {"Path": "shorter.example/sub", "Version": "v1.0.0"}
}
{
    "ImportPath": "rev.example/sub",
    "Module": {"Path": "rev.example/sub", "Version": "v1.0.0"}
}
{
    "ImportPath": "rev.example/sub/pkg",
    "Module": {"Path": "rev.example/sub/pkg", "Version": "v1.0.0"}
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.resolve_host_ips",
        return_value=["93.184.216.34"],
    )
    mock_download_bounded = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.download_bounded",
        side_effect=[
            # 1. shorter.example/sub/pkg claims shorter.example/sub -> fails prefix check because /sub declares shorter.example
            b'<meta name="go-import" content="shorter.example/sub git https://github.com/org/sub">',
            b'<meta name="go-import" content="shorter.example git https://github.com/org/sub">',
            # 2. shorter.example/sub resolved as its own module -> must still fetch and succeed via shorter.example
            b'<meta name="go-import" content="shorter.example git https://github.com/org/sub">',
            b'<meta name="go-import" content="shorter.example git https://github.com/org/sub">',
            # 3. rev.example/sub resolved first -> succeeds via rev.example
            b'<meta name="go-import" content="rev.example git https://github.com/org/rev">',
            b'<meta name="go-import" content="rev.example git https://github.com/org/rev">',
            # 4. rev.example/sub/pkg claims rev.example/sub -> must still verify /sub (not reuse module cache) and reject
            b'<meta name="go-import" content="rev.example/sub git https://github.com/org/rev">',
            b'<meta name="go-import" content="rev.example git https://github.com/org/rev">',
        ],
    )
    initial_metadata = [
        Metadata(
            name="github.com/org/app",
            origin="github.com/org/app",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert [(m.name, m.origin) for m in result] == [
        ("shorter.example/sub/pkg", "https://shorter.example/sub/pkg"),
        ("shorter.example/sub", "https://github.com/org/sub"),
        ("rev.example/sub", "https://github.com/org/rev"),
        ("rev.example/sub/pkg", "https://rev.example/sub/pkg"),
    ]
    assert [c.args for c in mock_download_bounded.call_args_list] == [
        ("https://shorter.example/sub/pkg?go-get=1",),
        ("https://shorter.example/sub?go-get=1",),
        ("https://shorter.example/sub?go-get=1",),
        ("https://shorter.example?go-get=1",),
        ("https://rev.example/sub?go-get=1",),
        ("https://rev.example?go-get=1",),
        ("https://rev.example/sub/pkg?go-get=1",),
        ("https://rev.example/sub?go-get=1",),
    ]
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/app",
        env={"GOTOOLCHAIN": "auto"},
    )
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()


def test_gopkg_vanity_import_rejects_unsafe_paths_and_malformed_meta_tags(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unsafe/local module paths skip HTTP; non-GitHub, non-git, or malformed go-import tags fall back."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/app",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/app",
    )
    # Unsafe/unresolvable paths must not trigger any HTTP fetch
    unsafe_paths = [
        "",
        "k8s.io/api bad",
        "/leading-slash",
        "localhost/pkg",
        "sub.localhost/pkg",
        "localhost./pkg",
        "sub.localhost./pkg",
        "user@k8s.io/api",
        "k8s.io/api?x=1",
        "k8s.io/api#frag",
        "k8s.io:8080/api",
        "k8s.io:notaport/api",
        "127.0.0.1/pkg",
        "127.1/pkg",
        "0177.0.0.1/pkg",
        "0x7f.0x1/pkg",
        "bad..host/pkg",
        ".example.com/pkg",
        "example.com../pkg",
        "example.рф/pkg",
        "[::1]/pkg",
        "[broken/pkg",
    ]
    unsafe_deps_json = "\n".join(
        json.dumps(
            {"ImportPath": f"pkg/{i}", "Module": {"Path": path, "Version": "v1.0.0"}}
        )
        for i, path in enumerate(unsafe_paths)
    )
    # Malformed, non-git, non-GitHub, in-body, or unsafe repo_root tags must be rejected
    bad_meta_html = (
        b"<html><head>"
        b'<link name="go-import" content="vanity.example.com/pkg git https://github.com/evil/not-meta">'
        b'<meta content="vanity.example.com/pkg git https://github.com/evil/no-name">'
        b'<meta name content="vanity.example.com/pkg git https://github.com/evil/bool-name">'
        b'<meta name="go-import">'
        b'<meta name="go-import" content="">'
        b'<meta name="go-import" content="only-two tokens">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/org/repo extra">'
        b'<meta name="go-import" content="vanity.example.com/pkg hg https://github.com/org/repo">'
        b'<meta name="go-import" content="other.example.com/pkg git https://github.com/org/repo">'
        b'<meta name="go-import" content="vanity.example.com/pk git https://github.com/evil/partial-prefix">'
        b'<meta name="go-import" content="vanity.example.com/pkg git http://github.com/org/repo">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https:///org/repo">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://go.googlesource.com/repo">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://user@github.com/org/repo">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com:443/org/repo">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com:bad/org/repo">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/org/repo?q=1">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/org/repo#frag">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/only-owner">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/org/repo/extra">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/-flag/repo">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/org/-flag">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/./repo">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/org/.">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/../repo">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/org/..">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/org/.git">'
        b'<meta name="go-import" content="vanity.example.com/pkg git https://[broken/org/repo">'
        b"</head><main>"
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/evil/after-head">'
        b"</main><body>"
        b'<meta name="go-import" content="vanity.example.com/pkg git https://github.com/evil/in-body">'
        b"</body></html>"
    )
    vanity_dep_json = json.dumps(
        {
            "ImportPath": "vanity.example.com/pkg",
            "Module": {"Path": "vanity.example.com/pkg", "Version": "v1.0.0"},
        }
    )
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[unsafe_deps_json, vanity_dep_json, vanity_dep_json],
    )
    mock_resolve_host_ips = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.resolve_host_ips",
        return_value=["93.184.216.34"],
    )
    mock_download_bounded = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.download_bounded",
        return_value=bad_meta_html,
    )

    initial_metadata = [
        Metadata(
            name="github.com/org/app",
            origin="github.com/org/app",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]
    with caplog.at_level(logging.DEBUG, logger="dd_license_attribution"):
        unsafe_result = strategy.augment_metadata(initial_metadata)
    assert [(m.name, m.origin) for m in unsafe_result] == [
        (path, f"https://{path}") for path in unsafe_paths
    ]
    assert caplog.messages == []
    mock_resolve_host_ips.assert_not_called()
    mock_download_bounded.assert_not_called()

    # Fetch vanity.example.com/pkg once, reject all malformed tags, and negative-cache it
    vanity_result = strategy.augment_metadata(list(initial_metadata))
    vanity_result_cached = strategy.augment_metadata(vanity_result)
    assert [(m.name, m.origin) for m in vanity_result_cached] == [
        ("vanity.example.com/pkg", "https://vanity.example.com/pkg")
    ]
    assert [c.args for c in mock_download_bounded.call_args_list] == [
        ("https://vanity.example.com/pkg?go-get=1",)
    ]
    assert mock_download_bounded.call_args.kwargs["max_bytes"] == 64 * 1024
    assert callable(mock_download_bounded.call_args.kwargs["redirect_validator"])
    expected_go_list_calls = [
        call(
            ["go", "list", "-json", "all"],
            cwd="/tmp/go-resolve/app",
            env={"GOTOOLCHAIN": "auto"},
        ),
        call(
            ["go", "list", "-json", "all"],
            cwd="/tmp/go-resolve/app",
            env={"GOTOOLCHAIN": "auto"},
        ),
        call(
            ["go", "list", "-json", "all"],
            cwd="/tmp/go-resolve/app",
            env={"GOTOOLCHAIN": "auto"},
        ),
    ]
    mock_output_from_command.assert_has_calls(expected_go_list_calls)
    assert mock_output_from_command.call_args_list == expected_go_list_calls
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()


def test_gopkg_vanity_import_validates_resolved_ips_for_initial_and_redirect_urls(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Initial vanity hosts and redirect targets must resolve exclusively to public non-multicast IPs."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/app",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/app",
    )
    deps_list_json = "\n".join(
        json.dumps(
            {
                "ImportPath": f"{host}/pkg",
                "Module": {"Path": f"{host}/pkg", "Version": "v1.0.0"},
            }
        )
        for host in [
            "loopback.example",
            "private.example",
            "linklocal.example",
            "cgnat.example",
            "multicast.example",
            "mapped-loopback.example",
            "mixed.example",
            "empty.example",
            "garbage.example",
            "nxdomain.example",
            "mapped-public.example",
            "punycode.xn--p1ai",
            "bodyonly.example",
        ]
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )
    ip_map: dict[str, list[str] | Exception] = {
        "loopback.example": ["127.0.0.1"],
        "private.example": ["10.0.0.5"],
        "linklocal.example": ["169.254.169.254"],
        "cgnat.example": ["100.64.0.1"],
        "multicast.example": ["224.0.0.1"],
        "mapped-loopback.example": ["::ffff:127.0.0.1"],
        "mixed.example": ["93.184.216.34", "192.168.1.1"],
        "empty.example": [],
        "garbage.example": ["not-an-ip"],
        "nxdomain.example": OSError("Failed to resolve host nxdomain.example"),
        "mapped-public.example": ["::ffff:93.184.216.34"],
        "punycode.xn--p1ai": ["2606:2800:220:1::1"],
        "bodyonly.example": ["93.184.216.34"],
        "redirect-private.example": ["10.1.2.3"],
        "redirect-public.example": ["93.184.216.34"],
        "redirect-public.example.": ["93.184.216.34"],
    }

    def fake_resolve(hostname: str) -> list[str]:
        entry = ip_map[hostname]
        if isinstance(entry, Exception):
            raise entry
        return entry

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.resolve_host_ips",
        side_effect=fake_resolve,
    )
    captured_validators: list[object] = []

    def fake_download(
        url: str,
        *,
        max_bytes: int,
        redirect_validator: object = None,
    ) -> bytes:
        captured_validators.append(redirect_validator)
        if url == "https://mapped-public.example/pkg?go-get=1":
            return b'<meta name="go-import" content="mapped-public.example/pkg git https://github.com/org/mapped">'
        if url == "https://punycode.xn--p1ai/pkg?go-get=1":
            return b'<meta name="go-import" content="punycode.xn--p1ai/pkg git https://github.com/org/puny">'
        # HTML with <body> but no </head> verifies handle_starttag("body") independently of handle_endtag("head")
        return (
            b"<html><body>"
            b'<meta name="go-import" content="bodyonly.example/pkg git https://github.com/evil/body-only">'
            b"</body></html>"
        )

    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.download_bounded",
        side_effect=fake_download,
    )

    result = strategy.augment_metadata(
        [
            Metadata(
                name="github.com/org/app",
                origin="github.com/org/app",
                local_src_path=None,
                license=[],
                version=None,
                copyright=[],
            )
        ]
    )
    origins = {m.name: m.origin for m in result}
    assert origins["mapped-public.example/pkg"] == "https://github.com/org/mapped"
    assert origins["punycode.xn--p1ai/pkg"] == "https://github.com/org/puny"
    assert origins["bodyonly.example/pkg"] == "https://bodyonly.example/pkg"
    for rejected_host in [
        "loopback.example",
        "private.example",
        "linklocal.example",
        "cgnat.example",
        "multicast.example",
        "mapped-loopback.example",
        "mixed.example",
        "empty.example",
        "garbage.example",
        "nxdomain.example",
    ]:
        assert origins[f"{rejected_host}/pkg"] == f"https://{rejected_host}/pkg"

    # Only the 3 hosts resolving to public IPs reached download_bounded
    assert [c.args for c in mock_download.call_args_list] == [
        ("https://mapped-public.example/pkg?go-get=1",),
        ("https://punycode.xn--p1ai/pkg?go-get=1",),
        ("https://bodyonly.example/pkg?go-get=1",),
    ]
    # Verify the redirect validator itself blocks private-IP redirects and numeric aliases
    validator = captured_validators[0]
    assert callable(validator)
    validator("https://redirect-public.example/pkg?go-get=1")
    validator("https://redirect-public.example./pkg?go-get=1")
    with pytest.raises(ValueError, match="Non-public resolved IP"):
        validator("https://redirect-private.example/pkg?go-get=1")
    with pytest.raises(ValueError, match="Numeric or non-public host"):
        validator("https://127.1/pkg?go-get=1")
    with pytest.raises(ValueError, match="Numeric or non-public host"):
        validator("https://0177.0.0.1/pkg?go-get=1")


_SINGLE_MODULE_GO_LIST_OUTPUT = """
{
    "ImportPath": "github.com/org/package1/v2",
    "Module": {
        "Path": "github.com/org/package1/v2",
        "Main": true,
        "Dir": "cache_dir/org_package1"
    }
}
{
    "ImportPath": "github.com/org/package4",
    "Module": {
        "Path": "github.com/org/package4",
        "Version": "v1.2.3",
        "Dir": "/tmp/go/pkg/mod/github.com/org/package4@v1.2.3"
    }
}
{
    "ImportPath": "bytes",
    "Standard": true
}"""


def _single_module_strategy(
    mocker: pytest_mock.MockFixture, project_scope: ProjectScope
) -> tuple[GoPkgMetadataCollectionStrategy, pytest_mock.MockType]:
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/org/package1",
        None,
    )
    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/package1",
        branch="main",
        local_root_path="cache_dir/org_package1",
        local_full_path="cache_dir/org_package1",
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/org/package1",
        mock_source_code_manager,
        project_scope,
        single_module=True,
    )
    return strategy, mock_source_code_manager


def test_gopkg_single_module_lists_only_the_root_module_without_workspace(
    mocker: pytest_mock.MockFixture,
) -> None:
    strategy, mock_source_code_manager = _single_module_strategy(
        mocker, ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES
    )
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory"
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.path_exists",
        return_value=True,
    )
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=_SINGLE_MODULE_GO_LIST_OUTPUT,
    )

    result = strategy.augment_metadata([])

    # The main module itself is not a transitive dependency.
    assert result == [
        Metadata(
            name="github.com/org/package4",
            origin="https://github.com/org/package4",
            local_src_path="/tmp/go/pkg/mod/github.com/org/package4@v1.2.3",
            license=[],
            version="v1.2.3",
            copyright=[],
        ),
    ]
    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/package1"
    )
    mock_walk_directory.assert_not_called()
    mock_path_exists.assert_called_once_with("cache_dir/org_package1/go.mod")
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="cache_dir/org_package1",
        env={"GOTOOLCHAIN": "auto", "GOWORK": "off"},
    )


def test_gopkg_single_module_keeps_the_main_module_when_not_transitive_only(
    mocker: pytest_mock.MockFixture,
) -> None:
    strategy, _ = _single_module_strategy(mocker, ProjectScope.ALL)
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.path_exists",
        return_value=True,
    )
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[
            _SINGLE_MODULE_GO_LIST_OUTPUT,
            "ref: refs/heads/main\tHEAD\n72a11341aa684010caf1ca5dee779f0e7e84dfe9\tHEAD\n",
        ],
    )

    result = strategy.augment_metadata([])

    assert [m.name for m in result] == [
        "github.com/org/package1/v2",
        "github.com/org/package4",
    ]
    assert result[0].origin == "https://github.com/org/package1/tree/main/v2"
    assert mock_output_from_command.call_args_list == [
        call(
            ["go", "list", "-json", "all"],
            cwd="cache_dir/org_package1",
            env={"GOTOOLCHAIN": "auto", "GOWORK": "off"},
        ),
        call(
            [
                "git",
                "ls-remote",
                "--symref",
                "https://github.com/org/package1",
                "HEAD",
            ]
        ),
    ]


def test_gopkg_single_module_only_root_project_updates_known_entries_only(
    mocker: pytest_mock.MockFixture,
) -> None:
    strategy, _ = _single_module_strategy(mocker, ProjectScope.ONLY_ROOT_PROJECT)
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.path_exists",
        return_value=True,
    )
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=_SINGLE_MODULE_GO_LIST_OUTPUT,
    )
    root = Metadata(
        name="github.com/org/package4",
        origin=None,
        local_src_path=None,
        license=[],
        version=None,
        copyright=[],
    )

    result = strategy.augment_metadata([root])

    assert result == [
        Metadata(
            name="github.com/org/package4",
            origin="https://github.com/org/package4",
            local_src_path="/tmp/go/pkg/mod/github.com/org/package4@v1.2.3",
            license=[],
            version="v1.2.3",
            copyright=[],
        )
    ]
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="cache_dir/org_package1",
        env={"GOTOOLCHAIN": "auto", "GOWORK": "off"},
    )


def test_gopkg_single_module_without_root_go_mod_skips_collection(
    mocker: pytest_mock.MockFixture,
) -> None:
    strategy, _ = _single_module_strategy(
        mocker, ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.path_exists",
        return_value=False,
    )
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command"
    )
    mock_logger = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.logger"
    )
    initial_metadata = [
        Metadata(
            name="package2",
            origin="package2_origin",
            local_src_path=None,
            license=["MIT"],
            version="1.2",
            copyright=[],
        )
    ]

    result = strategy.augment_metadata(list(initial_metadata))

    assert result == initial_metadata
    mock_path_exists.assert_called_once_with("cache_dir/org_package1/go.mod")
    mock_output_from_command.assert_not_called()
    mock_logger.warning.assert_called_once_with(
        "Single Go module mode: no go.mod in %s, skipping Go module collection.",
        "cache_dir/org_package1",
    )
