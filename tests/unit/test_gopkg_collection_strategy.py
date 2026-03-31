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
    "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0",
    "ImportPath": "github.com/org/package1",
    "Name": "org/package1",
    "Root": "/tmp/go/pkg/mod/github.com/org/package1@v1.0",
    "Module": {
            "Path": "github.com/org/package1",
            "Version": "v1.0",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0"
    },
    "Deps": [
            "bufio",
            "bytes",
            "github.com/org/package1/package3"
    ]
}
{
    "Dir": "/tmp/go/pkg/mod/github.com/org/package5",
    "ImportPath": "github.com/org/package1/package5",
    "Name": "package5",
    "Root": "/tmp/go/pkg/mod/github.com/org/package5",
    "Module": {
            "Path": "github.com/org/package1/package5",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package5"
    },
    "Deps": [
            "github.com/org/package6"
    ]
}"""

    deps_list_json_3 = """
{
    "Dir": "/tmp/go/pkg/mod/github.com/org/package1/@v1.0/package3",
    "ImportPath": "github.com/org/package1/package3",
    "Name": "package3",
    "Root": "/tmp/go/pkg/mod/github.com/org/package1/@v1.0",
    "Module": {
            "Path": "github.com/org/package1/package3",
            "Version": "v1.0",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0/package3"
    },
    "Deps": [
            "github.com/org/package4"
    ]
}
{
    "Dir": "/tmp/go/pkg/mod/github.com/org/package4@v1.2.3",
    "ImportPath": "github.com/org/package4",
    "Name": "package4",
    "Root": "/tmp/go/pkg/mod/github.com/org/package4@v1.2.3",
    "Module": {
            "Path": "github.com/org/package4",
            "Version": "v1.2.3",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package4@v1.2.3"
    },
    "Deps": []
}
{
        "Dir": "/opt/homebrew/Cellar/go/1.23.5/libexec/src/bytes",
        "ImportPath": "bytes",
        "Name": "bytes",
        "Doc": "Package bytes implements functions for the manipulation of byte slices.",
        "Root": "/opt/homebrew/Cellar/go/1.23.5/libexec",
        "Match": [
                "all"
        ],
        "Goroot": true,
        "Standard": true,
        "Stale": true,
        "StaleReason": "stale dependency: internal/goarch",
        "Deps": []
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
            mocker.call("CWD=`pwd`; cd org_package1 && go list -json all; cd $CWD"),
            mocker.call(f"git ls-remote --symref https://github.com/org/package1 HEAD"),
            mocker.call(
                "CWD=`pwd`; cd org_package1/package3 && go list -json all; cd $CWD"
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
    "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0",
    "ImportPath": "github.com/org/package1",
    "Name": "org/package1",
    "Root": "/tmp/go/pkg/mod/github.com/org/package1@v1.0",
    "Module": {
            "Path": "github.com/org/package1",
            "Version": "v1.0",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0"
    },
    "Deps": [
            "bufio",
            "bytes",
            "github.com/org/package1/src"
    ]
}
{
    "Dir": "/tmp/go/pkg/mod/github.com/org/package1/src",
    "ImportPath": "github.com/org/package1/src",
    "Name": "src",
    "Root": "/tmp/go/pkg/mod/github.com/org/package1/src",
    "Module": {
            "Path": "github.com/org/package1/src",
            "Version": "v1.0",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package1/src"
    },
    "Deps": [
            "github.com/org/package2"
    ]
}"""
    deps_list_json_src = """
{
    "Dir": "/tmp/go/pkg/mod/github.com/org/package1/src",
    "ImportPath": "github.com/org/package1/src",
    "Name": "src",
    "Root": "/tmp/go/pkg/mod/github.com/org/package1/src",
    "Module": {
            "Path": "github.com/org/package1/src",
            "Version": "v1.0",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package1/src"
    },
    "Deps": [
            "github.com/org/package2"
    ]
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
            mocker.call("CWD=`pwd`; cd org_package1 && go list -json all; cd $CWD"),
            mocker.call(f"git ls-remote --symref https://github.com/org/package1 HEAD"),
            mocker.call("CWD=`pwd`; cd org_package1/src && go list -json all; cd $CWD"),
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
    "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0",
    "ImportPath": "github.com/org/package1",
    "Name": "org/package1",
    "Root": "/tmp/go/pkg/mod/github.com/org/package1@v1.0",
    "Module": {
            "Path": "github.com/org/package1",
            "Version": "v1.0",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package1@v1.0"
    },
    "Deps": [
            "bufio",
            "bytes",
            "github.com/org/package1/src"
    ]
}
{
    "Dir": "/tmp/go/pkg/mod/github.com/org/package1/src",
    "ImportPath": "github.com/org/package1/src",
    "Name": "src",
    "Root": "/tmp/go/pkg/mod/github.com/org/package1/src",
    "Module": {
            "Path": "github.com/org/package1/src",
            "Version": "v1.0",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package1/src"
    },
    "Deps": [
            "github.com/org/package2"
    ]
}
{
    "Dir": "/tmp/go/pkg/mod/github.com/org/package2",
    "ImportPath": "github.com/org/package2",
    "Name": "src",
    "Root": "/tmp/go/pkg/mod/github.com/org/package2",
    "Module": {
            "Path": "github.com/org/package2",
            "Version": "v1.0",
            "Time": "2022-09-15T18:34:49Z",
            "Dir": "/tmp/go/pkg/mod/github.com/org/package2"
    },
    "Deps": []
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
            call("CWD=`pwd`; cd org_package1 && go list -json all; cd $CWD"),
            call("CWD=`pwd`; cd org_package1/src && go list -json all; cd $CWD"),
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

    # go list -m -json all returns module-level data with Path/Version/Dir at top level
    deps_list_json = """
{
    "Path": "ddla-go-resolve",
    "Main": true,
    "Dir": "/tmp/go-resolve/github_com_stretchr_testify",
    "GoMod": "/tmp/go-resolve/github_com_stretchr_testify/go.mod",
    "GoVersion": "1.21"
}
{
    "Path": "github.com/stretchr/testify",
    "Version": "v1.9.0",
    "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
}
{
    "Path": "github.com/davecgh/go-spew",
    "Version": "v1.1.1",
    "Dir": "/tmp/go/pkg/mod/github.com/davecgh/go-spew@v1.1.1"
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
        "CWD=`pwd`; cd /tmp/go-resolve/github_com_stretchr_testify && GOTOOLCHAIN=auto go list -m -json all; cd $CWD"
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
    "Path": "{synthetic}",
    "Main": true,
    "Dir": "/tmp/go-resolve/testify"
}}
{{
    "Path": "github.com/stretchr/testify",
    "Version": "v1.9.0",
    "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
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
    "Path": "github.com/stretchr/testify",
    "Version": "v1.9.0",
    "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
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
    "Path": "github.com/stretchr/testify",
    "Version": "v1.9.0",
    "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
}
{
    "Path": "github.com/davecgh/go-spew",
    "Version": "v1.1.1",
    "Dir": "/tmp/go/pkg/mod/github.com/davecgh/go-spew@v1.1.1"
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

    # Seed removed, then only testify added back (go-spew filtered by only_root_project)
    # Since seed was removed and testify is not in the remaining list,
    # only_root_project will skip testify too. Result should be empty.
    assert len(result) == 0


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

    # Seed removed, empty output means no deps found
    assert len(result) == 0
    mock_output_from_command.assert_called_once()


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
    "Path": "github.com/stretchr/testify",
    "Version": "v1.9.0",
    "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
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
    """Indirect dependencies in go list -m -json all may lack a Dir field.

    These should get local_src_path=None so downstream strategies (e.g. ScanCode)
    skip local scanning instead of crashing on an empty path.
    """
    mock_source_code_manager = mocker.Mock()
    strategy = GoPkgMetadataCollectionStrategy(
        "github.com/stretchr/testify",
        mock_source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/go-resolve/testify",
    )

    # objx is indirect — no Dir field in go list -m -json all output
    deps_list_json = """
{
    "Path": "ddla-go-resolve",
    "Main": true,
    "Dir": "/tmp/go-resolve/testify"
}
{
    "Path": "github.com/stretchr/testify",
    "Version": "v1.9.0",
    "Dir": "/tmp/go/pkg/mod/github.com/stretchr/testify@v1.9.0"
}
{
    "Path": "github.com/stretchr/objx",
    "Version": "v0.5.2",
    "Indirect": true
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
        "CWD=`pwd`; cd /tmp/go-resolve/testify && GOTOOLCHAIN=auto go list -m -json all; cd $CWD"
    )
