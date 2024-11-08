import os
from unittest.mock import call, patch

import pytest
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy import (
    ScanCodeToolkitMetadataCollectionStrategy,
)
from scancode.api import get_licenses


def test_scancode_toolkit_collection_strategy_skips_packages_with_license_and_copyright(
    mocker,
):
    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="test_purl",
            license="APACHE-2.0",
            copyright="Datadog Inc.",
        )
    ]

    strategy = ScanCodeToolkitMetadataCollectionStrategy()
    updated_metadata = strategy.augment_metadata(initial_metadata)
    del strategy  # to call __del__ method

    assert updated_metadata == initial_metadata

    temp_dir_object.cleanup.assert_called_once()


def mock_exists_side_effect_false(path):
    # Only return True for the specific path you want to mock
    if path.startswith("test_temp_dir/owner-repo"):
        return False
    # For all other paths, call the original `os.path.exists`
    return os.path.exists(path)


def test_scancode_toolkit_collection_strategy_extracts_license_from_github_repos(
    mocker,
):
    purl_parser_object = mocker.Mock()
    purl_parser_object.get_github_owner_and_repo.side_effect = [
        (None, None),
        ("owner", "repo"),
    ]
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)
    system_mock = mocker.patch("os.system", return_value=0)
    listdir_mock = mocker.patch("os.listdir", return_value=["file1", "file2"])

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="non_githubt_test_purl",
            license=None,
            copyright="Datadog Inc.",
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl",
            license=None,
            copyright="Datadog Inc.",
        ),
    ]

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "APACHE-2.0"
    }

    strategy = ScanCodeToolkitMetadataCollectionStrategy()

    with patch(
        "os.path.exists", side_effect=mock_exists_side_effect_false
    ) as mock_exists:
        updated_metadata = strategy.augment_metadata(initial_metadata)
        mock_exists.assert_called_once_with("test_temp_dir/owner-repo")

    del strategy  # to call __del__ method

    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("test_temp_dir/owner-repo/file1"),
            call("test_temp_dir/owner-repo/file2"),
        ]
    )

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="non_githubt_test_purl",
            license=None,
            copyright="Datadog Inc.",
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl",
            license="APACHE-2.0",
            copyright="Datadog Inc.",
        ),
    ]

    assert updated_metadata == expected_metadata

    purl_parser_object.get_github_owner_and_repo.assert_has_calls(
        [
            mocker.call("non_githubt_test_purl"),
            mocker.call("github_test_purl"),
        ]
    )
    system_mock.assert_called_once_with(
        "git clone --depth 1 https://github.com/owner/repo test_temp_dir/owner-repo"
    )
    listdir_mock.assert_called_once_with("test_temp_dir/owner-repo")

    temp_dir_object.cleanup.assert_called_once()


def test_scancode_toolkit_collection_strategy_with_github_repository_failing_clone_raises_exception(
    mocker,
):
    purl_parser_object = mocker.Mock()
    purl_parser_object.get_github_owner_and_repo.side_effect = [
        ("owner", "repo"),
    ]
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)
    mocker.patch("os.system", return_value=1)

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl",
            license=None,
            copyright="Datadog Inc.",
        ),
    ]

    strategy = ScanCodeToolkitMetadataCollectionStrategy()
    with pytest.raises(
        ValueError, match="Failed to clone repository: https://github.com/owner/repo"
    ):
        strategy.augment_metadata(initial_metadata)


def test_scancode_toolkit_collection_strategy_extracts_copyright_from_github_repos(
    mocker,
):
    purl_parser_object = mocker.Mock()
    purl_parser_object.get_github_owner_and_repo.return_value = ("owner", "repo")
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)

    strategy = ScanCodeToolkitMetadataCollectionStrategy()

    system_mock = mocker.patch("os.system", return_value=0)

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_copyrights.side_effect = [
        {
            "holders": [{"holder": "Datadog Inc."}],
            "authors": [{"author": "Datadog Authors"}],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        },
        {
            "holders": [],
            "authors": [],
            "copyrights": [],
        },
        {
            "holders": [],
            "authors": [{"author": "Datadog Authors"}],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        },
        {
            "holders": [],
            "authors": [],
            "copyrights": [],
        },
        {
            "holders": [],
            "authors": [],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        },
        {
            "holders": [],
            "authors": [],
            "copyrights": [],
        },
    ]

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license="APACHE-2.0",
            copyright="Datadog Inc.",
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            license="APACHE-2.0",
            copyright=None,
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            license="APACHE-2.0",
            copyright=None,
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            license="APACHE-2.0",
            copyright=None,
        ),
    ]


    mock_walk_return_value = [
        (
            "test_path",
            [],
            ["test_1", "test_2"],
        ),  # Simulates one directory with two files
    ]

    walk_mock = mocker.patch("os.walk", return_value=mock_walk_return_value)

    with patch(
        "os.path.exists", side_effect=mock_exists_side_effect_false
    ) as mock_exists:
        updated_metadata = strategy.augment_metadata(initial_metadata)
        mock_exists.assert_called_with("test_temp_dir/owner-repo")

    del strategy  # to call __del__ method

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license="APACHE-2.0",
            copyright="Datadog Inc.",
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            license="APACHE-2.0",
            copyright="Datadog Inc.",
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            license="APACHE-2.0",
            copyright="Datadog Authors",
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            license="APACHE-2.0",
            copyright="Datadog Inc. 2024",
        ),
    ]

    assert updated_metadata == expected_metadata

    purl_parser_object.get_github_owner_and_repo.assert_has_calls(
        [
            mocker.call("github_test_purl_2"),
            mocker.call("github_test_purl_3"),
            mocker.call("github_test_purl_4"),
        ]
    )
    system_mock.assert_called_with(
        "git clone --depth 1 https://github.com/owner/repo test_temp_dir/owner-repo"
    )
    assert system_mock.call_count == 3

    walk_mock.assert_called_with("test_temp_dir/owner-repo")
    assert walk_mock.call_count == 3
    temp_dir_object.cleanup.assert_called_once()
