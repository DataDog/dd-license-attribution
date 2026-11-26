# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import logging
from functools import partial
from unittest.mock import call

import pytest_mock
from pytest import LogCaptureFixture

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.config.cli_configs import default_config
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy import (
    ScanCodeToolkitMetadataCollectionStrategy,
    _strip_missing_go_major_version_suffix,
)


class GitUrlParseMock:
    def __init__(
        self,
        valid: bool,
        platform: str,
        owner: str | None,
        repo: str | None,
        path: str | None,
    ):
        self.valid = valid
        self.platform = platform
        self.owner = owner
        self.repo = repo
        self.path_raw = path
        self.branch = None
        self.protocol = "https"
        self.host = "github.com"
        self.url2https = f"https://github.com/{self.owner}/{self.repo}"


def mock_get_copyrights_side_effect(
    path: str, prefix_dir: str
) -> dict[str, list[dict[str, str]]]:
    if path == f"{prefix_dir}/copy1":
        return {
            "holders": [{"holder": "Datadog Inc."}],
            "authors": [{"author": "Datadog Authors"}],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        }
    elif path == f"{prefix_dir}/test_path_2/COPY2":
        return {
            "holders": [],
            "authors": [{"author": "Datadog Authors"}],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        }
    elif path == f"{prefix_dir}/test_path_3/copy1":
        return {
            "holders": [],
            "authors": [],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        }
    elif path == f"{prefix_dir}/test_path_4/copy1":
        return {
            "holders": [{"holder": "An individual"}],
            "authors": [],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        }
    else:
        return {
            "holders": [],
            "authors": [],
            "copyrights": [],
        }


def test_scancode_toolkit_collection_strategy_skips_packages_with_license_and_copyright(
    mocker: pytest_mock.MockFixture,
) -> None:
    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        )
    ]

    license_files = ["license1", "license2"]
    copyright_files = ["copy1", "copy2"]

    mock_source_code_manager = mocker.Mock()

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        mock_source_code_manager,
        license_source_files=license_files,
        copyright_source_files=copyright_files,
    )
    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == initial_metadata


def test_scancode_toolkit_collection_strategy_extracts_license_from_github_repos(
    mocker: pytest_mock.MockFixture,
) -> None:
    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=["License1", "license2", "file1", "file2"],
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="non_github_test_purl",
            local_src_path=None,
            license=[],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl",
            local_src_path=None,
            license=[],
            copyright=["Datadog Inc."],
        ),
    ]

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "APACHE-2.0"
    }

    license_files = ["license1", "LICENSE2", "license3"]
    copyright_files = ["copy1", "copy2"]

    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.side_effect = [
        None,
        SourceCodeReference(
            repo_url="https://github.com/test_owner/test_repo",
            branch="main",
            local_root_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
            local_full_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
        ),
    ]
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=license_files,
        copyright_source_files=copyright_files,
    )

    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=True,
    )

    updated_metadata = strategy.augment_metadata(initial_metadata)

    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/License1"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/license2"),
        ]
    )

    path_exists_mock.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
        ]
    )

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="non_github_test_purl",
            local_src_path=None,
            license=[],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
    ]

    assert expected_metadata == updated_metadata

    listdir_mock.assert_called_once_with(
        "cache_test/test_owner-test_repo/main/20220101-000000Z"
    )


def test_scancode_toolkit_collection_strategy_extracts_copyright_from_github_repos(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.side_effect = [
        SourceCodeReference(
            repo_url="https://github.com/test_owner/test_repo",
            branch="main",
            local_root_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
            local_full_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
        ),
        SourceCodeReference(
            repo_url="https://github.com/test_owner/test_repo",
            branch="main",
            local_root_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
            local_full_path="cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2",
        ),
        SourceCodeReference(
            repo_url="https://github.com/test_owner/test_repo",
            branch="main",
            local_root_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
            local_full_path="cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3",
        ),
    ]

    license_files = ["license1", "LICENSE2"]
    copyright_files = ["Copy1", "copy2", "copy3"]

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        ),
    ]

    walk_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.walk_directory"
    )

    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=["ignore"],
    )

    scancode_api_mock = mocker.patch("scancode.api")
    mock_get_copyrights_side_effect_with_cache = partial(
        mock_get_copyrights_side_effect,
        prefix_dir="cache_test/test_owner-test_repo/main/20220101-000000Z",
    )
    scancode_api_mock.get_copyrights.side_effect = (
        mock_get_copyrights_side_effect_with_cache
    )

    mock_walk_return_value_side_effect: list[list[tuple[str, list[str], list[str]]]] = [
        [
            (
                "cache_test/test_owner-test_repo/main/20220101-000000Z",
                [],
                ["test_1", "test_2", "copy1", "COPY2"],
            ),
        ],
        [
            (
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2",
                [],
                ["test_3", "test_4", "copy1", "COPY2"],
            ),
        ],
        [
            (
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3",
                [],
                ["test_5", "test_6", "copy1", "COPY2"],
            ),
        ],
    ]

    walk_mock.side_effect = mock_walk_return_value_side_effect

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=license_files,
        copyright_source_files=copyright_files,
    )

    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=True,
    )

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Authors"],
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc. 2024"],
        ),
    ]

    assert expected_metadata == updated_metadata

    source_code_manager_mock.assert_has_calls(
        [
            mocker.call.get_code("github_test_purl_2", force_update=False),
            mocker.call.get_code("github_test_purl_3", force_update=False),
            mocker.call.get_code("github_test_purl_4", force_update=False),
        ]
    )

    listdir_mock.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
        ]
    )

    walk_mock.assert_called_with(
        "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3"
    )

    scancode_api_mock.get_copyrights.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/copy1"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/COPY2"),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2/copy1"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2/COPY2"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3/copy1"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3/COPY2"
            ),
        ]
    )

    path_exists_mock.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
        ]
    )

    listdir_mock.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
        ]
    )


def test_scancode_toolkit_collection_strategy_receives_empty_filters_all_files_are_scanned(
    mocker: pytest_mock.MockFixture,
) -> None:

    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="main",
        local_root_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
        local_full_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        ),
    ]

    scancode_api_mock = mocker.patch("scancode.api")
    mock_get_copyrights_side_effect_with_cache = partial(
        mock_get_copyrights_side_effect,
        prefix_dir="cache_test/test_owner-test_repo/main/20220101-000000Z",
    )
    scancode_api_mock.get_copyrights.side_effect = (
        mock_get_copyrights_side_effect_with_cache
    )

    walk_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.walk_directory"
    )
    mock_walk_return_value_side_effect: list[list[tuple[str, list[str], list[str]]]] = [
        [
            (
                "cache_test/test_owner-test_repo/main/20220101-000000Z",
                [],
                ["test_1", "test_2", "copy1", "COPY2"],
            ),
        ],
        [
            (
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2",
                [],
                ["test_3", "test_4", "copy1", "COPY2"],
            ),
        ],
        [
            (
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3",
                [],
                ["test_5", "test_6", "copy1", "COPY2"],
            ),
        ],
    ]

    walk_mock.side_effect = mock_walk_return_value_side_effect

    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=True,
    )

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=None,
        copyright_source_files=None,
    )

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Authors"],
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc. 2024"],
        ),
    ]

    assert expected_metadata == updated_metadata

    walk_mock.assert_called_with(
        "cache_test/test_owner-test_repo/main/20220101-000000Z"
    )

    scancode_api_mock.get_copyrights.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/test_1"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/test_2"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/copy1"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/COPY2"),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2/test_3"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2/test_4"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2/copy1"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_2/COPY2"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3/test_5"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3/test_6"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3/copy1"
            ),
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_path_3/COPY2"
            ),
        ]
    )

    source_code_manager_mock.assert_has_calls(
        [
            mocker.call.get_code("github_test_purl_2", force_update=False),
            mocker.call.get_code("github_test_purl_3", force_update=False),
            mocker.call.get_code("github_test_purl_4", force_update=False),
        ]
    )

    path_exists_mock.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
        ]
    )


def test_scancode_toolkit_collection_strategy_do_not_mix_up_pre_cloned_repos(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.side_effect = [
        SourceCodeReference(
            repo_url="https://github.com/test_owner/test_repo",
            branch="main",
            local_root_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
            local_full_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
        ),
        SourceCodeReference(
            repo_url="https://github.com/test_owner2/test_repo2",
            branch="main",
            local_root_path="cache_test/test_owner2-test_repo2/main/20220101-000000Z",
            local_full_path="cache_test/test_owner2-test_repo2/main/20220101-000000Z",
        ),
        SourceCodeReference(
            repo_url="https://github.com/test_owner/test_repo",
            branch="main",
            local_root_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
            local_full_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
        ),
    ]

    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        side_effect=[["License1"], ["license2"], ["License1", "file2"]],
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            local_src_path=None,
            license=[],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            local_src_path=None,
            license=[],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_1",
            local_src_path=None,
            license=[],
            copyright=["Datadog Inc."],
        ),
    ]

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "APACHE-2.0"
    }

    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=True,
    )

    license_files = ["license1", "LICENSE2"]
    copyright_files = ["Copy1", "copy2", "copy3"]

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=license_files,
        copyright_source_files=copyright_files,
    )

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_1",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
    ]

    assert expected_metadata == updated_metadata

    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/License1"),
            call("cache_test/test_owner2-test_repo2/main/20220101-000000Z/license2"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z/License1"),
        ]
    )

    listdir_mock.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner2-test_repo2/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
        ]
    )

    source_code_manager_mock.assert_has_calls(
        [
            mocker.call.get_code("github_test_purl_1", force_update=False),
            mocker.call.get_code("github_test_purl_2", force_update=False),
            mocker.call.get_code("github_test_purl_1", force_update=False),
        ]
    )

    path_exists_mock.assert_has_calls(
        [
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner2-test_repo2/main/20220101-000000Z"),
            call("cache_test/test_owner2-test_repo2/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
        ]
    )


def test_dotgit_directory_is_not_inspected_for_license_and_copyright_files(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="package1",
        branch="main",
        local_root_path="cache_test/package1/main/20220101-000000Z",
        local_full_path="cache_test/package1/main/20220101-000000Z/test_path_1",
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="package1",
            local_src_path=None,
            license=[],
            copyright=[],
        )
    ]
    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=["LICENSE", "COPYRIGHT"],
    )

    walk_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.walk_directory",
        return_value=[
            (
                "cache_test/package1/main/20220101-000000Z/test_path_1",
                [".git"],
                ["LICENSE", "COPYRIGHT"],
            ),
            (
                "cache_test/package1/main/20220101-000000Z/test_path/.git",
                [],
                ["License", "Copyright"],
            ),
            (
                "cache_test/package1/main/20220101-000000Z/test_path_1/.git/path",
                [],
                ["LICENSE", "COPYRIGHT"],
            ),
        ],
    )

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "APACHE-2.0"
    }
    scancode_api_mock.get_copyrights.return_value = {
        "holders": [{"holder": "Datadog Inc."}],
        "authors": [{"author": "Datadog Authors"}],
        "copyrights": [{"copyright": "Datadog Inc. 2024"}],
    }

    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=True,
    )

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=["LICENSE"],
        copyright_source_files=["COPYRIGHT"],
    )

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="package1",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        )
    ]

    assert expected_metadata == updated_metadata

    walk_mock.assert_has_calls(
        [
            call("cache_test/package1/main/20220101-000000Z/test_path_1"),
        ]
    )
    listdir_mock.assert_has_calls(
        [
            call("cache_test/package1/main/20220101-000000Z/test_path_1"),
            call("cache_test/package1/main/20220101-000000Z"),
            call("cache_test/package1/main/20220101-000000Z"),
        ]
    )
    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("cache_test/package1/main/20220101-000000Z/test_path_1/LICENSE"),
            call("cache_test/package1/main/20220101-000000Z/LICENSE"),
        ]
    )
    scancode_api_mock.get_copyrights.assert_has_calls(
        [
            call("cache_test/package1/main/20220101-000000Z/test_path_1/COPYRIGHT"),
            call("cache_test/package1/main/20220101-000000Z/COPYRIGHT"),
        ]
    )

    path_exists_mock.assert_has_calls(
        [
            call("cache_test/package1/main/20220101-000000Z/test_path_1"),
            call("cache_test/package1/main/20220101-000000Z"),
        ]
    )


def test_scancode_toolkit_collection_strategy_extracts_copyright_and_license_from_local_src_path_if_available(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="package1",
        branch="main",
        local_root_path="cache_test/package2/main/20220101-000000Z",
        local_full_path="cache_test/package2/main/20220101-000000Z",
    )

    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=["LICENSE", "COPYRIGHT"],
    )

    walk_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.walk_directory",
        side_effect=[
            [
                (
                    "/tmp/go/mod/github.com/org/package1@v1.0",
                    [],
                    ["LICENSE", "COPYRIGHT"],
                )
            ],
            [
                (
                    "cache_test/package2/main/20220101-000000Z",
                    [],
                    ["LICENSE", "COPYRIGHT"],
                )
            ],
        ],
    )

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "TEST_LICENSE"
    }
    scancode_api_mock.get_copyrights.return_value = {
        "holders": [{"holder": "TEST_HOLDER"}],
        "authors": [{"author": "TEST_AUTHOR"}],
        "copyrights": [{"copyright": "TEST_COPY"}],
    }

    initial_metadata = [
        Metadata(
            name="package1",
            version="v1.0",
            origin="package1",
            local_src_path="/tmp/go/mod/github.com/org/package1@v1.0",
            license=[],
            copyright=[],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="package2",
            local_src_path=None,
            license=[],
            copyright=[],
        ),
        Metadata(
            name="package3",
            version="v1.0",
            origin="package3",
            local_src_path="/tmp/go/mod/github.com/org/package3@v1.0",
            license=["MIT"],
            copyright=["Datadog Inc."],
        ),
    ]

    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=True,
    )

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=["license"],
        copyright_source_files=["copyright"],
    )

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="package1",
            version="v1.0",
            origin="package1",
            local_src_path="/tmp/go/mod/github.com/org/package1@v1.0",
            license=["TEST_LICENSE"],
            copyright=["TEST_HOLDER"],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="package2",
            local_src_path=None,
            license=["TEST_LICENSE"],
            copyright=["TEST_HOLDER"],
        ),
        Metadata(
            name="package3",
            version="v1.0",
            origin="package3",
            local_src_path="/tmp/go/mod/github.com/org/package3@v1.0",
            license=["MIT"],
            copyright=["Datadog Inc."],
        ),
    ]

    assert expected_metadata == updated_metadata

    walk_mock.assert_has_calls(
        [
            call("/tmp/go/mod/github.com/org/package1@v1.0"),
            call("cache_test/package2/main/20220101-000000Z"),
        ]
    )

    listdir_mock.assert_has_calls(
        [
            call("/tmp/go/mod/github.com/org/package1@v1.0"),
            call("cache_test/package2/main/20220101-000000Z"),
        ]
    )

    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("/tmp/go/mod/github.com/org/package1@v1.0/LICENSE"),
            call("cache_test/package2/main/20220101-000000Z/LICENSE"),
        ]
    )

    scancode_api_mock.get_copyrights.assert_has_calls(
        [
            call("/tmp/go/mod/github.com/org/package1@v1.0/COPYRIGHT"),
            call("cache_test/package2/main/20220101-000000Z/COPYRIGHT"),
        ]
    )

    path_exists_mock.assert_has_calls(
        [
            call("cache_test/package2/main/20220101-000000Z"),
            call("cache_test/package2/main/20220101-000000Z"),
        ]
    )


def test_scancode_toolkit_collection_strategy_extracts_copyright_and_license_from_repo_if_local_src_path_cannot_provide_it(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="http://github.com/org/package1",
        branch="main",
        local_root_path="cache_test/org/package1/main/20220101-000000Z",
        local_full_path="cache_test/org/package1/main/20220101-000000Z",
    )

    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        side_effect=[["nothing", "here"], ["LICENSE", "COPYRIGHT"]],
    )

    walk_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.walk_directory",
        side_effect=[
            [
                (
                    "/tmp/go/mod/github.com/org/package1@v1.0",
                    [],
                    ["nothing", "here"],
                )
            ],
            [
                (
                    "cache_test/org/package1/main/20220101-000000Z",
                    [],
                    ["LICENSE", "COPYRIGHT"],
                )
            ],
        ],
    )

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "TEST_LICENSE"
    }
    scancode_api_mock.get_copyrights.return_value = {
        "holders": [{"holder": "TEST_HOLDER"}],
        "authors": [{"author": "TEST_AUTHOR"}],
        "copyrights": [{"copyright": "TEST_COPY"}],
    }

    initial_metadata = [
        Metadata(
            name="github.com/org/package1",
            version="v1.0",
            origin="https://github.com/org/package1",
            local_src_path="/tmp/go/mod/github.com/org/package1@v1.0",
            license=[],
            copyright=[],
        ),
    ]

    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=True,
    )

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=["license"],
        copyright_source_files=["copyright"],
    )

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="github.com/org/package1",
            version="v1.0",
            origin="https://github.com/org/package1",
            local_src_path="/tmp/go/mod/github.com/org/package1@v1.0",
            license=["TEST_LICENSE"],
            copyright=["TEST_HOLDER"],
        ),
    ]

    assert expected_metadata == updated_metadata

    walk_mock.assert_has_calls(
        [
            call("/tmp/go/mod/github.com/org/package1@v1.0"),
            call("cache_test/org/package1/main/20220101-000000Z"),
        ]
    )

    listdir_mock.assert_has_calls(
        [
            call("/tmp/go/mod/github.com/org/package1@v1.0"),
            call("cache_test/org/package1/main/20220101-000000Z"),
        ]
    )

    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("cache_test/org/package1/main/20220101-000000Z/LICENSE"),
        ]
    )

    scancode_api_mock.get_copyrights.assert_has_calls(
        [
            call("cache_test/org/package1/main/20220101-000000Z/COPYRIGHT"),
        ]
    )

    source_code_manager_mock.assert_has_calls(
        [
            mocker.call.get_code("https://github.com/org/package1", force_update=False),
        ]
    )

    path_exists_mock.assert_has_calls(
        [
            call("cache_test/org/package1/main/20220101-000000Z"),
        ]
    )


def test_scancode_toolkit_collection_strategy_extracts_only_copyright_when_license_already_exists(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Test that when a package has local_src_path and already has a license,
    only copyright is extracted."""

    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=["LICENSE", "COPYRIGHT"],
    )

    walk_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.walk_directory",
        return_value=[
            (
                "/tmp/go/mod/github.com/org/package1@v1.0",
                [],
                ["LICENSE", "COPYRIGHT"],
            )
        ],
    )

    scancode_api_mock = mocker.patch("scancode.api")
    # License should not be called since package already has license
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "SHOULD_NOT_BE_CALLED"
    }
    scancode_api_mock.get_copyrights.return_value = {
        "holders": [{"holder": "TEST_HOLDER"}],
        "authors": [{"author": "TEST_AUTHOR"}],
        "copyrights": [{"copyright": "TEST_COPY"}],
    }

    initial_metadata = [
        Metadata(
            name="package1",
            version="v1.0",
            origin="package1",
            local_src_path="/tmp/go/mod/github.com/org/package1@v1.0",
            license=["EXISTING_LICENSE"],  # Already has license
            copyright=[],  # Empty copyright - should be extracted
        ),
    ]

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        mocker.Mock(),  # source_code_manager not needed for local_src_path
        license_source_files=["license"],
        copyright_source_files=["copyright"],
    )

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="package1",
            version="v1.0",
            origin="package1",
            local_src_path="/tmp/go/mod/github.com/org/package1@v1.0",
            license=["EXISTING_LICENSE"],  # Should remain unchanged
            copyright=["TEST_HOLDER"],  # Should be extracted
        ),
    ]

    assert expected_metadata == updated_metadata

    # Verify that license extraction was not called (since package already has license)
    scancode_api_mock.get_licenses.assert_not_called()

    # Verify that copyright extraction was called
    scancode_api_mock.get_copyrights.assert_called_once_with(
        "/tmp/go/mod/github.com/org/package1@v1.0/COPYRIGHT"
    )

    walk_mock.assert_called_once_with("/tmp/go/mod/github.com/org/package1@v1.0")
    # list_dir should not be called because this test verifies copyright extraction using recursive directory traversal (walk_directory),
    # which is appropriate for extracting copyright information from nested directories.
    listdir_mock.assert_not_called()


def test_no_crash_on_wrong_path_being_infered_in_previous_step_if_the_local_src_dir_is_set(
    mocker: pytest_mock.MockFixture,
) -> None:
    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=["License1", "license2", "file1", "file2"],
    )

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {}

    license_files = ["license1", "LICENSE2", "license3"]
    copyright_files = ["copy1", "copy2"]

    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="main",
        local_root_path="cache_test/test_owner-test_repo/main/20220101-000000Z",
        local_full_path="cache_test/test_owner-test_repo/main/20220101-000000Z/test_not_existent_path",
    )

    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        side_effect=[True, False],
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="non_github_test_purl",
            local_src_path="/local_path/to/package1",
            license=[],
            copyright=["Datadog Inc."],
        ),
    ]

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=license_files,
        copyright_source_files=copyright_files,
    )

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="non_github_test_purl",
            local_src_path="/local_path/to/package1",
            license=[],
            copyright=["Datadog Inc."],
        ),
    ]

    assert expected_metadata == updated_metadata

    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("/local_path/to/package1/License1"),
            call("/local_path/to/package1/license2"),
        ]
    )

    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_test/test_owner-test_repo/main/20220101-000000Z/test_not_existent_path"
            ),
            call("cache_test/test_owner-test_repo/main/20220101-000000Z"),
        ]
    )

    listdir_mock.assert_called_once_with("/local_path/to/package1")


def test_scancode_toolkit_logs_warning_when_source_code_cannot_be_resolved(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """A package whose source cannot be resolved/cloned is skipped with a WARNING (not silently) and counted in a summary."""
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = None

    strategy = ScanCodeToolkitMetadataCollectionStrategy(source_code_manager_mock)
    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=[],
            copyright=[],
        )
    ]

    with caplog.at_level(logging.WARNING):
        updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == initial_metadata
    source_code_manager_mock.get_code.assert_called_once_with(
        "test_purl", force_update=False
    )
    expected_warning = (
        "Skipping source scan for package1: could not resolve or clone test_purl"
    )
    assert any(
        expected_warning in record.message for record in caplog.records
    ), caplog.records
    expected_summary = "Enrichment skipped for 1 of 1 dependencies"
    assert any(
        expected_summary in record.message for record in caplog.records
    ), caplog.records


def test_scancode_toolkit_skip_summary_counts_only_unresolved_packages(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """The summary reports skipped-of-total; packages that never needed enrichment don't count."""
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = None

    strategy = ScanCodeToolkitMetadataCollectionStrategy(source_code_manager_mock)
    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=["MIT"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="test_purl_2",
            local_src_path=None,
            license=[],
            copyright=[],
        ),
    ]

    with caplog.at_level(logging.WARNING):
        updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == initial_metadata
    # Only package2 needed enrichment; package1 already had license+copyright.
    source_code_manager_mock.get_code.assert_called_once_with(
        "test_purl_2", force_update=False
    )
    assert any(
        "Skipping source scan for package2: could not resolve or clone test_purl_2"
        in record.message
        for record in caplog.records
    ), caplog.records
    expected_summary = "Enrichment skipped for 1 of 2 dependencies"
    assert any(
        expected_summary in record.message for record in caplog.records
    ), caplog.records


def test_scancode_toolkit_no_skip_summary_when_all_packages_enriched_or_complete(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """No skip-summary WARNING is emitted when nothing was skipped."""
    source_code_manager_mock = mocker.Mock()

    strategy = ScanCodeToolkitMetadataCollectionStrategy(source_code_manager_mock)
    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=["MIT"],
            copyright=["Datadog Inc."],
        )
    ]

    with caplog.at_level(logging.WARNING):
        updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == initial_metadata
    source_code_manager_mock.get_code.assert_not_called()
    assert not any(
        "Enrichment skipped" in record.message for record in caplog.records
    ), caplog.records


def test_scancode_toolkit_matches_umbrella_license_extensions_and_skips_per_license_files(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Default presets match standard umbrella license extensions (e.g. COPYING.md, LICENSE.rst, LICENCE.txt)
    without merging sibling per-license files (e.g. LICENSE.APACHE, LICENSE.BSD, LICENSE-MIT) into an AND.
    """
    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=[
            "COPYING.md",
            "LICENSE.BSD",
            "LICENSE.MPL-2.0",
            "LICENSE.APACHE",
            "LICENSE-MIT",
            "LICENSE-3rdparty.csv",
            "license.go",
            "license.py",
            "README.md",
        ],
    )
    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "BSD-3-Clause AND MPL-2.0"
    }
    source_code_manager_mock = mocker.Mock()
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=default_config.preset_license_file_locations,
        copyright_source_files=default_config.preset_copyright_file_locations,
    )
    initial_metadata = [
        Metadata(
            name="github.com/cyphar/filepath-securejoin",
            version="v0.7.0",
            origin="https://github.com/cyphar/filepath-securejoin",
            local_src_path="/go/pkg/mod/github.com/cyphar/filepath-securejoin@v0.7.0",
            license=[],
            copyright=["SUSE LLC"],
        )
    ]

    updated = strategy.augment_metadata(initial_metadata)

    assert len(updated) == 1
    assert set(updated[0].license) == {"BSD-3-Clause", "MPL-2.0"}
    listdir_mock.assert_called_once_with(
        "/go/pkg/mod/github.com/cyphar/filepath-securejoin@v0.7.0"
    )
    scancode_api_mock.get_licenses.assert_called_once_with(
        "/go/pkg/mod/github.com/cyphar/filepath-securejoin@v0.7.0/COPYING.md"
    )
    scancode_api_mock.get_copyrights.assert_not_called()
    source_code_manager_mock.get_code.assert_not_called()


def test_scancode_toolkit_does_not_turn_dual_license_choice_into_and(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Packages with an umbrella LICENSE plus per-license sibling files (e.g. packaging, cryptography)
    keep the umbrella OR expression rather than appending sibling files as AND."""
    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=["LICENSE", "LICENSE.APACHE", "LICENSE.BSD"],
    )
    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "BSD-3-Clause OR Apache-2.0"
    }
    source_code_manager_mock = mocker.Mock()
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=default_config.preset_license_file_locations,
        copyright_source_files=default_config.preset_copyright_file_locations,
    )
    initial_metadata = [
        Metadata(
            name="packaging",
            version="26.3",
            origin="https://github.com/pypa/packaging",
            local_src_path="/local/packaging",
            license=[],
            copyright=["pypa"],
        )
    ]

    updated = strategy.augment_metadata(initial_metadata)

    assert len(updated) == 1
    assert updated[0].license == ["BSD-3-Clause OR Apache-2.0"]
    listdir_mock.assert_called_once_with("/local/packaging")
    scancode_api_mock.get_licenses.assert_called_once_with("/local/packaging/LICENSE")
    scancode_api_mock.get_copyrights.assert_not_called()
    source_code_manager_mock.get_code.assert_not_called()


def test_cleanup_licenses_preserves_parenthesized_spdx_expressions() -> None:
    result = ScanCodeToolkitMetadataCollectionStrategy.cleanup_licenses(
        ["(Apache-2.0 AND (Apache-2.0 OR BSD-3-Clause))"]
    )
    assert set(result) == {"Apache-2.0", "Apache-2.0 OR BSD-3-Clause"}


def test_cleanup_licenses_flattens_nested_and_and_deduplicates() -> None:
    result = ScanCodeToolkitMetadataCollectionStrategy.cleanup_licenses(
        [
            "(BSD-3-Clause AND (MIT AND Apache-2.0) AND MIT)",
            "((Apache-2.0 OR BSD-3-Clause) AND Apache-2.0)",
        ]
    )
    assert len(result) == 4
    assert set(result) == {
        "Apache-2.0",
        "Apache-2.0 OR BSD-3-Clause",
        "BSD-3-Clause",
        "MIT",
    }


def test_cleanup_licenses_keeps_or_unwrapped_for_cautionary_prefix_checks() -> None:
    result = ScanCodeToolkitMetadataCollectionStrategy.cleanup_licenses(
        ["GPL-3.0-only OR MIT", "Apache-2.0"]
    )
    assert set(result) == {"Apache-2.0", "GPL-3.0-only OR MIT"}


def test_cleanup_licenses_does_not_split_and_inside_or() -> None:
    result = ScanCodeToolkitMetadataCollectionStrategy.cleanup_licenses(
        ["(Apache-2.0 OR (MIT AND BSD-3-Clause))"]
    )
    assert result == ["Apache-2.0 OR (MIT AND BSD-3-Clause)"]


def test_cleanup_licenses_preserves_with_exception_and_filters_unknown_and_cla() -> (
    None
):
    result = ScanCodeToolkitMetadataCollectionStrategy.cleanup_licenses(
        [
            "(Apache-2.0 WITH LLVM-exception) AND LicenseRef-scancode-unknown-license-reference AND LicenseRef-scancode-generic-cla"
        ]
    )
    assert result == ["Apache-2.0 WITH LLVM-exception"]

    filtered_to_single_or = ScanCodeToolkitMetadataCollectionStrategy.cleanup_licenses(
        ["(MIT OR Apache-2.0) AND LicenseRef-scancode-unknown-license-reference"]
    )
    assert filtered_to_single_or == ["MIT OR Apache-2.0"]


def test_cleanup_licenses_falls_back_on_unparseable_and_skips_empty() -> None:
    result = ScanCodeToolkitMetadataCollectionStrategy.cleanup_licenses(
        ["", "   ", "invalid ( broken"]
    )
    assert result == ["invalid ( broken"]

    with_other_license = ScanCodeToolkitMetadataCollectionStrategy.cleanup_licenses(
        ["invalid ( broken", "MIT"]
    )
    assert len(with_other_license) == 2
    assert set(with_other_license) == {"invalid ( broken", "MIT"}


def test_scancode_toolkit_extracts_valid_spdx_from_parenthesized_expression(
    mocker: pytest_mock.MockFixture,
) -> None:
    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=["LICENSE"],
    )
    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "(MIT AND Apache-2.0)"
    }
    source_code_manager_mock = mocker.Mock()
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=["LICENSE"],
        copyright_source_files=["NOTICE"],
    )
    initial_metadata = [
        Metadata(
            name="go.yaml.in/yaml/v3",
            version="v3.0.4",
            origin="https://go.yaml.in/yaml/v3",
            local_src_path="/local/yaml/v3",
            license=[],
            copyright=["Canonical Ltd."],
        )
    ]

    updated = strategy.augment_metadata(initial_metadata)

    assert len(updated) == 1
    assert set(updated[0].license) == {"Apache-2.0", "MIT"}
    listdir_mock.assert_called_once_with("/local/yaml/v3")
    scancode_api_mock.get_licenses.assert_called_once_with("/local/yaml/v3/LICENSE")
    scancode_api_mock.get_copyrights.assert_not_called()
    source_code_manager_mock.get_code.assert_not_called()


def test_scancode_toolkit_preserves_existing_go_major_version_directory(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Directory-based Go v2+ modules (where v2/ exists in the clone) scan local_full_path directly."""
    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        side_effect=[["LICENSE"], ["LICENSE"]],
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        side_effect=[True, True],
    )
    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.side_effect = [
        {"detected_license_expression_spdx": "MIT"},
        {"detected_license_expression_spdx": "Apache-2.0"},
    ]
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/repo",
        branch="main",
        local_root_path="cache/org-repo/main",
        local_full_path="cache/org-repo/main/v2",
    )
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=["LICENSE"],
        copyright_source_files=["NOTICE"],
    )
    initial_metadata = [
        Metadata(
            name="github.com/org/repo/v2",
            version="v2.1.0",
            origin="https://github.com/org/repo/tree/main/v2",
            local_src_path=None,
            license=[],
            copyright=["Org"],
        )
    ]

    updated = strategy.augment_metadata(initial_metadata)

    assert set(updated[0].license) == {"Apache-2.0", "MIT"}
    source_code_manager_mock.get_code.assert_called_once_with(
        "https://github.com/org/repo/tree/main/v2", force_update=False
    )
    path_exists_mock.assert_has_calls(
        [call("cache/org-repo/main/v2"), call("cache/org-repo/main")]
    )
    listdir_mock.assert_has_calls(
        [call("cache/org-repo/main/v2"), call("cache/org-repo/main")]
    )
    scancode_api_mock.get_licenses.assert_has_calls(
        [call("cache/org-repo/main/v2/LICENSE"), call("cache/org-repo/main/LICENSE")]
    )
    scancode_api_mock.get_copyrights.assert_not_called()


def test_scancode_toolkit_falls_back_when_go_major_version_dir_is_absent(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Branch/tag-based Go v2+ modules (no v2/ or v10/ dir on disk) fall back to the parent path without warning."""
    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        side_effect=[["LICENSE"], ["LICENSE"], ["LICENSE"], ["LICENSE"]],
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        side_effect=[
            False,
            True,
            True,
            False,
            True,
            True,
            False,
            True,
            True,
            True,
        ],
    )
    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "Apache-2.0"
    }
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.side_effect = [
        SourceCodeReference(
            repo_url="https://github.com/containerd/typeurl",
            branch="main",
            local_root_path="cache/containerd-typeurl/main",
            local_full_path="cache/containerd-typeurl/main/v2",
        ),
        SourceCodeReference(
            repo_url="https://github.com/go-playground/validator",
            branch="master",
            local_root_path="cache/go-playground-validator/master",
            local_full_path="cache/go-playground-validator/master/v10",
        ),
        SourceCodeReference(
            repo_url="https://github.com/org/mono",
            branch="main",
            local_root_path="cache/org-mono/main",
            local_full_path="cache/org-mono/main/pkg/subpkg/v3",
        ),
    ]
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=["LICENSE"],
        copyright_source_files=["NOTICE"],
    )
    initial_metadata = [
        Metadata(
            name="github.com/containerd/typeurl/v2",
            version="v2.3.0",
            origin="https://github.com/containerd/typeurl/tree/main/v2",
            local_src_path=None,
            license=[],
            copyright=["containerd"],
        ),
        Metadata(
            name="github.com/go-playground/validator/v10",
            version="v10.26.0",
            origin="https://github.com/go-playground/validator/tree/master/v10",
            local_src_path=None,
            license=[],
            copyright=["Dean Karn"],
        ),
        Metadata(
            name="github.com/org/mono/pkg/subpkg/v3",
            version="v3.1.0",
            origin="https://github.com/org/mono/tree/main/pkg/subpkg/v3",
            local_src_path=None,
            license=[],
            copyright=["Org"],
        ),
    ]

    with caplog.at_level(logging.WARNING):
        updated = strategy.augment_metadata(initial_metadata)

    assert [m.license for m in updated] == [
        ["Apache-2.0"],
        ["Apache-2.0"],
        ["Apache-2.0"],
    ]
    assert not any(
        "does not exist, skipping" in record.message for record in caplog.records
    ), caplog.records
    path_exists_mock.assert_has_calls(
        [
            call("cache/containerd-typeurl/main/v2"),
            call("cache/containerd-typeurl/main"),
            call("cache/containerd-typeurl/main/go.mod"),
            call("cache/go-playground-validator/master/v10"),
            call("cache/go-playground-validator/master"),
            call("cache/go-playground-validator/master/go.mod"),
            call("cache/org-mono/main/pkg/subpkg/v3"),
            call("cache/org-mono/main"),
            call("cache/org-mono/main/pkg/subpkg"),
            call("cache/org-mono/main/pkg/subpkg/go.mod"),
        ]
    )
    listdir_mock.assert_has_calls(
        [
            call("cache/containerd-typeurl/main"),
            call("cache/go-playground-validator/master"),
            call("cache/org-mono/main/pkg/subpkg"),
            call("cache/org-mono/main"),
        ]
    )
    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("cache/containerd-typeurl/main/LICENSE"),
            call("cache/go-playground-validator/master/LICENSE"),
            call("cache/org-mono/main/pkg/subpkg/LICENSE"),
            call("cache/org-mono/main/LICENSE"),
        ]
    )
    scancode_api_mock.get_copyrights.assert_not_called()
    source_code_manager_mock.get_code.assert_has_calls(
        [
            call(
                "https://github.com/containerd/typeurl/tree/main/v2",
                force_update=False,
            ),
            call(
                "https://github.com/go-playground/validator/tree/master/v10",
                force_update=False,
            ),
            call(
                "https://github.com/org/mono/tree/main/pkg/subpkg/v3",
                force_update=False,
            ),
        ]
    )


def test_scancode_toolkit_skips_missing_non_siv_non_go_or_missing_parent_paths(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
) -> None:
    """Missing paths that are not Go v2+ modules (v1, v0, v02, v2alpha, npm/PyPI, missing parent, or no go.mod) still skip."""
    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        side_effect=[
            False,
            True,  # v1
            False,
            True,  # v0
            False,
            True,  # v02
            False,
            True,  # v2alpha
            False,
            True,  # non-child path
            False,
            True,
            False,  # missing parent dir for Go module
            False,
            True,  # npm package (name does not look like Go module)
            False,
            True,  # scoped npm package (@scope/v2 has no dot in host)
            False,
            True,
            False,  # Go-like name but fallback dir has no go.mod
        ],
    )
    scancode_api_mock = mocker.patch("scancode.api")
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.side_effect = [
        SourceCodeReference(
            repo_url="https://github.com/org/repo",
            branch="main",
            local_root_path="cache/org-repo/main",
            local_full_path="cache/org-repo/main/v1",
        ),
        SourceCodeReference(
            repo_url="https://github.com/org/repo",
            branch="main",
            local_root_path="cache/org-repo/main",
            local_full_path="cache/org-repo/main/v0",
        ),
        SourceCodeReference(
            repo_url="https://github.com/org/repo",
            branch="main",
            local_root_path="cache/org-repo/main",
            local_full_path="cache/org-repo/main/v02",
        ),
        SourceCodeReference(
            repo_url="https://github.com/org/repo",
            branch="main",
            local_root_path="cache/org-repo/main",
            local_full_path="cache/org-repo/main/v2alpha",
        ),
        SourceCodeReference(
            repo_url="https://github.com/org/repo",
            branch="main",
            local_root_path="cache/org-repo/main",
            local_full_path="other/path/v2",
        ),
        SourceCodeReference(
            repo_url="https://github.com/org/repo",
            branch="main",
            local_root_path="cache/org-repo/main",
            local_full_path="cache/org-repo/main/missing/v3",
        ),
        SourceCodeReference(
            repo_url="https://github.com/org/js-repo",
            branch="main",
            local_root_path="cache/org-js-repo/main",
            local_full_path="cache/org-js-repo/main/pkg/v2",
        ),
        SourceCodeReference(
            repo_url="https://github.com/org/js-repo",
            branch="main",
            local_root_path="cache/org-js-repo/main",
            local_full_path="cache/org-js-repo/main/v2",
        ),
        SourceCodeReference(
            repo_url="https://github.com/org/non-go",
            branch="main",
            local_root_path="cache/org-non-go/main",
            local_full_path="cache/org-non-go/main/v2",
        ),
    ]
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=["LICENSE"],
        copyright_source_files=["NOTICE"],
    )
    package_names: list[str | None] = [
        "github.com/org/repo/v1",
        "github.com/org/repo/v0",
        "github.com/org/repo/v02",
        "github.com/org/repo/v2alpha",
        "github.com/org/repo/v2",
        "github.com/org/repo/missing/v3",
        "my-npm-pkg",
        "@scope/v2",
        "github.com/org/non-go/v2",
    ]
    initial_metadata = [
        Metadata(
            name=name,
            version=None,
            origin=f"https://github.com/org/repo/tree/main/p{i}",
            local_src_path=None,
            license=[],
            copyright=["Org"],
        )
        for i, name in enumerate(package_names)
    ]

    with caplog.at_level(logging.WARNING):
        updated = strategy.augment_metadata(initial_metadata)

    assert all(m.license == [] for m in updated)
    skip_warnings = [
        r for r in caplog.records if "does not exist, skipping" in r.message
    ]
    assert len(skip_warnings) == 9
    scancode_api_mock.get_licenses.assert_not_called()
    scancode_api_mock.get_copyrights.assert_not_called()
    assert path_exists_mock.call_args_list == [
        call("cache/org-repo/main/v1"),
        call("cache/org-repo/main"),
        call("cache/org-repo/main/v0"),
        call("cache/org-repo/main"),
        call("cache/org-repo/main/v02"),
        call("cache/org-repo/main"),
        call("cache/org-repo/main/v2alpha"),
        call("cache/org-repo/main"),
        call("other/path/v2"),
        call("cache/org-repo/main"),
        call("cache/org-repo/main/missing/v3"),
        call("cache/org-repo/main"),
        call("cache/org-repo/main/missing"),
        call("cache/org-js-repo/main/pkg/v2"),
        call("cache/org-js-repo/main"),
        call("cache/org-js-repo/main/v2"),
        call("cache/org-js-repo/main"),
        call("cache/org-non-go/main/v2"),
        call("cache/org-non-go/main"),
        call("cache/org-non-go/main/go.mod"),
    ]
    assert source_code_manager_mock.get_code.call_args_list == [
        call(f"https://github.com/org/repo/tree/main/p{i}", force_update=False)
        for i in range(9)
    ]


def test_strip_missing_go_major_version_suffix_trailing_slashes_and_field_forwarding(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Helper normalizes trailing slashes, enforces Go provenance, and forwards all SourceCodeReference fields."""
    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=True,
    )

    # Trailing slashes on both local_root_path and local_full_path, plus a root ending in 'X'
    root_with_slash = SourceCodeReference(
        repo_url="https://github.com/org/repo",
        branch="branchX",
        local_root_path="/cache/org-repo/branchX/",
        local_full_path="/cache/org-repo/branchX/v2/",
    )
    assert _strip_missing_go_major_version_suffix(
        "github.com/org/repo/v2", root_with_slash
    ) == SourceCodeReference(
        repo_url="https://github.com/org/repo",
        branch="branchX",
        local_root_path="/cache/org-repo/branchX/",
        local_full_path="/cache/org-repo/branchX/",
    )

    # Nested subpath under a root ending in 'X' with trailing slash on full path
    nested_with_slash = SourceCodeReference(
        repo_url="https://github.com/org/mono",
        branch="release-X",
        local_root_path="/cache/org-mono/branchX",
        local_full_path="/cache/org-mono/branchX/pkg/v4/",
    )
    assert _strip_missing_go_major_version_suffix(
        "github.com/org/mono/pkg/v4", nested_with_slash
    ) == SourceCodeReference(
        repo_url="https://github.com/org/mono",
        branch="release-X",
        local_root_path="/cache/org-mono/branchX",
        local_full_path="/cache/org-mono/branchX/pkg",
    )
    assert path_exists_mock.call_args_list == [
        call("/cache/org-repo/branchX/go.mod"),
        call("/cache/org-mono/branchX/pkg"),
        call("/cache/org-mono/branchX/pkg/go.mod"),
    ]

    # Suffix ending in 'X' (v2X), None package_name, missing suffix, or dot only outside host must be rejected
    non_siv_x = SourceCodeReference(
        repo_url="https://github.com/org/repo",
        branch="main",
        local_root_path="/cache/org-repo/main",
        local_full_path="/cache/org-repo/main/v2X",
    )
    assert (
        _strip_missing_go_major_version_suffix("github.com/org/repo/v2X", non_siv_x)
        is None
    )
    assert (
        _strip_missing_go_major_version_suffix("github.com/org/repo/v2", non_siv_x)
        is None
    )
    assert _strip_missing_go_major_version_suffix(None, root_with_slash) is None
    assert (
        _strip_missing_go_major_version_suffix("github.com/org/repo", root_with_slash)
        is None
    )
    assert (
        _strip_missing_go_major_version_suffix("@scope/pkg.js/v2", root_with_slash)
        is None
    )
    assert (
        _strip_missing_go_major_version_suffix("@example.org/v2", root_with_slash)
        is None
    )
    assert (
        _strip_missing_go_major_version_suffix("scope/pkg.js/v2", root_with_slash)
        is None
    )


def test_scancode_toolkit_skips_existence_check_when_local_full_path_empty(
    mocker: pytest_mock.MockFixture,
) -> None:
    """When local_full_path is empty, the path existence check is skipped and scanning proceeds."""
    path_exists_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
    )
    listdir_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        side_effect=[[], ["LICENSE"]],
    )
    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "MIT"
    }
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/repo",
        branch="main",
        local_root_path="cache/org-repo/main",
        local_full_path="",
    )
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        source_code_manager_mock,
        license_source_files=["LICENSE"],
        copyright_source_files=["NOTICE"],
    )
    initial_metadata = [
        Metadata(
            name="pkg",
            version=None,
            origin="https://github.com/org/repo",
            local_src_path=None,
            license=[],
            copyright=["Org"],
        )
    ]

    updated = strategy.augment_metadata(initial_metadata)

    assert updated[0].license == ["MIT"]
    path_exists_mock.assert_not_called()
    listdir_mock.assert_has_calls([call(""), call("cache/org-repo/main")])
    scancode_api_mock.get_licenses.assert_called_once_with(
        "cache/org-repo/main/LICENSE"
    )
