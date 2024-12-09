from unittest.mock import call, patch

import pytest
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy import (
    ScanCodeToolkitMetadataCollectionStrategy,
)


def test_scancode_toolkit_collection_strategy_skips_packages_with_license_and_copyright(
    mocker,
):
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

    license_files = ["license1", "license2"]
    copyright_files = ["copy1", "copy2"]
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        license_source_files=license_files, copyright_source_files=copyright_files
    )
    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == initial_metadata


def test_scancode_toolkit_collection_strategy_extracts_license_from_github_repos(
    mocker,
):
    class GitUrlParseMock:
        def __init__(self, valid, platform, owner, repo):
            self.valid = valid
            self.platform = platform
            self.owner = owner
            self.repo = repo
            self.path = None
            self.branch = None

        def url2https(self):
            return f"https://github.com/{self.owner}/{self.repo}"

    giturlparse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.parse_git_url",
        side_effect=[
            GitUrlParseMock(True, "gitlab", None, None),
            GitUrlParseMock(True, "github", "test_owner", "test_repo"),
        ],
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)
    system_mock = mocker.patch("os.system", return_value=0)
    listdir_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        return_value=["License1", "license2", "file1", "file2"],
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="non_githubt_test_purl",
            license=None,
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl",
            license=None,
            copyright=["Datadog Inc."],
        ),
    ]

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "APACHE-2.0"
    }

    license_files = ["license1", "LICENSE2", "license3"]
    copyright_files = ["copy1", "copy2"]
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        license_source_files=license_files, copyright_source_files=copyright_files
    )

    with patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=False,
    ) as mock_exists:
        updated_metadata = strategy.augment_metadata(initial_metadata)
        mock_exists.assert_called_once_with("test_temp_dir/test_owner-test_repo")

    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("test_temp_dir/test_owner-test_repo/License1"),
            call("test_temp_dir/test_owner-test_repo/license2"),
        ]
    )

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="non_githubt_test_purl",
            license=None,
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
    ]

    assert expected_metadata == updated_metadata

    giturlparse_mock.assert_has_calls(
        [mocker.call("non_githubt_test_purl"), mocker.call("github_test_purl")]
    )
    system_mock.assert_called_once_with(
        "git clone --depth 1 https://github.com/test_owner/test_repo test_temp_dir/test_owner-test_repo"
    )
    listdir_mock.assert_called_once_with("test_temp_dir/test_owner-test_repo")


def test_scancode_toolkit_collection_strategy_with_github_repository_failing_clone_raises_exception(
    mocker,
):
    class GitUrlParseMock:
        def __init__(self, valid, platform, owner, repo):
            self.valid = valid
            self.platform = platform
            self.owner = owner
            self.repo = repo
            self.path = None
            self.branch = None

        def url2https(self):
            return f"https://github.com/{self.owner}/{self.repo}"

    git_url_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
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
            copyright=["Datadog Inc."],
        ),
    ]

    license_files = ["license1", "license2"]
    copyright_files = ["copy1", "copy2"]
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        license_source_files=license_files, copyright_source_files=copyright_files
    )
    with pytest.raises(
        ValueError,
        match="Failed to clone repository: https://github.com/test_owner/test_repo",
    ):
        strategy.augment_metadata(initial_metadata)
    git_url_parse_mock.assert_called_once_with("github_test_purl")


def mock_get_copyrights_side_effect(path):
    if path == "test_temp_dir/test_owner-test_repo/copy1":
        return {
            "holders": [{"holder": "Datadog Inc."}],
            "authors": [{"author": "Datadog Authors"}],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        }
    elif path == "test_temp_dir/test_owner-test_repo/test_path_2/COPY2":
        return {
            "holders": [],
            "authors": [{"author": "Datadog Authors"}],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        }
    elif path == "test_temp_dir/test_owner-test_repo/test_path_3/copy1":
        return {
            "holders": [],
            "authors": [],
            "copyrights": [{"copyright": "Datadog Inc. 2024"}],
        }
    elif path == "test_temp_dir/test_owner-test_repo/test_path_4/copy1":
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


def test_scancode_toolkit_collection_strategy_extracts_copyright_from_github_repos(
    mocker,
):
    class GitUrlParseMock:
        def __init__(self, valid, platform, owner, repo):
            self.valid = valid
            self.platform = platform
            self.owner = owner
            self.repo = repo
            self.path = None
            self.branch = None

        def url2https(self):
            return f"https://github.com/{self.owner}/{self.repo}"

    git_url_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)

    license_files = ["license1", "LICENSE2"]
    copyright_files = ["Copy1", "copy2", "copy3"]
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        license_source_files=license_files, copyright_source_files=copyright_files
    )

    system_mock = mocker.patch("os.system", return_value=0)

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_copyrights.side_effect = mock_get_copyrights_side_effect

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            license=["APACHE-2.0"],
            copyright=None,
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            license=["APACHE-2.0"],
            copyright=None,
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            license=["APACHE-2.0"],
            copyright=None,
        ),
    ]

    walk_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.walk_directory"
    )
    mock_walk_return_value_side_effect = [
        [
            (
                "test_temp_dir/test_owner-test_repo",
                [],
                ["test_1", "test_2", "copy1", "COPY2"],
            ),
        ],
        [
            (
                "test_temp_dir/test_owner-test_repo/test_path_2",
                [],
                ["test_3", "test_4", "copy1", "COPY2"],
            ),
        ],
        [
            (
                "test_temp_dir/test_owner-test_repo/test_path_3",
                [],
                ["test_5", "test_6", "copy1", "COPY2"],
            ),
        ],
    ]

    walk_mock.side_effect = mock_walk_return_value_side_effect

    with patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=False,
    ) as mock_exists:
        updated_metadata = strategy.augment_metadata(initial_metadata)
        assert mock_exists.call_count == 3

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            license=["APACHE-2.0"],
            copyright=["Datadog Authors"],
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc. 2024"],
        ),
    ]

    assert expected_metadata == updated_metadata

    git_url_parse_mock.assert_has_calls(
        [
            mocker.call("github_test_purl_2"),
            mocker.call("github_test_purl_3"),
            mocker.call("github_test_purl_4"),
        ]
    )
    system_mock.assert_called_with(
        "git clone --depth 1 https://github.com/test_owner/test_repo test_temp_dir/test_owner-test_repo"
    )
    assert system_mock.call_count == 3

    walk_mock.assert_called_with("test_temp_dir/test_owner-test_repo")

    scancode_api_mock.get_copyrights.assert_has_calls(
        [
            call("test_temp_dir/test_owner-test_repo/copy1"),
            call("test_temp_dir/test_owner-test_repo/COPY2"),
            call("test_temp_dir/test_owner-test_repo/test_path_2/copy1"),
            call("test_temp_dir/test_owner-test_repo/test_path_2/COPY2"),
            call("test_temp_dir/test_owner-test_repo/test_path_3/copy1"),
            call("test_temp_dir/test_owner-test_repo/test_path_3/COPY2"),
        ]
    )


def test_scancode_toolkit_collection_strategy_receives_empty_filters_all_files_are_scanned(
    mocker,
):
    class GitUrlParseMock:
        def __init__(self, valid, platform, owner, repo):
            self.valid = valid
            self.platform = platform
            self.owner = owner
            self.repo = repo
            self.path = None
            self.branch = None

        def url2https(self):
            return f"https://github.com/{self.owner}/{self.repo}"

    git_url_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        license_source_files=None, copyright_source_files=None
    )

    system_mock = mocker.patch("os.system", return_value=0)

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_copyrights.side_effect = mock_get_copyrights_side_effect

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            license=["APACHE-2.0"],
            copyright=None,
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            license=["APACHE-2.0"],
            copyright=None,
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            license=["APACHE-2.0"],
            copyright=None,
        ),
    ]

    walk_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.walk_directory"
    )
    mock_walk_return_value_side_effect = [
        [
            (
                "test_temp_dir/test_owner-test_repo",
                [],
                ["test_1", "test_2", "copy1", "COPY2"],
            ),
        ],
        [
            (
                "test_temp_dir/test_owner-test_repo/test_path_2",
                [],
                ["test_3", "test_4", "copy1", "COPY2"],
            ),
        ],
        [
            (
                "test_temp_dir/test_owner-test_repo/test_path_3",
                [],
                ["test_5", "test_6", "copy1", "COPY2"],
            ),
        ],
    ]

    walk_mock.side_effect = mock_walk_return_value_side_effect

    with patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        return_value=False,
    ) as mock_exists:
        updated_metadata = strategy.augment_metadata(initial_metadata)
        assert mock_exists.call_count == 3

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_3",
            license=["APACHE-2.0"],
            copyright=["Datadog Authors"],
        ),
        Metadata(
            name="package4",
            version=None,
            origin="github_test_purl_4",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc. 2024"],
        ),
    ]

    assert expected_metadata == updated_metadata

    git_url_parse_mock.assert_has_calls(
        [
            mocker.call("github_test_purl_2"),
            mocker.call("github_test_purl_3"),
            mocker.call("github_test_purl_4"),
        ]
    )
    system_mock.assert_called_with(
        "git clone --depth 1 https://github.com/test_owner/test_repo test_temp_dir/test_owner-test_repo"
    )
    assert system_mock.call_count == 3

    walk_mock.assert_called_with("test_temp_dir/test_owner-test_repo")

    scancode_api_mock.get_copyrights.assert_has_calls(
        [
            call("test_temp_dir/test_owner-test_repo/test_1"),
            call("test_temp_dir/test_owner-test_repo/test_2"),
            call("test_temp_dir/test_owner-test_repo/copy1"),
            call("test_temp_dir/test_owner-test_repo/COPY2"),
            call("test_temp_dir/test_owner-test_repo/test_path_2/test_3"),
            call("test_temp_dir/test_owner-test_repo/test_path_2/test_4"),
            call("test_temp_dir/test_owner-test_repo/test_path_2/copy1"),
            call("test_temp_dir/test_owner-test_repo/test_path_2/COPY2"),
            call("test_temp_dir/test_owner-test_repo/test_path_3/test_5"),
            call("test_temp_dir/test_owner-test_repo/test_path_3/test_6"),
            call("test_temp_dir/test_owner-test_repo/test_path_3/copy1"),
            call("test_temp_dir/test_owner-test_repo/test_path_3/COPY2"),
        ]
    )


def test_scancode_toolkit_collection_strategy_do_not_mix_up_pre_cloned_repos(mocker):
    class GitUrlParseMock:
        def __init__(self, valid, platform, owner, repo):
            self.valid = valid
            self.platform = platform
            self.owner = owner
            self.repo = repo
            self.path = None
            self.branch = None

        def url2https(self):
            return f"https://github.com/{self.owner}/{self.repo}"

    git_url_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.parse_git_url",
        side_effect=[
            GitUrlParseMock(True, "github", "test_owner", "test_repo"),
            GitUrlParseMock(True, "github", "test_owner2", "test_repo2"),
            GitUrlParseMock(True, "github", "test_owner", "test_repo"),
        ],
    )

    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)

    system_mock = mocker.patch("os.system", return_value=0)

    listdir_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.list_dir",
        side_effect=[["License1"], ["license2"], ["License1", "file2"]],
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license=None,
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            license=None,
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_1",
            license=None,
            copyright=["Datadog Inc."],
        ),
    ]

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_licenses.return_value = {
        "detected_license_expression_spdx": "APACHE-2.0"
    }

    license_files = ["license1", "LICENSE2"]
    copyright_files = ["Copy1", "copy2", "copy3"]
    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        license_source_files=license_files, copyright_source_files=copyright_files
    )

    with patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        side_effect=[False, False, True],
    ) as mock_exists:
        updated_metadata = strategy.augment_metadata(initial_metadata)
        assert mock_exists.call_count == 3

    scancode_api_mock.get_licenses.assert_has_calls(
        [
            call("test_temp_dir/test_owner-test_repo/License1"),
            call("test_temp_dir/test_owner2-test_repo2/license2"),
            call("test_temp_dir/test_owner-test_repo/License1"),
        ]
    )

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package2",
            version=None,
            origin="github_test_purl_2",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
        Metadata(
            name="package3",
            version=None,
            origin="github_test_purl_1",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        ),
    ]

    assert expected_metadata == updated_metadata

    git_url_parse_mock.assert_has_calls(
        [
            mocker.call("github_test_purl_1"),
            mocker.call("github_test_purl_2"),
            mocker.call("github_test_purl_1"),
        ]
    )
    system_mock.assert_has_calls(
        [
            call(
                "git clone --depth 1 https://github.com/test_owner/test_repo test_temp_dir/test_owner-test_repo"
            ),
            call(
                "git clone --depth 1 https://github.com/test_owner2/test_repo2 test_temp_dir/test_owner2-test_repo2"
            ),
        ]
    )
    listdir_mock.assert_has_calls(
        [
            call("test_temp_dir/test_owner-test_repo"),
            call("test_temp_dir/test_owner2-test_repo2"),
            call("test_temp_dir/test_owner-test_repo"),
        ]
    )


def test_scancode_toolkit_collection_strategy_pathed_dependencies_are_not_scanned_at_root(
    mocker,
):
    class GitUrlParseMock:
        def __init__(self, valid, platform, owner, repo, path):
            self.valid = valid
            self.platform = platform
            self.owner = owner
            self.repo = repo
            self.path = path
            self.branch = None

        def url2https(self):
            return f"https://github.com/{self.owner}/{self.repo}"

    git_url_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            True, "github", "test_owner", "test_repo", "/test_path_4"
        ),
    )
    temp_dir_object = mocker.Mock()
    temp_dir_object.name = "test_temp_dir"
    mocker.patch("tempfile.TemporaryDirectory", return_value=temp_dir_object)

    strategy = ScanCodeToolkitMetadataCollectionStrategy(
        license_source_files=None, copyright_source_files=None
    )

    system_mock = mocker.patch("os.system", return_value=0)

    scancode_api_mock = mocker.patch("scancode.api")
    scancode_api_mock.get_copyrights.side_effect = mock_get_copyrights_side_effect

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license=["APACHE-2.0"],
            copyright=None,
        ),
    ]

    walk_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.walk_directory"
    )
    mock_walk_return_value_side_effect = [
        [
            (
                "test_temp_dir/test_owner-test_repo",
                [],
                ["test_1", "test_2", "COPY2"],
            ),
            (
                "test_temp_dir/test_owner-test_repo/test_path_2",
                [],
                ["test_3", "test_4", "COPY2"],
            ),
            (
                "test_temp_dir/test_owner-test_repo/test_path_3",
                [],
                ["test_5", "test_6", "COPY2"],
            ),
            (
                "test_temp_dir/test_owner-test_repo/test_path_4",
                [],
                ["test_7", "test_8", "copy1"],
            ),
        ],
    ]

    walk_mock.side_effect = mock_walk_return_value_side_effect

    with patch(
        "ospo_tools.metadata_collector.strategies.scan_code_toolkit_metadata_collection_strategy.path_exists",
        side_effect=[False, False, True],
    ) as mock_exists:
        updated_metadata = strategy.augment_metadata(initial_metadata)
        assert mock_exists.call_count == 1

    expected_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="github_test_purl_1",
            license=["APACHE-2.0"],
            copyright=["An individual"],
        ),
    ]

    assert expected_metadata == updated_metadata

    git_url_parse_mock.assert_called_once_with("github_test_purl_1")
    system_mock.assert_called_with(
        "git clone --depth 1 https://github.com/test_owner/test_repo test_temp_dir/test_owner-test_repo"
    )
    assert system_mock.call_count == 1

    walk_mock.assert_called_with("test_temp_dir/test_owner-test_repo")

    scancode_api_mock.get_copyrights.assert_has_calls(
        [
            call("test_temp_dir/test_owner-test_repo/test_1"),
            call("test_temp_dir/test_owner-test_repo/test_2"),
            call("test_temp_dir/test_owner-test_repo/COPY2"),
            call("test_temp_dir/test_owner-test_repo/test_path_4/test_7"),
            call("test_temp_dir/test_owner-test_repo/test_path_4/test_8"),
            call("test_temp_dir/test_owner-test_repo/test_path_4/copy1"),
        ]
    )
