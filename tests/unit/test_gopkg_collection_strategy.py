# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from unittest.mock import call

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
        deps_list_json_3,
        branch_detection_output,
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
                ["go", "list", "-json", "all"],
                cwd="org_package1/package3",
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
            deps_list_json_src,
            branch_detection_output,
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
                ["go", "list", "-json", "all"],
                cwd="org_package1/src",
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


def test_gopkg_collection_strategy_merges_case_insensitive_sbom_entries(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Lowercase and mixed-case SBOM entries must merge with canonical go list paths."""
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/DataDog/my-repo",
        None,
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/DataDog/my-repo",
        mock_source_code_manager,
        ProjectScope.ALL,
    )

    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/DataDog/my-repo",
        branch="main",
        local_root_path="cache_dir/DataDog_my-repo",
        local_full_path="cache_dir/DataDog_my-repo",
    )
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory",
        return_value=[("my-repo", [], ["go.mod"])],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.open_file",
        return_value="module github.com/DataDog/my-repo",
    )

    deps_list_json = """
{
    "ImportPath": "github.com/DataDog/dd-trace-go/v2/ddtrace",
    "Module": {
        "Path": "github.com/DataDog/dd-trace-go/v2",
        "Version": "v2.8.2",
        "Dir": "/go/pkg/mod/github.com/!data!dog/dd-trace-go/v2@v2.8.2"
    }
}
{
    "ImportPath": "github.com/DataDog/datadog-go/statsd",
    "Module": {
        "Path": "github.com/DataDog/datadog-go",
        "Version": "v4.8.3",
        "Dir": "/go/pkg/mod/github.com/!data!dog/datadog-go@v4.8.3"
    }
}"""

    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[deps_list_json, "ref: refs/heads/main\tHEAD"],
    )

    initial_metadata = [
        Metadata(
            name=None,
            origin="https://example.com/nameless",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="github.com/datadog/dd-trace-go/v2",
            origin="https://github.com/datadog/dd-trace-go/v2",
            local_src_path=None,
            license=["Apache-2.0"],
            version="v2.8.2",
            copyright=["Datadog, Inc."],
        ),
        Metadata(
            name="github.com/DATADOG/datadog-go",
            origin="https://github.com/DATADOG/datadog-go",
            local_src_path=None,
            license=["MIT"],
            version="v4.8.3",
            copyright=["Datadog, Inc."],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert len(result) == 3
    merged_trace = result[1]
    assert merged_trace.name == "github.com/DataDog/dd-trace-go/v2"
    assert merged_trace.origin == "https://github.com/DataDog/dd-trace-go/tree/main/v2"
    assert (
        merged_trace.local_src_path
        == "/go/pkg/mod/github.com/!data!dog/dd-trace-go/v2@v2.8.2"
    )
    assert merged_trace.version == "v2.8.2"
    assert merged_trace.license == ["Apache-2.0"]
    assert merged_trace.copyright == ["Datadog, Inc."]

    merged_statsd = result[2]
    assert merged_statsd.name == "github.com/DataDog/datadog-go"
    assert merged_statsd.origin == "https://github.com/DataDog/datadog-go"
    assert (
        merged_statsd.local_src_path
        == "/go/pkg/mod/github.com/!data!dog/datadog-go@v4.8.3"
    )
    assert merged_statsd.version == "v4.8.3"
    assert merged_statsd.license == ["MIT"]
    assert merged_statsd.copyright == ["Datadog, Inc."]

    mock_source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/DataDog/my-repo"
    )
    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/DataDog/my-repo"
    )
    mock_walk_directory.assert_called_once_with("cache_dir/DataDog_my-repo")
    mock_open_file.assert_called_once_with("my-repo/go.mod")
    mock_output_from_command.assert_has_calls(
        [
            call(
                ["go", "list", "-json", "all"],
                cwd="my-repo",
                env={"GOTOOLCHAIN": "auto"},
            ),
            call(
                [
                    "git",
                    "ls-remote",
                    "--symref",
                    "https://github.com/DataDog/dd-trace-go",
                    "HEAD",
                ]
            ),
        ]
    )


def test_gopkg_only_root_project_matches_case_insensitively(
    mocker: pytest_mock.MockFixture,
) -> None:
    """ONLY_ROOT_PROJECT matches root metadata regardless of module path casing."""
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/DataDog/my-repo",
        None,
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/DataDog/my-repo",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
    )
    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/DataDog/my-repo",
        branch="main",
        local_root_path="cache_dir/DataDog_my-repo",
        local_full_path="cache_dir/DataDog_my-repo",
    )
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory",
        return_value=[("my-repo", [], ["go.mod"])],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.open_file",
        return_value="module github.com/DataDog/my-repo",
    )
    deps_list_json = """
{
    "ImportPath": "github.com/other/dep",
    "Module": {
        "Path": "github.com/other/dep",
        "Version": "v0.1.0",
        "Dir": "/cache/other/dep"
    }
}
{
    "ImportPath": "github.com/DataDog/my-repo",
    "Module": {
        "Path": "github.com/DataDog/my-repo",
        "Version": "v1.0.0",
        "Dir": "/cache/DataDog/my-repo"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )

    initial_metadata = [
        Metadata(
            name=None,
            origin="https://example.com/nameless",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="github.com/Datadog/my-repo",
            origin="https://github.com/Datadog/my-repo",
            local_src_path=None,
            license=["Apache-2.0"],
            version=None,
            copyright=["Datadog, Inc."],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert len(result) == 2
    assert result[1].name == "github.com/DataDog/my-repo"
    assert result[1].origin == "https://github.com/DataDog/my-repo"
    assert result[1].local_src_path == "/cache/DataDog/my-repo"
    assert result[1].version == "v1.0.0"
    mock_source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/DataDog/my-repo"
    )
    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/DataDog/my-repo"
    )
    mock_walk_directory.assert_called_once_with("cache_dir/DataDog_my-repo")
    mock_open_file.assert_called_once_with("my-repo/go.mod")
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="my-repo",
        env={"GOTOOLCHAIN": "auto"},
    )


def test_gopkg_local_project_path_only_root_project_matches_case_insensitively(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Local-project ONLY_ROOT_PROJECT matches mixed-case module paths case-insensitively."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/Datadog/my-lib/subpkg@v1.2.0",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/go-resolve/my-lib",
    )
    deps_list_json = """
{
    "ImportPath": "github.com/other/dep",
    "Module": {
        "Path": "github.com/other/dep",
        "Version": "v0.1.0",
        "Dir": "/go/pkg/mod/github.com/other/dep@v0.1.0"
    }
}
{
    "ImportPath": "github.com/DataDog/my-lib/subpkg",
    "Module": {
        "Path": "github.com/DataDog/my-lib",
        "Version": "v1.2.0",
        "Dir": "/go/pkg/mod/github.com/!data!dog/my-lib@v1.2.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )
    initial_metadata = [
        Metadata(
            name="github.com/Datadog/my-lib/subpkg@v1.2.0",
            origin="github.com/Datadog/my-lib/subpkg@v1.2.0",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert len(result) == 1
    assert result[0].name == "github.com/DataDog/my-lib"
    assert result[0].version == "v1.2.0"
    mock_source_code_manager.get_canonical_urls.assert_not_called()
    mock_source_code_manager.get_code.assert_not_called()
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/my-lib",
        env={"GOTOOLCHAIN": "auto"},
    )


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
        side_effect=[
            _SINGLE_MODULE_GO_LIST_OUTPUT,
            "ref: refs/heads/main\tHEAD\n72a11341aa684010caf1ca5dee779f0e7e84dfe9\tHEAD\n",
            _SINGLE_MODULE_GO_LIST_OUTPUT,
        ],
    )
    root = Metadata(
        name="github.com/org/package1/v2",
        origin=None,
        local_src_path=None,
        license=[],
        version=None,
        copyright=[],
    )

    result = strategy.augment_metadata([root])

    assert result == [
        Metadata(
            name="github.com/org/package1/v2",
            origin="https://github.com/org/package1/tree/main/v2",
            local_src_path="cache_dir/org_package1",
            license=[],
            version=None,
            copyright=[],
        )
    ]

    # A Main module that does not match any known metadata entry is not added.
    unrelated = Metadata(
        name="github.com/org/unrelated",
        origin=None,
        local_src_path=None,
        license=[],
        version=None,
        copyright=[],
    )
    assert strategy.augment_metadata([unrelated]) == [unrelated]
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
        call(
            ["go", "list", "-json", "all"],
            cwd="cache_dir/org_package1",
            env={"GOTOOLCHAIN": "auto", "GOWORK": "off"},
        ),
    ]


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


def test_gopkg_local_project_path_only_root_project_preserves_uppercase_subpackage(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Uppercase subpackage dirs like V2 must not be mistaken for a lowercase /v2 module boundary."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "example.com/lib/V2/client",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/go-resolve/lib",
    )
    deps_list_json = """
{
    "ImportPath": "example.com/lib/V2/client",
    "Module": {
        "Path": "example.com/lib",
        "Version": "v1.4.0",
        "Dir": "/go/pkg/mod/example.com/lib@v1.4.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )
    initial_metadata = [
        Metadata(
            name="example.com/lib/V2/client",
            origin="example.com/lib/V2/client",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert len(result) == 1
    assert result[0].name == "example.com/lib"
    assert result[0].version == "v1.4.0"
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/lib",
        env={"GOTOOLCHAIN": "auto"},
    )


def test_gopkg_keeps_distinct_go_modules_differing_only_by_case(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Separate go.mod files reporting example.com/Foo and example.com/foo keep distinct entries."""
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/org/mono",
        None,
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/org/mono",
        mock_source_code_manager,
        ProjectScope.ALL,
    )
    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/mono",
        branch="main",
        local_root_path="cache_dir/org_mono",
        local_full_path="cache_dir/org_mono",
    )
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory",
        return_value=[("mono/a", [], ["go.mod"]), ("mono/b", [], ["go.mod"])],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.open_file",
        side_effect=["module example.com/a", "module example.com/b"],
    )
    go_list_a = """
{
    "ImportPath": "example.com/Foo",
    "Module": {
        "Path": "example.com/Foo",
        "Version": "v1.0.0",
        "Dir": "/go/pkg/mod/example.com/!foo@v1.0.0"
    }
}"""
    go_list_b = """
{
    "ImportPath": "example.com/foo",
    "Module": {
        "Path": "example.com/foo",
        "Version": "v2.0.0",
        "Dir": "/go/pkg/mod/example.com/foo@v2.0.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[go_list_a, go_list_b],
    )

    result = strategy.augment_metadata([])

    assert [(m.name, m.version, m.local_src_path) for m in result] == [
        ("example.com/Foo", "v1.0.0", "/go/pkg/mod/example.com/!foo@v1.0.0"),
        ("example.com/foo", "v2.0.0", "/go/pkg/mod/example.com/foo@v2.0.0"),
    ]
    mock_source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/org/mono"
    )
    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/mono"
    )
    mock_walk_directory.assert_called_once_with("cache_dir/org_mono")
    mock_open_file.assert_has_calls([call("mono/a/go.mod"), call("mono/b/go.mod")])
    mock_output_from_command.assert_has_calls(
        [
            call(
                ["go", "list", "-json", "all"],
                cwd="mono/a",
                env={"GOTOOLCHAIN": "auto"},
            ),
            call(
                ["go", "list", "-json", "all"],
                cwd="mono/b",
                env={"GOTOOLCHAIN": "auto"},
            ),
        ]
    )


def test_gopkg_clears_stale_attribution_when_case_insensitive_match_differs_on_version(
    mocker: pytest_mock.MockFixture,
) -> None:
    """When a case-insensitive SBOM alias has a different version than go list, clear stale license/copyright."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/app",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/app",
    )
    deps_list_json = """
{
    "ImportPath": "github.com/DataDog/lib",
    "Module": {
        "Path": "github.com/DataDog/lib",
        "Version": "v1.2.0",
        "Dir": "/go/pkg/mod/github.com/!data!dog/lib@v1.2.0"
    }
}
{
    "ImportPath": "github.com/DataDog/same",
    "Module": {
        "Path": "github.com/DataDog/same",
        "Version": "v2.0.0",
        "Dir": "/go/pkg/mod/github.com/!data!dog/same@v2.0.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
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
        Metadata(
            name="github.com/datadog/lib",
            origin="https://github.com/datadog/lib",
            local_src_path=None,
            license=["MIT"],
            version="v1.1.0",
            copyright=["Old Holder"],
        ),
        Metadata(
            name="github.com/datadog/same",
            origin="https://github.com/datadog/same",
            local_src_path=None,
            license=["Apache-2.0"],
            version="v2.0.0",
            copyright=["Datadog, Inc."],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert len(result) == 2
    assert result[0].name == "github.com/DataDog/lib"
    assert result[0].version == "v1.2.0"
    assert result[0].license == []
    assert result[0].copyright == []
    assert result[1].name == "github.com/DataDog/same"
    assert result[1].version == "v2.0.0"
    assert result[1].license == ["Apache-2.0"]
    assert result[1].copyright == ["Datadog, Inc."]
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/app",
        env={"GOTOOLCHAIN": "auto"},
    )


def test_gopkg_single_module_only_root_project_matches_main_case_insensitively_and_excludes_case_only_dep(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Single-module ONLY_ROOT_PROJECT matches the Main module case-insensitively and excludes case-only deps."""
    strategy, _ = _single_module_strategy(mocker, ProjectScope.ONLY_ROOT_PROJECT)
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.path_exists",
        return_value=True,
    )
    single_module_with_case_dep = """
{
    "ImportPath": "github.com/org/repo/client",
    "Module": {
        "Path": "github.com/org/repo",
        "Version": "v1.0.0",
        "Dir": "/tmp/go/pkg/mod/github.com/org/repo@v1.0.0"
    }
}
{
    "ImportPath": "github.com/org/Repo",
    "Module": {
        "Path": "github.com/org/Repo",
        "Main": true,
        "Dir": "cache_dir/org_package1"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=single_module_with_case_dep,
    )
    nameless = Metadata(
        name=None,
        origin="https://example.com/nameless",
        local_src_path=None,
        license=[],
        version=None,
        copyright=[],
    )
    root = Metadata(
        name="github.com/org/repo",
        origin="https://github.com/org/repo",
        local_src_path=None,
        license=["Apache-2.0"],
        version=None,
        copyright=["Org, Inc."],
    )

    result = strategy.augment_metadata([nameless, root])

    assert result == [
        nameless,
        Metadata(
            name="github.com/org/Repo",
            origin="https://github.com/org/Repo",
            local_src_path="cache_dir/org_package1",
            license=["Apache-2.0"],
            version=None,
            copyright=["Org, Inc."],
        ),
    ]
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="cache_dir/org_package1",
        env={"GOTOOLCHAIN": "auto", "GOWORK": "off"},
    )


def test_gopkg_preserves_existing_version_when_go_list_omits_version(
    mocker: pytest_mock.MockFixture,
) -> None:
    """When go list omits Version (e.g. main module), both exact and case-insensitive matches preserve existing version."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/app",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/app",
    )
    deps_list_json = """
{
    "ImportPath": "github.com/DataDog/exact-mod",
    "Module": {
        "Path": "github.com/DataDog/exact-mod",
        "Main": true,
        "Dir": "/cache/exact-mod"
    }
}
{
    "ImportPath": "github.com/DataDog/alias-mod",
    "Module": {
        "Path": "github.com/DataDog/alias-mod",
        "Main": true,
        "Dir": "/cache/alias-mod"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
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
        Metadata(
            name="github.com/DataDog/exact-mod",
            origin="https://github.com/DataDog/exact-mod",
            local_src_path=None,
            license=["Apache-2.0"],
            version="v1.0.0",
            copyright=["Datadog, Inc."],
        ),
        Metadata(
            name="github.com/datadog/alias-mod",
            origin="https://github.com/datadog/alias-mod",
            local_src_path=None,
            license=["MIT"],
            version="v2.1.0",
            copyright=["Datadog, Inc."],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert len(result) == 2
    assert result[0] == Metadata(
        name="github.com/DataDog/exact-mod",
        origin="https://github.com/DataDog/exact-mod",
        local_src_path="/cache/exact-mod",
        license=["Apache-2.0"],
        version="v1.0.0",
        copyright=["Datadog, Inc."],
    )
    assert result[1] == Metadata(
        name="github.com/DataDog/alias-mod",
        origin="https://github.com/DataDog/alias-mod",
        local_src_path="/cache/alias-mod",
        license=["MIT"],
        version="v2.1.0",
        copyright=["Datadog, Inc."],
    )
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/app",
        env={"GOTOOLCHAIN": "auto"},
    )


def test_gopkg_keeps_distinct_go_modules_after_exact_and_case_insensitive_matches(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Modules matched via exact or case-insensitive SBOM merge are marked Go-discovered and not overwritten by case variants."""
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/org/mono",
        None,
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/org/mono",
        mock_source_code_manager,
        ProjectScope.ALL,
    )
    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/mono",
        branch="main",
        local_root_path="cache_dir/org_mono",
        local_full_path="cache_dir/org_mono",
    )
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory",
        return_value=[("mono/a", [], ["go.mod"]), ("mono/b", [], ["go.mod"])],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.open_file",
        side_effect=["module example.com/a", "module example.com/b"],
    )
    go_list_a = """
{
    "ImportPath": "example.com/foo",
    "Module": {
        "Path": "example.com/foo",
        "Version": "v1.0.0",
        "Dir": "/go/pkg/mod/example.com/foo@v1.0.0"
    }
}
{
    "ImportPath": "example.com/Bar",
    "Module": {
        "Path": "example.com/Bar",
        "Version": "v1.1.0",
        "Dir": "/go/pkg/mod/example.com/!bar@v1.1.0"
    }
}"""
    go_list_b = """
{
    "ImportPath": "example.com/Foo",
    "Module": {
        "Path": "example.com/Foo",
        "Version": "v2.0.0",
        "Dir": "/go/pkg/mod/example.com/!foo@v2.0.0"
    }
}
{
    "ImportPath": "example.com/bar",
    "Module": {
        "Path": "example.com/bar",
        "Version": "v2.1.0",
        "Dir": "/go/pkg/mod/example.com/bar@v2.1.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[go_list_a, go_list_b],
    )
    initial_metadata = [
        Metadata(
            name="example.com/foo",
            origin="https://example.com/foo",
            local_src_path=None,
            license=["MIT"],
            version="v1.0.0",
            copyright=["Foo Inc."],
        ),
        Metadata(
            name="example.com/BAR",
            origin="https://example.com/BAR",
            local_src_path=None,
            license=["Apache-2.0"],
            version="v1.1.0",
            copyright=["Bar Inc."],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert [(m.name, m.version, m.local_src_path, m.license) for m in result] == [
        ("example.com/foo", "v1.0.0", "/go/pkg/mod/example.com/foo@v1.0.0", ["MIT"]),
        (
            "example.com/Bar",
            "v1.1.0",
            "/go/pkg/mod/example.com/!bar@v1.1.0",
            ["Apache-2.0"],
        ),
        ("example.com/Foo", "v2.0.0", "/go/pkg/mod/example.com/!foo@v2.0.0", []),
        ("example.com/bar", "v2.1.0", "/go/pkg/mod/example.com/bar@v2.1.0", []),
    ]
    mock_source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/org/mono"
    )
    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/mono"
    )
    mock_walk_directory.assert_called_once_with("cache_dir/org_mono")
    mock_open_file.assert_has_calls([call("mono/a/go.mod"), call("mono/b/go.mod")])
    mock_output_from_command.assert_has_calls(
        [
            call(
                ["go", "list", "-json", "all"],
                cwd="mono/a",
                env={"GOTOOLCHAIN": "auto"},
            ),
            call(
                ["go", "list", "-json", "all"],
                cwd="mono/b",
                env={"GOTOOLCHAIN": "auto"},
            ),
        ]
    )


def test_gopkg_reserves_exact_matches_before_consuming_case_insensitive_aliases(
    mocker: pytest_mock.MockFixture,
) -> None:
    """When go list reports example.com/Foo before example.com/foo and SBOM already has example.com/foo,
    example.com/Foo must not steal example.com/foo's SBOM license and copyright."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/org/app",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/app",
    )
    deps_list_json = """
{
    "ImportPath": "example.com/Foo",
    "Module": {
        "Path": "example.com/Foo",
        "Version": "v1.0.0",
        "Dir": "/go/pkg/mod/example.com/!foo@v1.0.0"
    }
}
{
    "ImportPath": "example.com/foo",
    "Module": {
        "Path": "example.com/foo",
        "Version": "v1.0.0",
        "Dir": "/go/pkg/mod/example.com/foo@v1.0.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
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
        Metadata(
            name="example.com/foo",
            origin="https://example.com/foo",
            local_src_path=None,
            license=["MIT"],
            version="v1.0.0",
            copyright=["Foo Lower Authors"],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    by_name = {m.name: m for m in result}
    assert len(result) == 2
    assert by_name["example.com/foo"].license == ["MIT"]
    assert by_name["example.com/foo"].copyright == ["Foo Lower Authors"]
    assert (
        by_name["example.com/foo"].local_src_path
        == "/go/pkg/mod/example.com/foo@v1.0.0"
    )
    assert by_name["example.com/Foo"].license == []
    assert by_name["example.com/Foo"].copyright == []
    assert (
        by_name["example.com/Foo"].local_src_path
        == "/go/pkg/mod/example.com/!foo@v1.0.0"
    )
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/app",
        env={"GOTOOLCHAIN": "auto"},
    )


def test_gopkg_reserves_exact_matches_across_multiple_go_mod_files(
    mocker: pytest_mock.MockFixture,
) -> None:
    """When one go.mod lists example.com/Foo and a later go.mod lists example.com/foo while SBOM has example.com/foo,
    example.com/Foo must not consume example.com/foo's SBOM attribution."""
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/org/mono",
        None,
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/org/mono",
        mock_source_code_manager,
        ProjectScope.ALL,
    )
    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/mono",
        branch="main",
        local_root_path="cache_dir/org_mono",
        local_full_path="cache_dir/org_mono",
    )
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory",
        return_value=[("mono/a", [], ["go.mod"]), ("mono/b", [], ["go.mod"])],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.open_file",
        side_effect=["module example.com/a", "module example.com/b"],
    )
    go_list_a = """
{
    "ImportPath": "example.com/Foo",
    "Module": {
        "Path": "example.com/Foo",
        "Version": "v1.0.0",
        "Dir": "/go/pkg/mod/example.com/!foo@v1.0.0"
    }
}"""
    go_list_b = """
{
    "ImportPath": "example.com/foo",
    "Module": {
        "Path": "example.com/foo",
        "Version": "v1.0.0",
        "Dir": "/go/pkg/mod/example.com/foo@v1.0.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[go_list_a, go_list_b],
    )
    initial_metadata = [
        Metadata(
            name="example.com/foo",
            origin="https://example.com/foo",
            local_src_path=None,
            license=["MIT"],
            version="v1.0.0",
            copyright=["Foo Lower Authors"],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    by_name = {m.name: m for m in result}
    assert len(result) == 2
    assert by_name["example.com/foo"].license == ["MIT"]
    assert by_name["example.com/foo"].copyright == ["Foo Lower Authors"]
    assert (
        by_name["example.com/foo"].local_src_path
        == "/go/pkg/mod/example.com/foo@v1.0.0"
    )
    assert by_name["example.com/Foo"].license == []
    assert by_name["example.com/Foo"].copyright == []
    assert (
        by_name["example.com/Foo"].local_src_path
        == "/go/pkg/mod/example.com/!foo@v1.0.0"
    )
    mock_source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/org/mono"
    )
    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/mono"
    )
    mock_walk_directory.assert_called_once_with("cache_dir/org_mono")
    mock_open_file.assert_has_calls([call("mono/a/go.mod"), call("mono/b/go.mod")])
    mock_output_from_command.assert_has_calls(
        [
            call(
                ["go", "list", "-json", "all"],
                cwd="mono/a",
                env={"GOTOOLCHAIN": "auto"},
            ),
            call(
                ["go", "list", "-json", "all"],
                cwd="mono/b",
                env={"GOTOOLCHAIN": "auto"},
            ),
        ]
    )


def test_gopkg_local_project_path_only_root_project_prefers_case_sensitive_ownership(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Root-only local scans prefer case-sensitive module ownership over case-insensitive fallback."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "example.com/lib/V2/client",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/go-resolve/lib",
    )
    deps_list_json = """
{
    "ImportPath": "example.com/lib/V2/client",
    "Module": {
        "Path": "example.com/lib",
        "Version": "v1.4.0",
        "Dir": "/go/pkg/mod/example.com/lib@v1.4.0"
    }
}
{
    "ImportPath": "example.com/lib/v2/helper",
    "Module": {
        "Path": "example.com/lib/v2",
        "Version": "v2.1.0",
        "Dir": "/go/pkg/mod/example.com/lib/v2@v2.1.0"
    }
}
{
    "ImportPath": "example.com/Lib/util",
    "Module": {
        "Path": "example.com/Lib",
        "Version": "v1.0.0",
        "Dir": "/go/pkg/mod/example.com/!lib@v1.0.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )
    initial_metadata = [
        Metadata(
            name="example.com/lib/V2/client",
            origin="example.com/lib/V2/client",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert [(m.name, m.version) for m in result] == [("example.com/lib", "v1.4.0")]
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="/tmp/go-resolve/lib",
        env={"GOTOOLCHAIN": "auto"},
    )


def test_gopkg_local_project_path_only_root_project_case_insensitive_fallback_per_root(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Case-sensitive ownership on one root entry does not block case-insensitive fallback on another."""
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "example.com/lib/V2/client",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/go-resolve/lib",
    )
    deps_list_json = """
{
    "ImportPath": "example.com/lib/V2/client",
    "Module": {
        "Path": "example.com/lib",
        "Version": "v1.4.0",
        "Dir": "/go/pkg/mod/example.com/lib@v1.4.0"
    }
}
{
    "ImportPath": "example.com/lib/v2/helper",
    "Module": {
        "Path": "example.com/lib/v2",
        "Version": "v2.1.0",
        "Dir": "/go/pkg/mod/example.com/lib/v2@v2.1.0"
    }
}
{
    "ImportPath": "github.com/DataDog/my-lib/v2/subpkg",
    "Module": {
        "Path": "github.com/DataDog/my-lib/v2",
        "Version": "v2.3.0",
        "Dir": "/go/pkg/mod/github.com/!data!dog/my-lib/v2@v2.3.0"
    }
}
{
    "ImportPath": "github.com/DataDog/my-lib/old",
    "Module": {
        "Path": "github.com/DataDog/my-lib",
        "Version": "v1.0.0",
        "Dir": "/go/pkg/mod/github.com/!data!dog/my-lib@v1.0.0"
    }
}
{
    "ImportPath": "github.com/DataDog/exact-mod",
    "Module": {
        "Path": "github.com/DataDog/exact-mod",
        "Version": "v1.1.0",
        "Dir": "/go/pkg/mod/github.com/!data!dog/exact-mod@v1.1.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        side_effect=[deps_list_json, "ref: refs/heads/main\tHEAD"],
    )
    initial_metadata = [
        Metadata(
            name="example.com/lib/V2/client",
            origin="example.com/lib/V2/client",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="github.com/Datadog/my-lib/v2/subpkg@v2.3.0",
            origin="https://github.com/Datadog/my-lib/v2/subpkg",
            local_src_path=None,
            license=[],
            version="v2.3.0",
            copyright=[],
        ),
        Metadata(
            name="github.com/datadog/exact-mod",
            origin="https://github.com/datadog/exact-mod",
            local_src_path=None,
            license=["Apache-2.0"],
            version="v1.1.0",
            copyright=["Datadog, Inc."],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert [(m.name, m.version) for m in result] == [
        ("github.com/Datadog/my-lib/v2/subpkg@v2.3.0", "v2.3.0"),
        ("github.com/DataDog/exact-mod", "v1.1.0"),
        ("example.com/lib", "v1.4.0"),
        ("github.com/DataDog/my-lib/v2", "v2.3.0"),
    ]
    mock_source_code_manager.get_code.assert_not_called()
    mock_source_code_manager.get_canonical_urls.assert_not_called()
    mock_output_from_command.assert_has_calls(
        [
            call(
                ["go", "list", "-json", "all"],
                cwd="/tmp/go-resolve/lib",
                env={"GOTOOLCHAIN": "auto"},
            ),
            call(
                [
                    "git",
                    "ls-remote",
                    "--symref",
                    "https://github.com/DataDog/my-lib",
                    "HEAD",
                ]
            ),
        ]
    )


def test_gopkg_only_root_project_prefers_exact_match_over_case_only_dependency(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Repository ONLY_ROOT_PROJECT scan prefers exact-case matches over case-only dependencies."""
    mock_source_code_manager = mocker.Mock()
    mock_source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/org/Repo",
        None,
    )
    strategy = GoPkgMetadataCollectionStrategy(
        "https://github.com/org/Repo",
        mock_source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
    )
    mock_source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/Repo",
        branch="main",
        local_root_path="cache_dir/org_Repo",
        local_full_path="cache_dir/org_Repo",
    )
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.walk_directory",
        return_value=[("org_Repo", [], ["go.mod"])],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.open_file",
        return_value="module github.com/org/Repo",
    )
    deps_list_json = """
{
    "ImportPath": "github.com/org/Repo",
    "Module": {
        "Path": "github.com/org/Repo",
        "Main": true,
        "Dir": "/cache/org/Repo"
    }
}
{
    "ImportPath": "github.com/org/repo/client",
    "Module": {
        "Path": "github.com/org/repo",
        "Version": "v1.0.0",
        "Dir": "/go/pkg/mod/github.com/org/repo@v1.0.0"
    }
}"""
    mock_output_from_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.gopkg_collection_strategy.output_from_command",
        return_value=deps_list_json,
    )
    initial_metadata = [
        Metadata(
            name="github.com/org/Repo",
            origin="https://github.com/org/Repo",
            local_src_path=None,
            license=["Apache-2.0"],
            version=None,
            copyright=["Org, Inc."],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == [
        Metadata(
            name="github.com/org/Repo",
            origin="https://github.com/org/Repo",
            local_src_path="/cache/org/Repo",
            license=["Apache-2.0"],
            version=None,
            copyright=["Org, Inc."],
        ),
    ]
    mock_source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/org/Repo"
    )
    mock_source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/Repo"
    )
    mock_walk_directory.assert_called_once_with("cache_dir/org_Repo")
    mock_open_file.assert_called_once_with("org_Repo/go.mod")
    mock_output_from_command.assert_called_once_with(
        ["go", "list", "-json", "all"],
        cwd="org_Repo",
        env={"GOTOOLCHAIN": "auto"},
    )
