# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from unittest.mock import call

import pytest_mock
from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from functools import partial
from dd_license_attribution.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy import (
    ScanCodeToolkitMetadataCollectionStrategy,
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
