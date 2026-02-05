# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from datetime import datetime
from typing import Any  # used for auxiliary testing function only
from unittest.mock import Mock, call, patch

import pytest

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    MirrorSpec,
    RefType,
    SourceCodeManager,
)


class GitUrlParseMock:
    def __init__(
        self,
        valid: bool,
        owner: str,
        repo: str,
        branch: str,
        path: str,
        path_raw: str,
    ):
        self.valid = valid
        self.protocol = "https"
        self.host = "github.com" if valid else "non_github.com"
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.path_raw = path
        self.path_raw = path_raw
        self.github = valid


def create_github_client_mock() -> Any:
    github_client_mock = Mock()
    repo_mock = Mock()
    html_url: str = "https://github.com/test_owner/test_repo"
    api_url: str = "https://api.github.com/repos/test_owner/test_repo"
    status: int = 200

    repo_mock.get.return_value = (
        status,
        {
            "html_url": html_url,
            "url": api_url,
        },
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock
    return github_client_mock


@pytest.mark.parametrize(
    "resource_url, expected_results, mocked_parser_results",
    [
        (
            "https://github.com/test_owner/test_repo/blob/test_branch/dir/file",
            (
                "https://github.com/test_owner/test_repo",
                "test_branch",
                "/dir",
                "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
            ),
            GitUrlParseMock(
                valid=True,
                owner="test_owner",
                repo="test_repo",
                path="test_branch/dir/file",
                branch="",
                path_raw="/blob/test_branch/dir/file",
            ),
        ),
        (
            "https://github.com/test_owner/test_repo/tree/test_branch/dir",
            (
                "https://github.com/test_owner/test_repo",
                "test_branch",
                "/dir",
                "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
            ),
            GitUrlParseMock(
                valid=True,
                owner="test_owner",
                repo="test_repo",
                branch="test_branch/dir",
                path="",
                path_raw="/tree/test_branch/dir",
            ),
        ),
        (
            "https://github.com/test_owner/test_repo/tree/test_branch",
            (
                "https://github.com/test_owner/test_repo",
                "test_branch",
                "",
                "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
            ),
            GitUrlParseMock(
                valid=True,
                owner="test_owner",
                repo="test_repo",
                branch="test_branch",
                path="",
                path_raw="/tree/test_branch",
            ),
        ),
        (
            "https://github.com/test_owner/test_repo/tree/test_tag",
            (
                "https://github.com/test_owner/test_repo",
                "test_tag",
                "",
                "cache_dir/20220101_000000Z/test_owner-test_repo/test_tag",
            ),
            GitUrlParseMock(
                valid=True,
                owner="test_owner",
                repo="test_repo",
                branch="test_tag",
                path="",
                path_raw="/tree/test_tag",
            ),
        ),
        (
            "https://github.com/test_owner/test_repo",
            (
                "https://github.com/test_owner/test_repo",
                "main",
                "",
                "cache_dir/20220101_000000Z/test_owner-test_repo/main",
            ),
            GitUrlParseMock(
                valid=True,
                owner="test_owner",
                repo="test_repo",
                branch="",
                path="",
                path_raw="",
            ),
        ),
    ],
)
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
def test_source_code_manager_get_non_cached_code(
    run_command_mock: Mock,
    output_from_command_mock: Mock,
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    artifact_file_exists_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    resource_url: str,
    expected_results: tuple[str, str, str, str],
    mocked_parser_results: GitUrlParseMock,
) -> None:
    (
        expected_clone_url,
        expected_branch,
        expected_directory,
        expected_local_path_root,
    ) = expected_results
    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch=expected_branch,
        local_root_path=f"{expected_local_path_root}",
        local_full_path=f"{expected_local_path_root}{expected_directory}",
    )

    # Configure mocks
    github_client_mock = create_github_client_mock()
    run_command_mock.return_value = 0
    output_from_command_mock.return_value = (
        "ref: refs/heads/main\tHEAD\n72a11341aa684010caf1ca5dee779f0e7e84dfe9\tHEAD\n"
    )
    get_datetime_now_mock.side_effect = [
        datetime.fromisoformat("2022-01-01T00:00:00+00:00")
    ]
    git_url_parse_mock.return_value = mocked_parser_results
    artifact_file_exists_mock.return_value = True
    artifact_list_dir_mock.return_value = []
    source_code_list_dir_mock.return_value = []

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    code_ref = source_code_manager.get_code(resource_url)

    assert code_ref == expected_source_code_reference
    if mocked_parser_results.path_raw != "":
        run_command_mock.assert_has_calls(
            [
                call(
                    f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
                ),
                call(
                    f"git clone -c advice.detachedHead=False --depth 1 --branch={expected_branch} {expected_clone_url} {expected_local_path_root}"
                ),
            ]
        )
    if (
        mocked_parser_results.branch == ""
        and not "test_branch" in mocked_parser_results.path_raw
    ):
        output_from_command_mock.assert_called_once_with(
            f"git ls-remote --symref {expected_source_code_reference.repo_url} HEAD"
        )
    assert get_datetime_now_mock.call_count == 1
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    artifact_file_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_get_cached_code(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_mock: Mock,
    path_exists_source_code_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    # Configure mocks
    get_datetime_now_mock.return_value = datetime.fromisoformat(
        "2022-01-01T00:00:00+00:00"
    )
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="test_branch",
        path="test_dir",
        path_raw="/tree/test_branch/test_dir",
    )
    path_exists_mock.return_value = True
    path_exists_source_code_mock.return_value = True
    artifact_list_dir_mock.return_value = ["20211231_001000Z"]
    source_code_list_dir_mock.return_value = ["20211231_001000Z"]
    run_command_mock.return_value = 0

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)
    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20211231_001000Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20211231_001000Z/test_owner-test_repo/test_branch/test_dir",
    )

    assert code_ref == expected_source_code_reference
    assert get_datetime_now_mock.call_count == 1
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    path_exists_mock.assert_called_once_with("cache_dir")
    path_exists_source_code_mock.assert_called_once_with(
        "cache_dir/20211231_001000Z/test_owner-test_repo/test_branch"
    )
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")

    run_command_mock.assert_called_once_with(
        f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
    )


@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_get_non_cached_code_because_it_expired(
    get_datetime_now_mock: Mock,
    mock_create_dirs: Mock,
    git_url_parse_mock: Mock,
    path_exists_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    # Configure mocks
    get_datetime_now_mock.side_effect = [
        datetime.fromisoformat("2022-01-01T00:00:00+00:00")
    ]
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="test_branch",
        path="test_dir",
        path_raw="/tree/test_branch/test_dir",
    )
    path_exists_mock.return_value = True
    artifact_list_dir_mock.return_value = ["20210101_000000Z"]
    source_code_list_dir_mock.return_value = ["20210101_000000Z"]
    run_command_mock.return_value = 0

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)
    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch/test_dir",
    )
    expected_cache_dir = "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch"

    assert code_ref == expected_source_code_reference
    assert get_datetime_now_mock.call_count == 1
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")

    run_command_mock.assert_has_calls(
        [
            call(
                f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
            ),
            call(
                f"git clone -c advice.detachedHead=False --depth 1 --branch={expected_source_code_reference.branch} {expected_source_code_reference.repo_url} {expected_cache_dir}"
            ),
        ]
    )
    mock_create_dirs.assert_called_once_with(expected_cache_dir)


@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_get_non_cached_code_because_force_update(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_mock: Mock,
    run_command_mock: Mock,
    artifact_mock_list_dir: Mock,
    source_code_mock_list_dir: Mock,
    mock_create_dirs: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    # Configure mocks
    get_datetime_now_mock.side_effect = [
        datetime.fromisoformat("2022-01-01T00:00:05+00:00")
    ]
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="test_branch",
        path="test_dir",
        path_raw="/tree/test_branch/test_dir",
    )
    path_exists_mock.return_value = True
    run_command_mock.return_value = 0
    artifact_mock_list_dir.return_value = ["20210101_000000Z"]
    source_code_mock_list_dir.return_value = ["20210101_000000Z"]

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)
    code_ref = source_code_manager.get_code(request_url, force_update=True)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20220101_000005Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20220101_000005Z/test_owner-test_repo/test_branch/test_dir",
    )
    expected_cache_dir = "cache_dir/20220101_000005Z/test_owner-test_repo/test_branch"

    assert code_ref == expected_source_code_reference
    assert get_datetime_now_mock.call_count == 1
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    path_exists_mock.assert_called_once_with("cache_dir")
    artifact_mock_list_dir.assert_called_once_with("cache_dir")
    source_code_mock_list_dir.assert_called_once_with("cache_dir")

    mock_create_dirs.assert_called_once_with(expected_cache_dir)

    run_command_mock.assert_has_calls(
        [
            call(
                f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
            ),
            call(
                f"git clone -c advice.detachedHead=False --depth 1 --branch={expected_source_code_reference.branch} {expected_source_code_reference.repo_url} {expected_cache_dir}"
            ),
        ]
    )


@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
def test_non_github_returns_none(
    git_url_parse_mock: Mock,
    mock_path_exists: Mock,
    mock_list_dir: Mock,
) -> None:
    # Configure mocks
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=False,
        owner="",
        repo="",
        branch="",
        path="",
        path_raw="",
    )
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []

    source_code_manager = SourceCodeManager("cache_dir", Mock(), 86400)
    request_url = (
        "https://non_github.com/test_owner/test_repo/tree/test_branch/test_dir"
    )
    code_ref = source_code_manager.get_code(request_url)

    assert code_ref is None
    assert git_url_parse_mock.call_count == 1  # Only called once before early return
    mock_path_exists.assert_called_once_with("cache_dir")
    mock_list_dir.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_artifact_manager_get_non_cached_code_for_ambiguous_branch_names(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    # Configure mocks
    get_datetime_now_mock.return_value = datetime.fromisoformat(
        "2022-01-01T00:00:00+00:00"
    )
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="test_branch/test_dir",
        path="",
        path_raw="/tree/test_branch/test_dir",
    )
    path_exists_mock.return_value = True
    artifact_list_dir_mock.return_value = ["20210101_000000Z"]
    source_code_list_dir_mock.return_value = ["20210101_000000Z"]
    run_command_mock.return_value = 0

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch/test_dir",
    )

    assert code_ref == expected_source_code_reference
    assert get_datetime_now_mock.call_count == 1
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")

    assert run_command_mock.call_count == 2
    run_command_mock.assert_has_calls(
        [
            call(
                f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
            ),
            call(
                f"git clone -c advice.detachedHead=False --depth 1 --branch={expected_source_code_reference.branch} {expected_source_code_reference.repo_url} {expected_source_code_reference.local_root_path}"
            ),
        ]
    )


@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_source_code_manager_fails_init_if_cache_dir_is_not_a_directory(
    path_exists_mock: Mock,
) -> None:
    path_exists_mock.return_value = False

    with pytest.raises(ValueError) as e:
        SourceCodeManager("cache_dir", Mock(), 86400)

    assert str(e.value) == "Local cache directory cache_dir does not exist"
    path_exists_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_source_code_manager_fails_init_if_cache_dir_contains_unexpected_files(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
) -> None:
    path_exists_mock.return_value = True
    list_dir_mock.return_value = ["unexpected_file"]

    with pytest.raises(ValueError) as e:
        SourceCodeManager("cache_dir", Mock(), 86400)

    assert (
        str(e.value)
        == "Local cache directory cache_dir has invalid subdirectory, are you sure it is a cache directory?"
    )
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_with_mirror_url(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    # Configure mocks
    get_datetime_now_mock.return_value = datetime.fromisoformat(
        "2022-01-01T00:00:00+00:00"
    )
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="test_branch",
        path="test_dir",
        path_raw="/tree/test_branch/test_dir",
    )
    path_exists_artifact_mock.return_value = True
    path_exists_source_code_mock.return_value = False
    run_command_mock.return_value = 0

    mirror_spec = MirrorSpec(
        original_url="https://github.com/test_owner/test_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
    )
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=[mirror_spec]
    )
    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch/test_dir",
    )
    expected_cache_dir = "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch"

    assert code_ref == expected_source_code_reference
    get_datetime_now_mock.assert_called_once()
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    path_exists_artifact_mock.assert_called_once_with("cache_dir")
    path_exists_source_code_mock.assert_called_once_with(expected_cache_dir)
    mock_create_dirs.assert_called_once_with(expected_cache_dir)
    run_command_mock.assert_has_calls(
        [
            call(
                f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
            ),
            call(
                f"git clone -c advice.detachedHead=False --depth 1 --branch={expected_source_code_reference.branch} https://github.com/mirror_owner/mirror_repo {expected_cache_dir}"
            ),
        ]
    )


@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_with_mirror_ref_mapping(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    # Configure mocks
    get_datetime_now_mock.return_value = datetime.fromisoformat(
        "2022-01-01T00:00:00+00:00"
    )
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="test_branch",
        path="test_dir",
        path_raw="/tree/test_branch/test_dir",
    )
    path_exists_artifact_mock.return_value = True
    path_exists_source_code_mock.return_value = False
    run_command_mock.return_value = 0

    mirror_spec = MirrorSpec(
        original_url="https://github.com/test_owner/test_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
        ref_mapping={
            (RefType.BRANCH, "test_branch"): (RefType.BRANCH, "mirror_branch")
        },
    )
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=[mirror_spec]
    )
    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch/test_dir",
    )
    expected_cache_dir = "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch"

    assert code_ref == expected_source_code_reference
    get_datetime_now_mock.assert_called_once()
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    path_exists_artifact_mock.assert_called_once_with("cache_dir")
    path_exists_source_code_mock.assert_called_once_with(expected_cache_dir)
    mock_create_dirs.assert_called_once_with(expected_cache_dir)
    run_command_mock.assert_has_calls(
        [
            call(
                f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
            ),
            call(
                f"git clone -c advice.detachedHead=False --depth 1 --branch=mirror_branch https://github.com/mirror_owner/mirror_repo {expected_cache_dir}"
            ),
        ]
    )


@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_with_unsupported_ref_type(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    run_command_mock: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    # Configure mocks
    get_datetime_now_mock.return_value = datetime.fromisoformat(
        "2022-01-01T00:00:00+00:00"
    )
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="test_branch",
        path="test_dir",
        path_raw="/tree/test_branch/test_dir",
    )
    path_exists_artifact_mock.return_value = True
    run_command_mock.return_value = 0

    mirror_spec = MirrorSpec(
        original_url="https://github.com/test_owner/test_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
        ref_mapping={(RefType.BRANCH, "test_branch"): (RefType.TAG, "v1.0")},
    )
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=[mirror_spec]
    )

    with pytest.raises(NotImplementedError) as e:
        source_code_manager.get_code(request_url)

    assert (
        str(e.value)
        == "Mirror reference type RefType.TAG is not yet implemented. Only branch-to-branch mapping is supported."
    )
    get_datetime_now_mock.assert_called_once()
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (before failure)
    path_exists_artifact_mock.assert_called_once_with("cache_dir")
    run_command_mock.assert_called_once_with(
        f"git ls-remote https://github.com/test_owner/test_repo test_branch | grep -q test_branch"
    )


@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_with_mirror_url_and_ref_mapping_for_the_default_branch(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    run_command_mock: Mock,
    output_from_command_mock: Mock,
    mock_create_dirs: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo"

    # Configure mocks
    get_datetime_now_mock.return_value = datetime.fromisoformat(
        "2022-01-01T00:00:00+00:00"
    )
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="",
        path="",
        path_raw="",
    )
    path_exists_artifact_mock.return_value = True
    path_exists_source_code_mock.return_value = False
    run_command_mock.return_value = 0
    output_from_command_mock.return_value = (
        "ref: refs/heads/main\tHEAD\n72a11341aa684010caf1ca5dee779f0e7e84dfe9\tHEAD\n"
    )

    mirror_spec = MirrorSpec(
        original_url="https://github.com/test_owner/test_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
        ref_mapping={(RefType.BRANCH, "main"): (RefType.BRANCH, "development")},
    )
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=[mirror_spec]
    )
    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="main",
        local_root_path="cache_dir/20220101_000000Z/test_owner-test_repo/main",
        local_full_path="cache_dir/20220101_000000Z/test_owner-test_repo/main",
    )
    expected_cache_dir = "cache_dir/20220101_000000Z/test_owner-test_repo/main"

    assert code_ref == expected_source_code_reference
    get_datetime_now_mock.assert_called_once()
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (first call), in get_canonical_urls, in get_code (after default branch resolved)
    path_exists_artifact_mock.assert_called_once_with("cache_dir")
    path_exists_source_code_mock.assert_called_once_with(expected_cache_dir)
    mock_create_dirs.assert_called_once_with(expected_cache_dir)
    output_from_command_mock.assert_called_once_with(
        f"git ls-remote --symref {expected_source_code_reference.repo_url} HEAD"
    )
    run_command_mock.assert_called_once_with(
        f"git clone -c advice.detachedHead=False --depth 1 --branch=development https://github.com/mirror_owner/mirror_repo {expected_cache_dir}"
    )


@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_with_multiple_mirrors(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    # Configure mocks
    get_datetime_now_mock.return_value = datetime.fromisoformat(
        "2022-01-01T00:00:00+00:00"
    )
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="test_branch",
        path="test_dir",
        path_raw="/tree/test_branch/test_dir",
    )
    path_exists_artifact_mock.return_value = True
    path_exists_source_code_mock.return_value = False
    run_command_mock.return_value = 0

    mirror_specs = [
        MirrorSpec(
            original_url="https://github.com/other_owner/other_repo",
            mirror_url="https://github.com/other_mirror/other_mirror_repo",
        ),
        MirrorSpec(
            original_url="https://github.com/test_owner/test_repo",
            mirror_url="https://github.com/mirror_owner/mirror_repo",
            ref_mapping={
                (RefType.BRANCH, "test_branch"): (RefType.BRANCH, "mirror_branch")
            },
        ),
    ]
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=mirror_specs
    )
    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch/test_dir",
    )
    expected_cache_dir = "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch"

    assert code_ref == expected_source_code_reference
    get_datetime_now_mock.assert_called_once()
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    path_exists_artifact_mock.assert_called_once_with("cache_dir")
    path_exists_source_code_mock.assert_called_once_with(expected_cache_dir)
    mock_create_dirs.assert_called_once_with(expected_cache_dir)
    run_command_mock.assert_has_calls(
        [
            call(
                f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
            ),
            call(
                f"git clone -c advice.detachedHead=False --depth 1 --branch=mirror_branch https://github.com/mirror_owner/mirror_repo {expected_cache_dir}"
            ),
        ]
    )


@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_with_no_mirror_match(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    # Configure mocks
    get_datetime_now_mock.return_value = datetime.fromisoformat(
        "2022-01-01T00:00:00+00:00"
    )
    github_client_mock = create_github_client_mock()
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="test_branch",
        path="test_dir",
        path_raw="/tree/test_branch/test_dir",
    )
    path_exists_artifact_mock.return_value = True
    path_exists_source_code_mock.return_value = False
    run_command_mock.return_value = 0

    mirror_spec = MirrorSpec(
        original_url="https://github.com/other_owner/other_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
    )
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=[mirror_spec]
    )
    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch/test_dir",
    )
    expected_cache_dir = "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch"

    assert code_ref == expected_source_code_reference
    get_datetime_now_mock.assert_called_once()
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    path_exists_artifact_mock.assert_called_once_with("cache_dir")
    path_exists_source_code_mock.assert_called_once_with(expected_cache_dir)
    mock_create_dirs.assert_called_once_with(expected_cache_dir)
    run_command_mock.assert_has_calls(
        [
            call(
                f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
            ),
            call(
                f"git clone -c advice.detachedHead=False --depth 1 --branch={expected_source_code_reference.branch} {expected_source_code_reference.repo_url} {expected_cache_dir}"
            ),
        ]
    )


# Tests for get_canonical_urls function


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
def test_get_canonical_urls_with_redirected_repository(
    git_url_parse_mock: Mock,
) -> None:
    """Test that get_canonical_urls follows redirects for renamed repositories."""
    # Configure parse_git_url mock
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="DataDog",
        repo="ospo-tools",
        branch="",
        path="",
        path_raw="",
    )

    # Mock the GitHub client
    github_client_mock = Mock()

    # First API call returns 301 redirect
    # Response based on actual API call to DataDog/ospo-tools
    redirect_response = {
        "message": "Moved Permanently",
        "url": "https://api.github.com/repositories/848318405",
        "documentation_url": "https://docs.github.com/rest",
    }

    # Set up the mock for repos["DataDog"]["ospo-tools"].get()
    owner_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (301, redirect_response)
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    # Second API call (following redirect) returns 200 with repository data
    # Response based on actual API call following the redirect
    final_response = {
        "full_name": "DataDog/dd-license-attribution",
        "html_url": "https://github.com/DataDog/dd-license-attribution",
        "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
        "owner": {"login": "DataDog"},
        "name": "dd-license-attribution",
    }

    # Mock the endpoint navigation for the redirect (repositories/848318405)
    repo_id_mock = Mock()
    repo_id_mock.get.return_value = (200, final_response)

    def getitem_side_effect(key):  # type: ignore[no-untyped-def]
        if key == "repositories":
            repositories_mock = Mock()
            repositories_mock.__getitem__ = Mock(return_value=repo_id_mock)
            return repositories_mock
        return Mock()

    github_client_mock.__getitem__ = Mock(side_effect=getitem_side_effect)

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    canonical_url, api_url = source_code_manager.get_canonical_urls(
        "https://github.com/DataDog/ospo-tools"
    )

    assert canonical_url == "https://github.com/DataDog/dd-license-attribution"
    assert api_url == "https://api.github.com/repos/DataDog/dd-license-attribution"
    assert git_url_parse_mock.call_count == 1  # Only called once in get_canonical_urls


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
def test_get_canonical_urls_with_non_redirected_repository(
    git_url_parse_mock: Mock,
) -> None:
    """Test that get_canonical_urls returns correct URLs for non-redirected repositories."""
    # Configure parse_git_url mock
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="DataDog",
        repo="dd-license-attribution",
        branch="",
        path="",
        path_raw="",
    )

    # Mock the GitHub client
    github_client_mock = Mock()

    # API call returns 200 with repository data
    # Response based on actual API call to DataDog/dd-license-attribution
    response = {
        "full_name": "DataDog/dd-license-attribution",
        "html_url": "https://github.com/DataDog/dd-license-attribution",
        "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
    }

    # Set up the mock for repos["DataDog"]["dd-license-attribution"].get()
    owner_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (200, response)
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    canonical_url, api_url = source_code_manager.get_canonical_urls(
        "https://github.com/DataDog/dd-license-attribution"
    )

    assert canonical_url == "https://github.com/DataDog/dd-license-attribution"
    assert api_url == "https://api.github.com/repos/DataDog/dd-license-attribution"
    assert git_url_parse_mock.call_count == 1  # Only called once in get_canonical_urls


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
def test_get_canonical_urls_with_non_github_url(
    git_url_parse_mock: Mock,
) -> None:
    """Test that get_canonical_urls returns original URL for non-GitHub URLs."""
    # Configure parse_git_url mock
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=False,
        owner="",
        repo="",
        branch="",
        path="",
        path_raw="",
    )

    github_client_mock = Mock()
    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    canonical_url, api_url = source_code_manager.get_canonical_urls(
        "https://gitlab.com/some/repo"
    )

    assert canonical_url == "https://gitlab.com/some/repo"
    assert api_url is None
    assert (
        git_url_parse_mock.call_count == 1
    )  # Only called once in get_canonical_urls before early return


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
def test_get_canonical_urls_with_api_error(git_url_parse_mock: Mock) -> None:
    """Test that get_canonical_urls handles API errors gracefully."""
    # Configure parse_git_url mock
    git_url_parse_mock.return_value = GitUrlParseMock(
        valid=True,
        owner="DataDog",
        repo="nonexistent-repo",
        branch="",
        path="",
        path_raw="",
    )

    # Mock the GitHub client
    github_client_mock = Mock()

    # API call returns 404 (not found)
    # Set up the mock for repos["DataDog"]["nonexistent-repo"].get()
    owner_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (404, {"message": "Not Found"})
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    canonical_url, api_url = source_code_manager.get_canonical_urls(
        "https://github.com/DataDog/nonexistent-repo"
    )

    # Verify the results - should return original URL with no API URL
    assert canonical_url == "https://github.com/DataDog/nonexistent-repo"
    assert api_url is None
    assert git_url_parse_mock.call_count == 1  # Only called once in get_canonical_urls


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_canonical_urls_caches_results(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
) -> None:
    """Test that get_canonical_urls caches results to avoid redundant API calls."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    git_url_parse_mock.return_value.valid = True
    git_url_parse_mock.return_value.github = True
    git_url_parse_mock.return_value.owner = "DataDog"
    git_url_parse_mock.return_value.repo = "dd-license-attribution"
    git_url_parse_mock.return_value.protocol = "https"
    git_url_parse_mock.return_value.host = "github.com"

    # Mock GitHub API client - following existing test pattern
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        200,
        {
            "html_url": "https://github.com/DataDog/dd-license-attribution",
            "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
        },
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # Call get_canonical_urls twice with the same URL
    url = "https://github.com/DataDog/dd-license-attribution"
    canonical_url1, api_url1 = source_code_manager.get_canonical_urls(url)
    canonical_url2, api_url2 = source_code_manager.get_canonical_urls(url)

    # Verify results are the same
    assert (
        canonical_url1
        == canonical_url2
        == "https://github.com/DataDog/dd-license-attribution"
    )
    assert (
        api_url1
        == api_url2
        == "https://api.github.com/repos/DataDog/dd-license-attribution"
    )

    # Verify GitHub API was only called once (caching works)
    assert repo_mock.get.call_count == 1

    # Verify giturlparse was only called once (caching works)
    assert git_url_parse_mock.call_count == 1

    # Verify initialization mocks (used during SourceCodeManager.__init__)
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_canonical_urls_caches_different_urls_separately(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
) -> None:
    """Test that get_canonical_urls caches different URLs separately."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock giturlparse - different responses for different URLs
    def parse_side_effect(url):  # type: ignore[no-untyped-def]
        result = Mock()
        result.valid = True
        result.github = True
        result.protocol = "https"
        result.host = "github.com"
        if "repo1" in url:
            result.owner = "owner"
            result.repo = "repo1"
        else:
            result.owner = "owner"
            result.repo = "repo2"
        return result

    git_url_parse_mock.side_effect = parse_side_effect

    # Mock GitHub API client - track calls per repo
    github_client_mock = Mock()
    get_call_count = {"repo1": 0, "repo2": 0}

    # Create two separate repo mocks
    repo1_mock = Mock()
    repo2_mock = Mock()

    def repo1_get():  # type: ignore[no-untyped-def]
        get_call_count["repo1"] += 1
        return (
            200,
            {
                "html_url": "https://github.com/owner/repo1",
                "url": "https://api.github.com/repos/owner/repo1",
            },
        )

    def repo2_get():  # type: ignore[no-untyped-def]
        get_call_count["repo2"] += 1
        return (
            200,
            {
                "html_url": "https://github.com/owner/repo2",
                "url": "https://api.github.com/repos/owner/repo2",
            },
        )

    repo1_mock.get = repo1_get
    repo2_mock.get = repo2_get

    # Setup owner mock to return different repos
    owner_mock = Mock()

    def owner_getitem(repo_name):  # type: ignore[no-untyped-def]
        if repo_name == "repo1":
            return repo1_mock
        else:
            return repo2_mock

    owner_mock.__getitem__ = Mock(side_effect=owner_getitem)

    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # Call get_canonical_urls with different URLs
    url1 = "https://github.com/owner/repo1"
    url2 = "https://github.com/owner/repo2"

    canonical_url1a, api_url1a = source_code_manager.get_canonical_urls(url1)
    canonical_url2a, api_url2a = source_code_manager.get_canonical_urls(url2)
    canonical_url1b, api_url1b = source_code_manager.get_canonical_urls(
        url1
    )  # Should use cache
    canonical_url2b, api_url2b = source_code_manager.get_canonical_urls(
        url2
    )  # Should use cache

    # Verify results are correct
    assert canonical_url1a == canonical_url1b == "https://github.com/owner/repo1"
    assert canonical_url2a == canonical_url2b == "https://github.com/owner/repo2"

    # Verify each URL was only called once (caching works for different URLs)
    assert get_call_count["repo1"] == 1
    assert get_call_count["repo2"] == 1

    # Verify giturlparse was only called 2 times (once per unique URL, not 4 due to caching)
    assert git_url_parse_mock.call_count == 2

    # Verify initialization mocks (used during SourceCodeManager.__init__)
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


# Tests for error handling and edge cases


@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
def test_extract_ref_with_commit_hash(run_command_mock: Mock) -> None:
    """Test extract_ref with commit hash fallback when branch/tag validation fails."""
    from dd_license_attribution.artifact_management.source_code_manager import (
        extract_ref,
    )

    # extract_ref tries progressively longer prefixes:
    # 1. "abc123def456" - fails (returns non-zero)
    # 2. "abc123def456/path" - fails
    # 3. "abc123def456/path/to" - fails
    # 4. "abc123def456/path/to/file" - fails
    # Then tries hash fallback:
    # 5. "abc123def456" as hash - succeeds (returns 0)
    run_command_mock.side_effect = [1, 1, 1, 1, 0]

    ref = "abc123def456/path/to/file"
    url = "https://github.com/owner/repo"

    result = extract_ref(ref, url)

    assert result == "abc123def456"
    assert run_command_mock.call_count == 5
    # Verify the hash check was called
    run_command_mock.assert_any_call(f"git ls-remote {url} | grep -q abc123def456")


@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
def test_extract_ref_with_invalid_hash_returns_empty(run_command_mock: Mock) -> None:
    """Test extract_ref returns empty string when hash validation also fails."""
    from dd_license_attribution.artifact_management.source_code_manager import (
        extract_ref,
    )

    # extract_ref tries progressively longer prefixes:
    # 1. "invalid_ref" - fails (returns non-zero)
    # 2. "invalid_ref/path" - fails
    # Then tries hash fallback:
    # 3. "invalid_ref" as hash - also fails (returns non-zero)
    run_command_mock.side_effect = [1, 1, 1]

    ref = "invalid_ref/path"
    url = "https://github.com/owner/repo"

    result = extract_ref(ref, url)

    assert result == ""
    assert run_command_mock.call_count == 3


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
def test_discover_default_branch_with_exception(
    output_from_command_mock: Mock,
) -> None:
    """Test _discover_default_branch raises NonAccessibleRepository on git command failure."""
    from dd_license_attribution.artifact_management.source_code_manager import (
        NonAccessibleRepository,
        SourceCodeManager,
    )

    output_from_command_mock.side_effect = Exception("git command failed")

    github_client_mock = Mock()
    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    url = "https://github.com/owner/repo"

    with pytest.raises(NonAccessibleRepository) as exc_info:
        source_code_manager._discover_default_branch(url)

    assert "Could not discover default branch for" in str(exc_info.value)
    assert url in str(exc_info.value)
    output_from_command_mock.assert_called_once_with(
        f"git ls-remote --symref {url} HEAD"
    )


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_code_returns_none_when_api_url_is_none(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
) -> None:
    """Test get_code returns None when canonical URL resolution returns None for api_url."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # First call: original URL parse (valid GitHub URL)
    # Second call: in get_canonical_urls (valid GitHub URL)
    # Third call: after get_canonical_urls returns (should not be reached)
    parsed_url_original = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="",
        path="",
        path_raw="",
    )
    parsed_url_canonical = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="",
        path="",
        path_raw="",
    )

    git_url_parse_mock.side_effect = [
        parsed_url_original,
        parsed_url_canonical,
    ]

    # Mock GitHub client to return 404
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (404, {"message": "Not Found"})
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    request_url = "https://github.com/test_owner/test_repo"
    code_ref = source_code_manager.get_code(request_url)

    # Should return None because api_url is None (GitHub API returned 404)
    assert code_ref is None
    assert git_url_parse_mock.call_count == 2


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_code_returns_none_when_canonical_url_parse_invalid(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
) -> None:
    """Test get_code returns None when parsed canonical URL is invalid."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # First call: original URL parse (valid GitHub URL)
    # Second call: in get_canonical_urls (valid)
    # Third call: parsing canonical URL (invalid - edge case)
    parsed_url_original = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="",
        path="",
        path_raw="",
    )
    parsed_url_in_canonical = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="",
        path="",
        path_raw="",
    )
    parsed_url_after_canonical = GitUrlParseMock(
        valid=False,  # Invalid after canonicalization (edge case)
        owner="",
        repo="",
        branch="",
        path="",
        path_raw="",
    )

    git_url_parse_mock.side_effect = [
        parsed_url_original,
        parsed_url_in_canonical,
        parsed_url_after_canonical,
    ]

    # Mock GitHub client to return valid response
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        200,
        {
            "html_url": "https://some-invalid-url",  # Malformed URL that parses as invalid
            "url": "https://api.github.com/repos/test_owner/test_repo",
        },
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    request_url = "https://github.com/test_owner/test_repo"
    code_ref = source_code_manager.get_code(request_url)

    # Should return None because canonical URL parses as invalid
    assert code_ref is None
    assert git_url_parse_mock.call_count == 3
