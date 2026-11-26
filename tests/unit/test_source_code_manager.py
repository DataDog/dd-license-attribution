# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import logging
from datetime import datetime
from pathlib import Path
from typing import Any  # used for auxiliary testing function only
from unittest.mock import Mock, call, patch

import pytest
from pytest import LogCaptureFixture

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.source_code_manager import (
    NONINTERACTIVE_GIT_ENV,
    NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    MirrorSpec,
    RefType,
    SourceCodeManager,
    _is_rate_limit_response,
    has_repository_path,
    keep_tree_path,
)


def _assert_staging_dir(actual_dir: str, expected_cache_dir: str) -> str:
    assert actual_dir.startswith(f"{expected_cache_dir}.tmp-")
    return actual_dir


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

    def _fake_output(
        args: list[str], cwd: str | None = None, env: dict[str, str] | None = None
    ) -> str:
        if "--symref" in args:
            return "ref: refs/heads/main\tHEAD\n72a11341aa684010caf1ca5dee779f0e7e84dfe9\tHEAD\n"
        ref = args[-1] if len(args) > 3 else ""
        if ref in ("test_branch", "test_tag"):
            return f"72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/{ref}\n"
        return ""

    output_from_command_mock.side_effect = _fake_output
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
        ls_remote_calls = [
            args[0]
            for args, _ in output_from_command_mock.call_args_list
            if args
            and args[0][:4]
            == [
                "git",
                "ls-remote",
                "--",
                expected_source_code_reference.repo_url,
            ]
        ]
        assert any(
            expected_source_code_reference.branch in cmd[4:] for cmd in ls_remote_calls
        )
        staging_dir = _assert_staging_dir(
            run_command_mock.call_args.args[0][-1], expected_local_path_root
        )
        run_command_mock.assert_called_once_with(
            [
                "git",
                "clone",
                "-c",
                "advice.detachedHead=False",
                "--depth",
                "1",
                f"--branch={expected_branch}",
                expected_clone_url,
                staging_dir,
            ]
        )
    if (
        mocked_parser_results.branch == ""
        and not "test_branch" in mocked_parser_results.path_raw
    ):
        output_from_command_mock.assert_any_call(
            [
                "git",
                "ls-remote",
                "--symref",
                "--",
                expected_source_code_reference.repo_url,
                "HEAD",
            ]
        )
    assert get_datetime_now_mock.call_count == 1
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (main logic)
    artifact_file_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
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
    output_from_command_mock: Mock,
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
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

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

    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            expected_source_code_reference.repo_url,
            expected_source_code_reference.branch,
        ]
    )
    run_command_mock.assert_not_called()


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_source_code_manager_get_non_cached_code_because_it_expired(
    get_datetime_now_mock: Mock,
    mock_create_dirs: Mock,
    git_url_parse_mock: Mock,
    path_exists_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
    output_from_command_mock: Mock,
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
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

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

    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            expected_source_code_reference.repo_url,
            expected_source_code_reference.branch,
        ]
    )
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    run_command_mock.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            f"--branch={expected_source_code_reference.branch}",
            expected_source_code_reference.repo_url,
            staging_dir,
        ]
    )
    mock_create_dirs.assert_called_once_with(staging_dir)


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_source_code_manager_get_non_cached_code_because_force_update(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_mock: Mock,
    run_command_mock: Mock,
    artifact_mock_list_dir: Mock,
    source_code_mock_list_dir: Mock,
    mock_create_dirs: Mock,
    output_from_command_mock: Mock,
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
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )
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

    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    mock_create_dirs.assert_called_once_with(staging_dir)

    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            expected_source_code_reference.repo_url,
            expected_source_code_reference.branch,
        ]
    )
    run_command_mock.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            f"--branch={expected_source_code_reference.branch}",
            expected_source_code_reference.repo_url,
            staging_dir,
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


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
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
    output_from_command_mock: Mock,
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
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

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

    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            expected_source_code_reference.repo_url,
            "test_branch/test_dir",
            expected_source_code_reference.branch,
        ]
    )
    staging_dir = _assert_staging_dir(
        run_command_mock.call_args.args[0][-1],
        expected_source_code_reference.local_root_path,
    )
    run_command_mock.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            f"--branch={expected_source_code_reference.branch}",
            expected_source_code_reference.repo_url,
            staging_dir,
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


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_source_code_manager_with_mirror_url(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
    output_from_command_mock: Mock,
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
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

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
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    mock_create_dirs.assert_called_once_with(staging_dir)
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            expected_source_code_reference.repo_url,
            expected_source_code_reference.branch,
        ]
    )
    run_command_mock.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            f"--branch={expected_source_code_reference.branch}",
            "https://github.com/mirror_owner/mirror_repo",
            staging_dir,
        ]
    )


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_source_code_manager_with_mirror_ref_mapping(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
    output_from_command_mock: Mock,
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
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

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
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    mock_create_dirs.assert_called_once_with(staging_dir)
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            expected_source_code_reference.repo_url,
            expected_source_code_reference.branch,
        ]
    )
    run_command_mock.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=mirror_branch",
            "https://github.com/mirror_owner/mirror_repo",
            staging_dir,
        ]
    )


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_source_code_manager_with_mirror_ref_mapping_to_tag(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
    output_from_command_mock: Mock,
) -> None:
    """A branch->tag ref_mapping checks out the mirror repository at the tag.

    The tag is fetched by its fully qualified ref so a same-named branch in
    the mirror cannot shadow it; the local cache stays keyed by the original
    branch name.
    """
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
    # Same timestamp as the setup time: the cache lookup runs and misses.
    artifact_list_dir_mock.return_value = ["20220101_000000Z"]
    source_code_list_dir_mock.return_value = ["20220101_000000Z"]
    run_command_mock.return_value = 0
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

    mirror_spec = MirrorSpec(
        original_url="https://github.com/test_owner/test_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
        ref_mapping={(RefType.BRANCH, "test_branch"): (RefType.TAG, "v1.0")},
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
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")
    path_exists_source_code_mock.assert_called_once_with(expected_cache_dir)
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    mock_create_dirs.assert_called_once_with(staging_dir)
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            expected_source_code_reference.repo_url,
            expected_source_code_reference.branch,
        ]
    )
    run_command_mock.assert_has_calls(
        [
            call(["git", "init", "--quiet"], cwd=staging_dir),
            call(
                [
                    "git",
                    "config",
                    "remote.origin.url",
                    "https://github.com/mirror_owner/mirror_repo",
                ],
                cwd=staging_dir,
            ),
            call(
                [
                    "git",
                    "fetch",
                    "--depth",
                    "1",
                    "origin",
                    "refs/tags/v1.0:refs/tags/v1.0",
                ],
                cwd=staging_dir,
            ),
            call(
                [
                    "git",
                    "-c",
                    "advice.detachedHead=False",
                    "checkout",
                    "FETCH_HEAD",
                ],
                cwd=staging_dir,
            ),
        ]
    )
    assert run_command_mock.call_count == 4


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_mirror_tag_fetch_failure_returns_none(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
    output_from_command_mock: Mock,
) -> None:
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

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
    # Same timestamp as the setup time: the cache lookup runs and misses.
    artifact_list_dir_mock.return_value = ["20220101_000000Z"]
    source_code_list_dir_mock.return_value = ["20220101_000000Z"]
    run_command_mock.side_effect = [0, 0, 128]
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

    mirror_spec = MirrorSpec(
        original_url="https://github.com/test_owner/test_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
        ref_mapping={(RefType.BRANCH, "test_branch"): (RefType.TAG, "v1.0")},
    )
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=[mirror_spec]
    )
    code_ref = source_code_manager.get_code(request_url)

    expected_cache_dir = "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch"
    assert code_ref is None
    get_datetime_now_mock.assert_called_once()
    assert git_url_parse_mock.call_count == 3
    path_exists_artifact_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")
    path_exists_source_code_mock.assert_called_once_with(expected_cache_dir)
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    mock_create_dirs.assert_called_once_with(staging_dir)
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            "https://github.com/test_owner/test_repo",
            "test_branch",
        ]
    )
    # The checkout step must not run once the tag fetch has failed.
    run_command_mock.assert_has_calls(
        [
            call(["git", "init", "--quiet"], cwd=staging_dir),
            call(
                [
                    "git",
                    "config",
                    "remote.origin.url",
                    "https://github.com/mirror_owner/mirror_repo",
                ],
                cwd=staging_dir,
            ),
            call(
                [
                    "git",
                    "fetch",
                    "--depth",
                    "1",
                    "origin",
                    "refs/tags/v1.0:refs/tags/v1.0",
                ],
                cwd=staging_dir,
            ),
        ]
    )
    assert run_command_mock.call_count == 3


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_source_code_manager_mirror_tag_forced_retry_after_failed_fetch(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
    output_from_command_mock: Mock,
) -> None:
    """A forced retry reuses the same cache dir; the tag setup must be
    idempotent so the fetch is attempted again."""
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

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
    artifact_list_dir_mock.return_value = []
    source_code_list_dir_mock.return_value = []
    # First attempt: fetch fails. Retry: every step succeeds.
    run_command_mock.side_effect = [0, 0, 128, 0, 0, 0, 0]
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

    mirror_spec = MirrorSpec(
        original_url="https://github.com/test_owner/test_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
        ref_mapping={(RefType.BRANCH, "test_branch"): (RefType.TAG, "v1.0")},
    )
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=[mirror_spec]
    )
    first = source_code_manager.get_code(request_url, force_update=True)
    retry = source_code_manager.get_code(request_url, force_update=True)

    expected_cache_dir = "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch"
    assert first is None
    assert retry == SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path=expected_cache_dir,
        local_full_path=f"{expected_cache_dir}/test_dir",
    )
    get_datetime_now_mock.assert_called_once()
    # 3 calls on the first attempt; the retry hits the canonical URL cache.
    assert git_url_parse_mock.call_count == 5
    path_exists_artifact_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_has_calls([call("cache_dir"), call("cache_dir")])
    assert source_code_list_dir_mock.call_count == 2
    assert mock_create_dirs.call_count == 2
    first_staging = _assert_staging_dir(
        mock_create_dirs.call_args_list[0].args[0], expected_cache_dir
    )
    second_staging = _assert_staging_dir(
        mock_create_dirs.call_args_list[1].args[0], expected_cache_dir
    )
    assert first_staging != second_staging
    ls_remote_call = call(
        [
            "git",
            "ls-remote",
            "--",
            "https://github.com/test_owner/test_repo",
            "test_branch",
        ]
    )
    output_from_command_mock.assert_has_calls([ls_remote_call, ls_remote_call])
    assert output_from_command_mock.call_count == 2
    assert run_command_mock.call_args_list == [
        call(["git", "init", "--quiet"], cwd=first_staging),
        call(
            [
                "git",
                "config",
                "remote.origin.url",
                "https://github.com/mirror_owner/mirror_repo",
            ],
            cwd=first_staging,
        ),
        call(
            [
                "git",
                "fetch",
                "--depth",
                "1",
                "origin",
                "refs/tags/v1.0:refs/tags/v1.0",
            ],
            cwd=first_staging,
        ),
        call(["git", "init", "--quiet"], cwd=second_staging),
        call(
            [
                "git",
                "config",
                "remote.origin.url",
                "https://github.com/mirror_owner/mirror_repo",
            ],
            cwd=second_staging,
        ),
        call(
            [
                "git",
                "fetch",
                "--depth",
                "1",
                "origin",
                "refs/tags/v1.0:refs/tags/v1.0",
            ],
            cwd=second_staging,
        ),
        call(
            ["git", "-c", "advice.detachedHead=False", "checkout", "FETCH_HEAD"],
            cwd=second_staging,
        ),
    ]


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_source_code_manager_mirror_tag_clone_with_git_env(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
    output_from_command_mock: Mock,
) -> None:
    """A TAG-clone with git_env passes env and timeout kwargs to every command.

    When skip_canonical_lookup is True the git_env is NONINTERACTIVE_GIT_ENV,
    so each TAG-path git command must carry cwd, env, and timeout kwargs —
    the same fields the non-TAG clone path already asserts in its env test.
    Without this test, mutations of the ``if git_env is not None`` guard
    and the env/timeout assignments in the TAG branch survive because no
    TAG-path test exercises them.
    """
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

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
    artifact_list_dir_mock.return_value = ["20220101_000000Z"]
    source_code_list_dir_mock.return_value = ["20220101_000000Z"]
    run_command_mock.return_value = 0
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

    mirror_spec = MirrorSpec(
        original_url="https://github.com/test_owner/test_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
        ref_mapping={(RefType.BRANCH, "test_branch"): (RefType.TAG, "v1.0")},
    )
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=[mirror_spec]
    )
    code_ref = source_code_manager.get_code(request_url, skip_canonical_lookup=True)

    expected_cache_dir = "cache_dir/20220101_000000Z/test_owner-test_repo/test_branch"
    assert code_ref == SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path=expected_cache_dir,
        local_full_path=f"{expected_cache_dir}/test_dir",
    )
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    expected_kwargs = {
        "cwd": staging_dir,
        "env": NONINTERACTIVE_GIT_ENV,
        "timeout": NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    }
    run_command_mock.assert_has_calls(
        [
            call(["git", "init", "--quiet"], **expected_kwargs),
            call(
                [
                    "git",
                    "config",
                    "remote.origin.url",
                    "https://github.com/mirror_owner/mirror_repo",
                ],
                **expected_kwargs,
            ),
            call(
                [
                    "git",
                    "fetch",
                    "--depth",
                    "1",
                    "origin",
                    "refs/tags/v1.0:refs/tags/v1.0",
                ],
                **expected_kwargs,
            ),
            call(
                [
                    "git",
                    "-c",
                    "advice.detachedHead=False",
                    "checkout",
                    "FETCH_HEAD",
                ],
                **expected_kwargs,
            ),
        ]
    )
    assert run_command_mock.call_count == 4
    # The branch-validation ls-remote also carries env and timeout when
    # git_env is set.
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            "https://github.com/test_owner/test_repo",
            "test_branch",
        ],
        env=NONINTERACTIVE_GIT_ENV,
        timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    )


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_source_code_manager_with_unsupported_commit_ref_type(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
    output_from_command_mock: Mock,
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
    artifact_list_dir_mock.return_value = []
    source_code_list_dir_mock.return_value = []
    run_command_mock.return_value = 0
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

    mirror_spec = MirrorSpec(
        original_url="https://github.com/test_owner/test_repo",
        mirror_url="https://github.com/mirror_owner/mirror_repo",
        ref_mapping={
            (RefType.BRANCH, "test_branch"): (
                RefType.COMMIT,
                "72a11341aa684010caf1ca5dee779f0e7e84dfe9",
            )
        },
    )
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, 86400, mirrors=[mirror_spec]
    )

    with pytest.raises(NotImplementedError) as e:
        source_code_manager.get_code(request_url)

    assert (
        str(e.value)
        == "Mirror reference type RefType.COMMIT is not yet implemented. Only branch and tag mapping targets are supported."
    )
    get_datetime_now_mock.assert_called_once()
    assert (
        git_url_parse_mock.call_count == 3
    )  # Called: in get_code (disambiguation), in get_canonical_urls, in get_code (before failure)
    path_exists_artifact_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_not_called()
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            "https://github.com/test_owner/test_repo",
            "test_branch",
        ]
    )
    run_command_mock.assert_not_called()


@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
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
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    mock_create_dirs.assert_called_once_with(staging_dir)
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--symref",
            "--",
            expected_source_code_reference.repo_url,
            "HEAD",
        ]
    )
    run_command_mock.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=development",
            "https://github.com/mirror_owner/mirror_repo",
            staging_dir,
        ]
    )


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_source_code_manager_with_multiple_mirrors(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
    output_from_command_mock: Mock,
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
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

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
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    mock_create_dirs.assert_called_once_with(staging_dir)
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            expected_source_code_reference.repo_url,
            expected_source_code_reference.branch,
        ]
    )
    run_command_mock.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=mirror_branch",
            "https://github.com/mirror_owner/mirror_repo",
            staging_dir,
        ]
    )


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_source_code_manager_with_no_mirror_match(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    path_exists_artifact_mock: Mock,
    path_exists_source_code_mock: Mock,
    run_command_mock: Mock,
    mock_create_dirs: Mock,
    output_from_command_mock: Mock,
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
    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/test_branch\n"
    )

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
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0], expected_cache_dir
    )
    mock_create_dirs.assert_called_once_with(staging_dir)
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            expected_source_code_reference.repo_url,
            expected_source_code_reference.branch,
        ]
    )
    run_command_mock.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            f"--branch={expected_source_code_reference.branch}",
            expected_source_code_reference.repo_url,
            staging_dir,
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
def test_get_canonical_urls_with_api_error(
    git_url_parse_mock: Mock, caplog: LogCaptureFixture
) -> None:
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

    with caplog.at_level(logging.WARNING):
        canonical_url, api_url = source_code_manager.get_canonical_urls(
            "https://github.com/DataDog/nonexistent-repo"
        )

    # Verify the results - should return original URL with no API URL
    assert canonical_url == "https://github.com/DataDog/nonexistent-repo"
    assert api_url is None
    assert git_url_parse_mock.call_count == 1  # Only called once in get_canonical_urls

    # The non-200 fallback must be visible at WARNING (not silently DEBUG),
    # naming the status code and the URL.
    expected_warning = (
        "Failed to resolve canonical URLs (status 404) for: "
        "https://github.com/DataDog/nonexistent-repo"
    )
    assert any(
        expected_warning in record.message for record in caplog.records
    ), caplog.records


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


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
def test_extract_ref_with_commit_hash(output_from_command_mock: Mock) -> None:
    """Test extract_ref with commit hash fallback when branch/tag validation fails."""
    from dd_license_attribution.artifact_management.source_code_manager import (
        extract_ref,
    )

    # First call queries all candidate ref prefixes together (no match),
    # second call queries all refs for the commit-hash fallback.
    output_from_command_mock.side_effect = [
        "",
        "abc123def456\trefs/heads/main\n",
    ]

    ref = "abc123def456/path/to/file"
    url = "https://github.com/owner/repo"

    result = extract_ref(ref, url)

    assert result == "abc123def456"
    assert output_from_command_mock.call_count == 2
    output_from_command_mock.assert_has_calls(
        [
            call(
                [
                    "git",
                    "ls-remote",
                    "--",
                    url,
                    "abc123def456/path/to/file",
                    "abc123def456/path/to",
                    "abc123def456/path",
                    "abc123def456",
                ]
            ),
            call(["git", "ls-remote", "--", url]),
        ]
    )


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
def test_extract_ref_returns_longest_matching_ref_prefix_in_one_call(
    output_from_command_mock: Mock,
) -> None:
    from dd_license_attribution.artifact_management.source_code_manager import (
        extract_ref,
    )

    output_from_command_mock.return_value = (
        "1111111111111111111111111111111111111111\trefs/heads/feature\n"
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/feature/slash\n"
    )

    result = extract_ref("feature/slash/path", "https://github.com/owner/repo")

    assert result == "feature/slash"
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            "https://github.com/owner/repo",
            "feature/slash/path",
            "feature/slash",
            "feature",
        ]
    )


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
def test_extract_ref_with_invalid_hash_returns_empty(
    output_from_command_mock: Mock,
) -> None:
    """Test extract_ref returns empty string when hash validation also fails."""
    from dd_license_attribution.artifact_management.source_code_manager import (
        extract_ref,
    )

    output_from_command_mock.side_effect = ["", ""]

    ref = "invalid_ref/path"
    url = "https://github.com/owner/repo"

    result = extract_ref(ref, url)

    assert result == ""
    output_from_command_mock.assert_has_calls(
        [
            call(["git", "ls-remote", "--", url, "invalid_ref/path", "invalid_ref"]),
            call(["git", "ls-remote", "--", url]),
        ]
    )
    assert output_from_command_mock.call_count == 2


@patch("dd_license_attribution.artifact_management.source_code_manager.logger")
@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
def test_extract_ref_does_not_log_url_credentials(
    output_from_command_mock: Mock,
    logger_mock: Mock,
) -> None:
    from dd_license_attribution.artifact_management.source_code_manager import (
        extract_ref,
    )

    output_from_command_mock.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/main\n"
    )
    secret = "ghp_super_secret_mirror_token"
    url = f"https://x-access-token:{secret}@github.com/owner/repo"

    assert extract_ref("main/apis", url) == "main"
    for log_call in logger_mock.debug.call_args_list:
        assert secret not in str(log_call)


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

    output_from_command_mock.side_effect = OSError("git command failed")

    github_client_mock = Mock()
    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    url = "https://github.com/owner/repo"

    with pytest.raises(NonAccessibleRepository) as exc_info:
        source_code_manager._discover_default_branch(url)

    assert "Could not discover default branch for" in str(exc_info.value)
    assert url in str(exc_info.value)
    output_from_command_mock.assert_called_once_with(
        ["git", "ls-remote", "--symref", "--", url, "HEAD"]
    )


@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
def test_get_code_returns_none_when_default_branch_cannot_be_discovered(
    git_url_parse_mock: Mock,
    artifact_path_exists_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    output_from_command_mock: Mock,
    run_command_mock: Mock,
    create_dirs_mock: Mock,
) -> None:
    parsed_url = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="",
        path="",
        path_raw="",
    )
    git_url_parse_mock.return_value = parsed_url
    artifact_path_exists_mock.return_value = True
    artifact_list_dir_mock.return_value = []
    source_code_list_dir_mock.return_value = []
    output_from_command_mock.side_effect = OSError("git ls-remote failed")
    github_client_mock = create_github_client_mock()
    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    code_ref = source_code_manager.get_code("https://github.com/test_owner/test_repo")

    assert code_ref is None
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--symref",
            "--",
            "https://github.com/test_owner/test_repo",
            "HEAD",
        ]
    )
    create_dirs_mock.assert_not_called()
    run_command_mock.assert_not_called()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_not_called()


@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_get_code_can_skip_canonical_lookup_for_direct_git_checkout(
    get_datetime_now_mock: Mock,
    git_url_parse_mock: Mock,
    artifact_path_exists_mock: Mock,
    artifact_list_dir_mock: Mock,
    source_code_list_dir_mock: Mock,
    output_from_command_mock: Mock,
    run_command_mock: Mock,
    create_dirs_mock: Mock,
) -> None:
    get_datetime_now_mock.return_value = datetime.fromisoformat(
        "2022-01-01T00:00:00+00:00"
    )
    parsed_url = GitUrlParseMock(
        valid=True,
        owner="test_owner",
        repo="test_repo",
        branch="",
        path="",
        path_raw="",
    )
    git_url_parse_mock.return_value = parsed_url
    artifact_path_exists_mock.return_value = True
    artifact_list_dir_mock.return_value = []
    source_code_list_dir_mock.return_value = []
    output_from_command_mock.return_value = (
        "ref: refs/heads/main\tHEAD\n72a11341aa684010caf1ca5dee779f0e7e84dfe9\tHEAD\n"
    )
    run_command_mock.return_value = 0
    github_client_mock = Mock()
    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    code_ref = source_code_manager.get_code(
        "https://github.com/test_owner/test_repo",
        skip_canonical_lookup=True,
    )

    assert code_ref == SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="main",
        local_root_path="cache_dir/20220101_000000Z/test_owner-test_repo/main",
        local_full_path="cache_dir/20220101_000000Z/test_owner-test_repo/main",
    )
    assert not github_client_mock.mock_calls
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--symref",
            "--",
            "https://github.com/test_owner/test_repo",
            "HEAD",
        ],
        env=NONINTERACTIVE_GIT_ENV,
        timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    )
    staging_dir = _assert_staging_dir(
        create_dirs_mock.call_args.args[0],
        "cache_dir/20220101_000000Z/test_owner-test_repo/main",
    )
    create_dirs_mock.assert_called_once_with(staging_dir)
    run_command_mock.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=main",
            "https://github.com/test_owner/test_repo",
            staging_dir,
        ],
        env=NONINTERACTIVE_GIT_ENV,
        timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    )
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")


@pytest.mark.parametrize("status", [401, 404])
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_code_returns_none_when_api_url_is_none(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
    output_from_command_mock: Mock,
    create_dirs_mock: Mock,
    status: int,
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

    # Mock GitHub client to return an error
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (status, {"message": "API error"})
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    request_url = "https://github.com/test_owner/test_repo"
    code_ref = source_code_manager.get_code(request_url)

    # Should return None because api_url is None (GitHub API returned an error)
    assert code_ref is None
    assert git_url_parse_mock.call_count == 2
    repo_mock.get.assert_called_once_with()
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_not_called()
    run_command_mock.assert_not_called()
    output_from_command_mock.assert_not_called()
    create_dirs_mock.assert_not_called()


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_code_returns_none_when_rate_limited_after_retries(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
    source_code_list_dir_mock: Mock,
    run_command_mock: Mock,
    output_from_command_mock: Mock,
    create_dirs_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """Test get_code retries 403 rate limit responses with backoff, then returns None."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

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

    # Mock GitHub client to always return a rate limit 403
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        403,
        {"message": "API rate limit exceeded for 1.2.3.4."},
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    request_url = "https://github.com/test_owner/test_repo"
    code_ref = source_code_manager.get_code(request_url)

    # Should return None because api_url is None (GitHub API stayed rate limited)
    assert code_ref is None
    git_url_parse_mock.assert_has_calls([call(request_url), call(request_url)])
    # 3 attempts total: the initial call plus GITHUB_API_MAX_RETRIES - 1 retries
    assert repo_mock.get.mock_calls == [call(), call(), call()]
    assert sleep_mock.mock_calls == [call(2.0), call(4.0)]
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_not_called()
    run_command_mock.assert_not_called()
    output_from_command_mock.assert_not_called()
    create_dirs_mock.assert_not_called()


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


class TestIsRateLimitResponseClassification:
    """Direct classification matrix for _is_rate_limit_response.

    GitHub secondary/abuse rate limits surface as a 403 whose message does
    not mention "rate limit" and often carries no Retry-After header; those
    must be classified as rate limits so they get retried. Permission 403s
    ("Resource not accessible by integration") must stay permanent.
    """

    @pytest.mark.parametrize(
        "status, result, headers, expected",
        [
            # A 429 is always a rate limit, regardless of body or headers.
            (429, None, None, True),
            (429, {"message": "Too many requests"}, None, True),
            # A 403 confirmed by a Retry-After header (secondary rate limit),
            # even when the primary quota (X-RateLimit-Remaining) is positive.
            (403, None, {"retry-after": "60"}, True),
            (403, None, {"retry-after": "30", "x-ratelimit-remaining": "5000"}, True),
            # A 403 confirmed by the primary quota being exhausted.
            (403, None, {"x-ratelimit-remaining": "0"}, True),
            (403, None, {"x-ratelimit-remaining": "-1"}, True),
            # A 403 confirmed by the message mentioning a rate limit.
            (
                403,
                {"message": "API rate limit exceeded for 1.2.3.4."},
                None,
                True,
            ),
            (
                403,
                {"message": "You have exceeded a secondary rate limit"},
                {},
                True,
            ),
            # A 403 for a secondary/abuse rate limit whose message does NOT
            # contain "rate limit" (GitHub abuse detection phrasing), with no
            # Retry-After header - the misclassification fixed in this change.
            (
                403,
                {
                    "message": "You have triggered an abuse detection mechanism "
                    "and will be blocked for a few minutes."
                },
                None,
                True,
            ),
            (
                403,
                {"message": "You have been blocked from the API for 1 hour."},
                None,
                True,
            ),
            # Abuse-detection phrasing matches case-insensitively.
            (
                403,
                {"message": "You have TRIGGERED an Abuse Detection mechanism"},
                None,
                True,
            ),
            # Abuse phrasing is confirmed even when the primary quota is
            # positive (X-RateLimit-Remaining only tracks the primary quota).
            (
                403,
                {"message": "You have triggered an abuse detection mechanism"},
                {"x-ratelimit-remaining": "5000"},
                True,
            ),
            # Permission failures are permanent: not retried, not rate limits.
            (
                403,
                {"message": "Resource not accessible by integration"},
                None,
                False,
            ),
            (
                403,
                {"message": "Resource not accessible by integration"},
                {"x-ratelimit-remaining": "5000"},
                False,
            ),
            # Unrelated 403 messages are permanent.
            (403, {"message": "Forbidden"}, None, False),
            (403, None, None, False),
            # An unparseable X-RateLimit-Remaining confirms nothing.
            (
                403,
                {"message": "Some other error"},
                {"x-ratelimit-remaining": "abc"},
                False,
            ),
            # Non-403/429 statuses are never rate limits here.
            (404, {"message": "Not Found"}, None, False),
            (301, {"message": "Moved Permanently"}, None, False),
            (200, None, None, False),
        ],
    )
    def test_classification_matrix(
        self,
        status: int,
        result: dict[str, Any] | None,
        headers: dict[str, str] | None,
        expected: bool,
    ) -> None:
        assert _is_rate_limit_response(status, result, headers) is expected


def _github_client_with_default_branch(status: int, default_branch: str) -> Any:
    github_client_mock = create_github_client_mock()
    repo_mock = github_client_mock.repos["test_owner"]["test_repo"]
    repo_mock.get.return_value = (
        status,
        (
            {
                "html_url": "https://github.com/test_owner/test_repo",
                "url": "https://api.github.com/repos/test_owner/test_repo",
                "default_branch": default_branch,
            }
            if status == 200
            else None
        ),
    )
    return github_client_mock


@pytest.mark.parametrize(
    "mirrors, repo_info_status, expected, expect_repo_info_lookup",
    [
        ([], 200, False, False),
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/test_owner/test_repo_mirror",
                )
            ],
            200,
            False,
            False,
        ),
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/test_owner/test_repo",
                    ref_mapping={(RefType.BRANCH, "main"): (RefType.TAG, "v1.0")},
                )
            ],
            200,
            True,
            True,
        ),
        (
            [
                MirrorSpec(
                    original_url="https://github.com/other_owner/other_repo",
                    mirror_url="https://github.com/other_owner/other_repo",
                    ref_mapping={(RefType.BRANCH, "main"): (RefType.TAG, "v1.0")},
                )
            ],
            200,
            False,
            False,
        ),
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/test_owner/test_repo",
                    ref_mapping={
                        (RefType.BRANCH, "release"): (RefType.BRANCH, "v3"),
                        (RefType.TAG, "main"): (RefType.TAG, "v1.0"),
                    },
                )
            ],
            200,
            False,
            True,
        ),
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/test_owner/test_repo",
                    ref_mapping={(RefType.BRANCH, "release"): (RefType.BRANCH, "v3")},
                )
            ],
            404,
            True,
            True,
        ),
        # An identity mapping on the same repository still checks out the
        # default branch, also with a token in the mirror URL.
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://git:token@github.com/test_owner/test_repo",
                    ref_mapping={(RefType.BRANCH, "main"): (RefType.BRANCH, "main")},
                )
            ],
            200,
            False,
            True,
        ),
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/test_owner/test_repo",
                    ref_mapping={(RefType.BRANCH, "main"): (RefType.BRANCH, "main")},
                )
            ],
            404,
            False,
            True,
        ),
        # GitHub owner/repo names are case-insensitive.
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/Test_Owner/Test_Repo",
                    ref_mapping={(RefType.BRANCH, "main"): (RefType.BRANCH, "main")},
                )
            ],
            200,
            False,
            True,
        ),
        # The same branch name on another repository (e.g. a fork) is not the
        # original default branch.
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/fork_owner/test_repo",
                    ref_mapping={(RefType.BRANCH, "main"): (RefType.BRANCH, "main")},
                )
            ],
            200,
            True,
            True,
        ),
        # Checkout uses the first mirror matching the repository, so only that
        # one decides (e.g. a caller's URL-only mirror ahead of the GitHub
        # Action's branch-mapping fallback).
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/test_owner/test_repo_mirror",
                ),
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/test_owner/test_repo",
                    ref_mapping={(RefType.BRANCH, "main"): (RefType.BRANCH, "pr")},
                ),
            ],
            200,
            False,
            False,
        ),
        (
            [
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/test_owner/test_repo",
                    ref_mapping={(RefType.BRANCH, "main"): (RefType.BRANCH, "pr")},
                ),
                MirrorSpec(
                    original_url="https://github.com/test_owner/test_repo",
                    mirror_url="https://github.com/test_owner/test_repo_mirror",
                ),
            ],
            200,
            True,
            True,
        ),
    ],
    ids=[
        "no-mirrors",
        "mirror-without-ref-mapping",
        "default-branch-remapped",
        "mirror-for-another-repo",
        "only-non-default-refs-remapped",
        "default-branch-unknown-branch-remapped",
        "same-repo-identity-mapping-with-token",
        "same-repo-identity-mapping-default-branch-unknown",
        "same-repo-identity-mapping-different-case",
        "identity-mapping-on-another-repo",
        "first-matching-mirror-has-no-ref-mapping",
        "first-matching-mirror-remaps-default-branch",
    ],
)
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_source_code_manager_remaps_default_branch(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    mirrors: list[MirrorSpec],
    repo_info_status: int,
    expected: bool,
    expect_repo_info_lookup: bool,
) -> None:
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []
    github_client_mock = _github_client_with_default_branch(repo_info_status, "main")
    source_code_manager = SourceCodeManager(
        "cache_dir", github_client_mock, mirrors=mirrors
    )

    assert (
        source_code_manager.remaps_default_branch(
            "https://github.com/test_owner/test_repo"
        )
        is expected
    )
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")
    # The default branch is only looked up when the matching mirror remaps refs.
    repo_info_get_mock = github_client_mock.repos["test_owner"]["test_repo"].get
    if expect_repo_info_lookup:
        repo_info_get_mock.assert_called_once_with()
    else:
        repo_info_get_mock.assert_not_called()


@pytest.mark.parametrize(
    "mirror_url, expected",
    [
        ("https://GIT.example.com/Owner/Repo", False),
        ("https://git.example.com/owner/repo", True),
    ],
    ids=["host-differs-in-case", "path-differs-in-case"],
)
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_source_code_manager_remaps_default_branch_non_github_path_case(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    mirror_url: str,
    expected: bool,
) -> None:
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []
    # Outside GitHub, repository paths may be case-sensitive.
    original_url = "https://git.example.com/Owner/Repo"
    github_client_mock = create_github_client_mock()
    source_code_manager = SourceCodeManager(
        "cache_dir",
        github_client_mock,
        mirrors=[
            MirrorSpec(
                original_url=original_url,
                mirror_url=mirror_url,
                ref_mapping={(RefType.BRANCH, "main"): (RefType.BRANCH, "main")},
            )
        ],
    )

    assert source_code_manager.remaps_default_branch(original_url) is expected
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")
    # The default branch can only be looked up on GitHub.
    assert github_client_mock.mock_calls == []


@pytest.mark.parametrize(
    "canonical_url, original_url, expected",
    [
        (
            "https://github.com/DataDog/new-name",
            "https://github.com/DataDog/old-name/tree/main/apis",
            "https://github.com/DataDog/new-name/tree/main/apis",
        ),
        (
            "https://github.com/DataDog/repo",
            "https://github.com/DataDog/repo",
            "https://github.com/DataDog/repo",
        ),
        (
            "https://github.com/DataDog/repo",
            "https://github.com/DataDog/repo/blob/main/apis/go.mod",
            "https://github.com/DataDog/repo/blob/main/apis/go.mod",
        ),
        (
            "https://github.com/DataDog/repo",
            "https://github.com/DataDog/repo/tree/main/apis?tab=readme-ov-file#top",
            "https://github.com/DataDog/repo/tree/main/apis",
        ),
        (
            # get_canonical_urls returns non-GitHub URLs unchanged
            "https://gitlab.com/org/repo/tree/main/apis",
            "https://gitlab.com/org/repo/tree/main/apis",
            "https://gitlab.com/org/repo/tree/main/apis",
        ),
        (
            "",
            "https://github.com/DataDog/repo/tree/main/apis",
            "https://github.com/DataDog/repo/tree/main/apis",
        ),
    ],
)
def test_keep_tree_path(canonical_url: str, original_url: str, expected: str) -> None:
    assert keep_tree_path(canonical_url, original_url) == expected


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/DataDog/repo/tree/main/apis", True),
        ("https://github.com/DataDog/repo/tree/main", True),
        ("https://github.com/DataDog/repo/blob/main/apis/go.mod", True),
        ("https://github.com/DataDog/repo", False),
        ("https://gitlab.com/org/repo/tree/main/apis", False),
        ("not a url", False),
    ],
)
def test_has_repository_path(url: str, expected: bool) -> None:
    assert has_repository_path(url) is expected


@pytest.mark.parametrize(
    "url, expected_path",
    [
        ("https://github.com/DataDog/repo/tree/main/apis", "/apis"),
        ("https://github.com/DataDog/repo/tree/main/apis/", "/apis"),
        ("https://github.com/DataDog/repo/tree/main/a/b", "/a/b"),
        ("https://github.com/DataDog/repo/tree/main", ""),
        ("https://github.com/DataDog/repo/blob/main/apis/go.mod", "/apis"),
    ],
)
@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_subdirectory_path_strips_the_ref(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
    url: str,
    expected_path: str,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    mock_extract_ref.return_value = "main"
    source_code_manager = SourceCodeManager("cache_dir", Mock())
    with patch.object(
        source_code_manager,
        "get_canonical_urls",
        return_value=(
            "https://github.com/DataDog/repo",
            "https://api.github.com/repos/DataDog/repo",
        ),
    ) as mock_get_canonical_urls:
        assert source_code_manager.get_subdirectory_path(url) == expected_path
        # Second call hits the cache and avoids repeating canonical / git lookups.
        assert source_code_manager.get_subdirectory_path(url) == expected_path
    mock_get_canonical_urls.assert_called_once_with(url)
    mock_extract_ref.assert_called_once()
    assert mock_extract_ref.call_args.args[1] == "https://github.com/DataDog/repo"
    assert mock_extract_ref.call_args.kwargs == {"git_env": NONINTERACTIVE_GIT_ENV}


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/DataDog/repo/tree/nonexistent",
        "https://github.com/DataDog/repo/tree/nonexistent/apis",
        "https://github.com/DataDog/repo/blob/nonexistent/file.py",
    ],
)
@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_subdirectory_path_returns_none_when_ref_unvalidated(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
    url: str,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    mock_extract_ref.return_value = ""
    source_code_manager = SourceCodeManager("cache_dir", Mock())
    with patch.object(
        source_code_manager,
        "get_canonical_urls",
        return_value=(
            "https://github.com/DataDog/repo",
            "https://api.github.com/repos/DataDog/repo",
        ),
    ) as mock_get_canonical_urls:
        assert source_code_manager.get_subdirectory_path(url) is None
        assert source_code_manager.get_code(url) is None
    assert mock_get_canonical_urls.call_count == 2
    assert mock_extract_ref.call_count == 2


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_subdirectory_path_returns_none_when_canonical_lookup_fails(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    source_code_manager = SourceCodeManager("cache_dir", Mock())
    url = "https://github.com/DataDog/repo/tree/main/apis"
    with patch.object(
        source_code_manager,
        "get_canonical_urls",
        return_value=("", None),
    ) as mock_get_canonical_urls:
        assert source_code_manager.get_subdirectory_path(url) is None
    mock_get_canonical_urls.assert_called_once_with(url)
    mock_extract_ref.assert_not_called()


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
def test_extract_ref_rejects_suffix_match_and_hash_substring(
    output_from_command_mock: Mock,
) -> None:
    from dd_license_attribution.artifact_management.source_code_manager import (
        extract_ref,
    )

    # "ci/release" must not match "release", and "heads" must not match as a SHA.
    output_from_command_mock.side_effect = [
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/ci/release\n",
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/main\n",
    ]
    assert extract_ref("release", "https://github.com/owner/repo") == ""

    output_from_command_mock.side_effect = [
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/main\n",
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/heads/main\n",
    ]
    assert extract_ref("heads", "https://github.com/owner/repo") == ""


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/DataDog/repo/tree/main/../../../../tmp/outside",
        "https://github.com/DataDog/repo/tree/main/apis/..",
        "https://github.com/DataDog/repo/blob/main/../../etc/passwd",
    ],
)
@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_path_traversal_rejected_in_get_subdirectory_path_and_get_code(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
    url: str,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    mock_extract_ref.return_value = "main"
    source_code_manager = SourceCodeManager("cache_dir", Mock())
    with patch.object(
        source_code_manager,
        "get_canonical_urls",
        return_value=(
            "https://github.com/DataDog/repo",
            "https://api.github.com/repos/DataDog/repo",
        ),
    ):
        assert source_code_manager.get_subdirectory_path(url) is None
        assert source_code_manager.get_code(url) is None


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_subdirectory_path_falls_back_to_mirror_for_ref_validation(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    # Original repo fails auth (returns ""), mirror succeeds.
    mock_extract_ref.side_effect = ["", "main"]
    mirror = MirrorSpec(
        original_url="https://github.com/DataDog/private-repo",
        mirror_url="https://x-access-token:tok@github.com/DataDog/private-repo",
    )
    source_code_manager = SourceCodeManager("cache_dir", Mock(), mirrors=[mirror])
    url = "https://github.com/DataDog/private-repo/tree/main/apis"
    with patch.object(
        source_code_manager,
        "get_canonical_urls",
        return_value=(
            "https://github.com/DataDog/private-repo",
            "https://api.github.com/repos/DataDog/private-repo",
        ),
    ):
        assert source_code_manager.get_subdirectory_path(url) == "/apis"
    assert mock_extract_ref.call_args_list == [
        call(
            "main/apis",
            "https://github.com/DataDog/private-repo",
            git_env=NONINTERACTIVE_GIT_ENV,
        ),
        call(
            "main/apis",
            "https://x-access-token:tok@github.com/DataDog/private-repo",
            git_env=NONINTERACTIVE_GIT_ENV,
        ),
    ]


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_subdirectory_path_does_not_cache_transient_failures_or_os_error(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    source_code_manager = SourceCodeManager("cache_dir", Mock())
    url = "https://github.com/DataDog/repo/tree/main/apis"

    # Transient canonical lookup failure (not in _canonical_urls_cache) must not poison cache.
    with patch.object(
        source_code_manager,
        "get_canonical_urls",
        side_effect=[
            ("", None),
            (
                "https://github.com/DataDog/repo",
                "https://api.github.com/repos/DataDog/repo",
            ),
            (
                "https://github.com/DataDog/repo",
                "https://api.github.com/repos/DataDog/repo",
            ),
        ],
    ):
        assert source_code_manager.get_subdirectory_path(url) is None
        # Timeout OSError returns None without caching either.
        mock_extract_ref.side_effect = [OSError("git timed out"), "main"]
        assert source_code_manager.get_subdirectory_path(url) is None
        # Subsequent call recovers and returns "/apis".
        assert source_code_manager.get_subdirectory_path(url) == "/apis"


@pytest.mark.parametrize(
    "url",
    ["https://github.com/DataDog/repo", "https://gitlab.com/org/repo/tree/main/x"],
)
@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_subdirectory_path_is_empty_without_a_repository_path(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
    url: str,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    source_code_manager = SourceCodeManager("cache_dir", Mock())
    with patch.object(
        source_code_manager, "get_canonical_urls"
    ) as mock_get_canonical_urls:
        assert source_code_manager.get_subdirectory_path(url) == ""
    mock_get_canonical_urls.assert_not_called()
    mock_extract_ref.assert_not_called()


@pytest.mark.parametrize(
    "url,expected_branch,default_branch,expected",
    [
        ("https://github.com/DataDog/repo/tree/main", "main", "main", True),
        ("https://github.com/DataDog/repo/tree/v1.0.0", "v1.0.0", "main", False),
        ("https://github.com/DataDog/repo/tree/main/apis", "main", "main", False),
        ("https://github.com/DataDog/repo/tree/missing", "", "main", False),
    ],
)
@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_is_default_branch_root(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
    url: str,
    expected_branch: str,
    default_branch: str,
    expected: bool,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    mock_extract_ref.return_value = expected_branch
    source_code_manager = SourceCodeManager(
        "cache_dir", _github_client_with_default_branch(200, default_branch)
    )
    with patch.object(
        source_code_manager,
        "get_canonical_urls",
        return_value=(
            "https://github.com/DataDog/repo",
            "https://api.github.com/repos/DataDog/repo",
        ),
    ):
        assert source_code_manager.is_default_branch_root(url) is expected


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_subdirectory_path_handles_repeated_slashes_and_mirror_ref_mapping(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    # Original fails, first mirror has no match, second mirror maps main -> mirror-main.
    mock_extract_ref.side_effect = ["", "", "", "mirror-main"]
    mirrors = [
        MirrorSpec(
            original_url="https://github.com/DataDog/repo",
            mirror_url="https://mirror1.example/DataDog/repo",
        ),
        MirrorSpec(
            original_url="https://github.com/DataDog/repo",
            mirror_url="https://mirror2.example/DataDog/repo",
            ref_mapping={(RefType.BRANCH, "main"): (RefType.BRANCH, "mirror-main")},
        ),
    ]
    source_code_manager = SourceCodeManager("cache_dir", Mock(), mirrors=mirrors)
    url = "https://github.com/DataDog/repo/tree//main/apis"
    with patch.object(
        source_code_manager,
        "get_canonical_urls",
        return_value=(
            "https://github.com/DataDog/repo",
            "https://api.github.com/repos/DataDog/repo",
        ),
    ):
        assert source_code_manager.get_subdirectory_path(url) == "/apis"


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_code_catches_os_error_from_ref_resolution(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    mock_extract_ref.side_effect = OSError("git timed out")
    source_code_manager = SourceCodeManager("cache_dir", Mock())
    url = "https://github.com/DataDog/repo/tree/main/apis"
    assert source_code_manager.get_code(url, skip_canonical_lookup=True) is None
    assert source_code_manager.has_unresolved_path(url) is True
    assert source_code_manager.has_successful_checkout(url) is False


def test_has_repository_path_detects_bare_tree_and_blob() -> None:
    assert has_repository_path("https://github.com/DataDog/repo/tree/") is True
    assert has_repository_path("https://github.com/DataDog/repo/blob/") is True


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_is_default_branch_root_plain_url_and_invalid_and_api_failure(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    mock_extract_ref.return_value = "main"
    source_code_manager = SourceCodeManager(
        "cache_dir", _github_client_with_default_branch(404, "main")
    )
    assert (
        source_code_manager.is_default_branch_root("https://github.com/DataDog/repo")
        is True
    )
    assert (
        source_code_manager.get_subdirectory_path(
            "https://github.com/DataDog/repo/tree/"
        )
        is None
    )
    with patch.object(
        source_code_manager,
        "get_canonical_urls",
        return_value=(
            "https://github.com/DataDog/repo",
            "https://api.github.com/repos/DataDog/repo",
        ),
    ):
        assert (
            source_code_manager.is_default_branch_root(
                "https://github.com/DataDog/repo/tree/main"
            )
            is False
        )


@patch("dd_license_attribution.artifact_management.source_code_manager.is_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_get_code_cached_checkout_rejects_missing_subdirectory(
    mock_now: Mock,
    mock_am_path_exists: Mock,
    mock_am_list_dir: Mock,
    mock_extract_ref: Mock,
    mock_list_dir: Mock,
    mock_path_exists: Mock,
    mock_is_dir: Mock,
) -> None:
    mock_now.return_value = datetime.fromisoformat("2022-01-01T00:00:00+00:00")
    mock_am_path_exists.return_value = True
    mock_am_list_dir.return_value = ["20220101_000000Z"]
    mock_list_dir.return_value = ["20220101_000000Z"]
    mock_path_exists.return_value = True
    mock_extract_ref.return_value = "main"
    mock_is_dir.side_effect = [True, False]

    source_code_manager = SourceCodeManager("cache_dir", Mock(), 86400)
    url = "https://github.com/DataDog/repo/tree/main/missing-dir"
    assert source_code_manager.get_code(url, skip_canonical_lookup=True) is None
    assert source_code_manager.has_unresolved_path(url) is True
    assert source_code_manager.has_successful_checkout(url) is False


@patch("dd_license_attribution.artifact_management.source_code_manager.is_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_get_code_fetches_commit_sha_and_rejects_missing_subdirectory(
    mock_am_path_exists: Mock,
    mock_am_list_dir: Mock,
    mock_extract_ref: Mock,
    mock_list_dir: Mock,
    mock_path_exists: Mock,
    mock_create_dirs: Mock,
    mock_run_command: Mock,
    mock_is_dir: Mock,
) -> None:
    mock_am_path_exists.return_value = True
    mock_am_list_dir.return_value = []
    mock_list_dir.return_value = []
    mock_path_exists.return_value = False
    mock_run_command.return_value = 0
    sha = "0123456789abcdef0123456789abcdef01234567"
    mock_extract_ref.return_value = sha
    # .git dir exists after clone, requested subdirectory does NOT exist.
    mock_is_dir.side_effect = [True, False]

    source_code_manager = SourceCodeManager("cache_dir", Mock())
    url = f"https://github.com/DataDog/repo/tree/{sha}/missing-dir"
    assert source_code_manager.get_code(url, skip_canonical_lookup=True) is None
    assert source_code_manager.has_unresolved_path(url) is True
    assert source_code_manager.has_successful_checkout(url) is False
    # Verify commit SHA used git init + fetch instead of git clone --branch=<sha>.
    commands = [c.args[0] for c in mock_run_command.call_args_list]
    assert ["git", "init", "--quiet"] in commands
    assert ["git", "fetch", "--depth", "1", "origin", sha] in commands


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
def test_extract_ref_accepts_unadvertised_full_commit_sha(
    output_from_command_mock: Mock,
) -> None:
    from dd_license_attribution.artifact_management.source_code_manager import (
        extract_ref,
    )

    sha = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
    output_from_command_mock.return_value = ""

    result = extract_ref(f"{sha}/subdir/pkg", "https://github.com/owner/repo")

    assert result == sha
    output_from_command_mock.assert_called_once_with(
        [
            "git",
            "ls-remote",
            "--",
            "https://github.com/owner/repo",
            f"{sha}/subdir/pkg",
            f"{sha}/subdir",
            sha,
        ]
    )


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_get_code_failed_clone_does_not_delete_existing_checkout_in_same_second(
    mock_now: Mock,
    mock_extract_ref: Mock,
    tmp_path: Path,
) -> None:
    mock_now.return_value = datetime.fromisoformat("2022-01-01T00:00:00+00:00")
    mock_extract_ref.return_value = "main"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    existing_checkout = cache_dir / "20220101_000000Z" / "DataDog-repo" / "main"
    existing_checkout.mkdir(parents=True)
    sentinel = existing_checkout / "live.txt"
    sentinel.write_text("in-use", encoding="utf-8")

    source_code_manager = SourceCodeManager(str(cache_dir), Mock(), 86400)
    with patch(
        "dd_license_attribution.artifact_management.source_code_manager.run_command",
        return_value=128,
    ):
        result = source_code_manager.get_code(
            "https://github.com/DataDog/repo/tree/main/sub",
            force_update=True,
            skip_canonical_lookup=True,
        )

    assert result is None
    assert sentinel.read_text(encoding="utf-8") == "in-use"
    # Staging directory must have been cleaned up.
    siblings = list(existing_checkout.parent.iterdir())
    assert siblings == [existing_checkout]


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
def test_get_code_rejects_unsafe_mapped_source_ref_outside_cache(
    mock_extract_ref: Mock,
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    sentinel = outside_dir / "keep.txt"
    sentinel.write_text("safe", encoding="utf-8")

    # Even if the mirror target ref validates, a malformed source ref containing
    # traversal segments must be rejected before creating or removing paths.
    mock_extract_ref.side_effect = lambda ref, url, git_env=None: (
        "main" if ref == "main" and "mirror.example" in url else ""
    )
    mirror = MirrorSpec(
        original_url="https://github.com/DataDog/repo",
        mirror_url="https://mirror.example/DataDog/repo",
        ref_mapping={
            (RefType.BRANCH, "../../../outside"): (RefType.BRANCH, "main"),
        },
    )
    source_code_manager = SourceCodeManager(str(cache_dir), Mock(), mirrors=[mirror])
    url = "https://github.com/DataDog/repo/tree/../../../outside/sub"

    assert source_code_manager.get_code(url, skip_canonical_lookup=True) is None
    assert source_code_manager.has_unresolved_path(url) is True
    assert sentinel.read_text(encoding="utf-8") == "safe"


@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_get_code_uses_matched_second_mirror_and_tag_ref_type(
    mock_now: Mock,
    mock_am_path_exists: Mock,
    mock_am_list_dir: Mock,
    mock_extract_ref: Mock,
    mock_list_dir: Mock,
    mock_path_exists: Mock,
    mock_create_dirs: Mock,
    mock_run_command: Mock,
) -> None:
    mock_now.return_value = datetime.fromisoformat("2022-01-01T00:00:00+00:00")
    mock_am_path_exists.return_value = True
    mock_am_list_dir.return_value = []
    mock_list_dir.return_value = []
    mock_path_exists.return_value = False
    mock_run_command.return_value = 0

    # Original and first mirror do not have v1.0; second mirror maps tag v1.0 -> branch release-1.
    def _fake_extract_ref(
        ref: str, url: str, git_env: dict[str, str] | None = None
    ) -> str:
        if url == "https://mirror2.example/DataDog/repo" and ref == "release-1":
            return "release-1"
        return ""

    mock_extract_ref.side_effect = _fake_extract_ref
    mirrors = [
        MirrorSpec(
            original_url="https://github.com/DataDog/repo",
            mirror_url="https://mirror1.example/DataDog/repo",
        ),
        MirrorSpec(
            original_url="https://github.com/DataDog/repo",
            mirror_url="https://mirror2.example/DataDog/repo",
            ref_mapping={
                (RefType.TAG, "v1.0"): (RefType.BRANCH, "release-1"),
            },
        ),
    ]
    source_code_manager = SourceCodeManager("cache_dir", Mock(), mirrors=mirrors)
    url = "https://github.com/DataDog/repo/tree/v1.0/apis"

    code_ref = source_code_manager.get_code(url, skip_canonical_lookup=True)

    assert code_ref == SourceCodeReference(
        repo_url="https://github.com/DataDog/repo",
        branch="v1.0",
        local_root_path="cache_dir/20220101_000000Z/DataDog-repo/v1.0",
        local_full_path="cache_dir/20220101_000000Z/DataDog-repo/v1.0/apis",
    )
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0],
        "cache_dir/20220101_000000Z/DataDog-repo/v1.0",
    )
    mock_run_command.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=release-1",
            "https://mirror2.example/DataDog/repo",
            staging_dir,
        ],
        env=NONINTERACTIVE_GIT_ENV,
        timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    )


def test_is_safe_git_ref_name_rejects_malformed_refs() -> None:
    from dd_license_attribution.artifact_management.source_code_manager import (
        _is_safe_git_ref_name,
    )

    assert _is_safe_git_ref_name("main") is True
    assert _is_safe_git_ref_name("release/v1.2.3") is True
    for bad_ref in [
        "",
        "@",
        "/leading",
        "trailing/",
        "trailing.",
        "a..b",
        "a//b",
        "a@{0}",
        "a\\b",
        "has space",
        "a~1",
        "a^2",
        "a:b",
        "a?b",
        "a*b",
        "a[0]",
        ".hidden",
        "dir/.hidden",
        "branch.lock",
        "a\x00b",
    ]:
        assert _is_safe_git_ref_name(bad_ref) is False, bad_ref


def test_publish_staging_checkout_publishes_and_handles_concurrent_and_force_update(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    scm = SourceCodeManager(str(cache_dir), Mock(), 86400)

    target = cache_dir / "20220101_000000Z" / "org-repo" / "main"
    target.parent.mkdir(parents=True)

    # Normal publish: staging directory is moved atomically to target.
    staging1 = cache_dir / "20220101_000000Z" / "org-repo" / "main.tmp-1"
    staging1.mkdir()
    (staging1 / "file.txt").write_text("v1", encoding="utf-8")
    scm._publish_staging_checkout(str(staging1), str(target), force_update=False)
    assert not staging1.exists()
    assert (target / "file.txt").read_text(encoding="utf-8") == "v1"

    # Concurrent publish (force_update=False): existing target wins, staging is removed.
    staging2 = cache_dir / "20220101_000000Z" / "org-repo" / "main.tmp-2"
    staging2.mkdir()
    (staging2 / "file.txt").write_text("v2", encoding="utf-8")
    scm._publish_staging_checkout(str(staging2), str(target), force_update=False)
    assert not staging2.exists()
    assert (target / "file.txt").read_text(encoding="utf-8") == "v1"

    # Forced update (force_update=True): replaces existing target cleanly.
    staging3 = cache_dir / "20220101_000000Z" / "org-repo" / "main.tmp-3"
    staging3.mkdir()
    (staging3 / "file.txt").write_text("v3", encoding="utf-8")
    scm._publish_staging_checkout(str(staging3), str(target), force_update=True)
    assert not staging3.exists()
    assert (target / "file.txt").read_text(encoding="utf-8") == "v3"
    assert list(target.parent.iterdir()) == [target]


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_has_resolved_path_tracks_successful_ref_lookups(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_extract_ref: Mock,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    mock_extract_ref.return_value = "main"
    scm = SourceCodeManager("cache_dir", Mock())
    url = "https://github.com/DataDog/repo/tree/main/apis"

    assert scm.has_resolved_path(url) is False
    with patch.object(
        scm,
        "get_canonical_urls",
        return_value=(
            "https://github.com/DataDog/repo",
            "https://api.github.com/repos/DataDog/repo",
        ),
    ):
        assert scm.get_subdirectory_path(url) == "/apis"
    assert scm.has_resolved_path(url) is True


def test_get_code_rejects_unsafe_default_branch_and_outside_cache_path(
    tmp_path: Path,
) -> None:
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    scm = SourceCodeManager(str(cache_dir), Mock(), 86400)
    assert scm._is_within_cache_dir(str(tmp_path / "outside")) is False

    with patch.object(scm, "_discover_default_branch", return_value="../escape"):
        assert (
            scm.get_code("https://github.com/DataDog/repo", skip_canonical_lookup=True)
            is None
        )

    with (
        patch.object(scm, "_discover_default_branch", return_value="main"),
        patch.object(scm, "_is_within_cache_dir", return_value=False),
    ):
        assert (
            scm.get_code("https://github.com/DataDog/repo", skip_canonical_lookup=True)
            is None
        )

    # Verify force_update rollback when rename of staging fails.
    target = cache_dir / "20220101_000000Z" / "org-repo" / "main"
    target.mkdir(parents=True)
    (target / "old.txt").write_text("old", encoding="utf-8")
    staging = cache_dir / "20220101_000000Z" / "org-repo" / "main.tmp-fail"
    staging.mkdir()
    real_rename = __import__("os").rename
    calls = {"n": 0}

    def _flaky_rename(src: str, dst: str) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("rename failed")
        real_rename(src, dst)

    with patch(
        "dd_license_attribution.artifact_management.source_code_manager.os.rename",
        side_effect=_flaky_rename,
    ):
        scm._publish_staging_checkout(str(staging), str(target), force_update=True)

    assert not staging.exists()
    assert (target / "old.txt").read_text(encoding="utf-8") == "old"


@patch("dd_license_attribution.artifact_management.source_code_manager.extract_ref")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
def test_get_code_propagates_staging_publish_failure_without_valid_target(
    mock_now: Mock,
    mock_extract_ref: Mock,
    tmp_path: Path,
    caplog: LogCaptureFixture,
) -> None:
    mock_now.return_value = datetime.fromisoformat("2022-01-01T00:00:00+00:00")
    mock_extract_ref.return_value = "main"
    cache_dir = tmp_path / "cache"
    cache_dir.mkdir()
    mirror = MirrorSpec(
        original_url="https://github.com/DataDog/repo",
        mirror_url="https://user:secret-token@mirror.example/DataDog/repo",
    )
    scm = SourceCodeManager(str(cache_dir), Mock(), 86400, mirrors=[mirror])
    url = "https://github.com/DataDog/repo/tree/main/apis"

    with (
        caplog.at_level(logging.ERROR, logger="dd_license_attribution"),
        patch(
            "dd_license_attribution.artifact_management.source_code_manager.run_command",
            return_value=0,
        ),
        patch(
            "dd_license_attribution.artifact_management.source_code_manager.os.rename",
            side_effect=OSError("rename failed"),
        ),
    ):
        assert scm.get_code(url, skip_canonical_lookup=True) is None

    assert scm.has_successful_checkout(url) is False
    assert scm.has_unresolved_path(url) is True
    assert "https://github.com/DataDog/repo" in caplog.text
    assert "secret-token" not in caplog.text

    # Missing staging directory must also fail when destination has no .git dir,
    # and succeed only when destination holds a verified .git checkout.
    missing_staging = cache_dir / "20220101_000000Z" / "DataDog-repo" / "missing.tmp"
    target = cache_dir / "20220101_000000Z" / "DataDog-repo" / "main"
    assert (
        scm._publish_staging_checkout(
            str(missing_staging), str(target), force_update=False
        )
        is False
    )
    (target / ".git").mkdir(parents=True)
    assert (
        scm._publish_staging_checkout(
            str(missing_staging), str(target), force_update=False
        )
        is True
    )


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.source_code_manager.run_command")
@patch("dd_license_attribution.artifact_management.source_code_manager.create_dirs")
@patch("dd_license_attribution.artifact_management.source_code_manager.path_exists")
@patch("dd_license_attribution.artifact_management.source_code_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
@patch("dd_license_attribution.artifact_management.artifact_manager.get_datetime_now")
@patch.object(
    SourceCodeManager, "_publish_staging_checkout", lambda self, *args, **kwargs: True
)
def test_get_code_preserves_advertised_tag_type_for_mirror_mapping(
    mock_now: Mock,
    mock_am_path_exists: Mock,
    mock_am_list_dir: Mock,
    mock_list_dir: Mock,
    mock_path_exists: Mock,
    mock_create_dirs: Mock,
    mock_run_command: Mock,
    mock_output_from_command: Mock,
) -> None:
    mock_now.return_value = datetime.fromisoformat("2022-01-01T00:00:00+00:00")
    mock_am_path_exists.return_value = True
    mock_am_list_dir.return_value = []
    mock_list_dir.return_value = []
    mock_path_exists.return_value = False
    mock_run_command.return_value = 0
    # Original repository advertises v1.0 as a tag.
    mock_output_from_command.return_value = (
        "72a11341aa684010caf1ca5dee779f0e7e84dfe9\trefs/tags/v1.0\n"
    )
    mirror = MirrorSpec(
        original_url="https://github.com/DataDog/repo",
        mirror_url="https://mirror.example/DataDog/repo",
        ref_mapping={(RefType.TAG, "v1.0"): (RefType.BRANCH, "release-1")},
    )
    scm = SourceCodeManager("cache_dir", Mock(), mirrors=[mirror])
    url = "https://github.com/DataDog/repo/tree/v1.0/apis"

    code_ref = scm.get_code(url, skip_canonical_lookup=True)

    assert code_ref == SourceCodeReference(
        repo_url="https://github.com/DataDog/repo",
        branch="v1.0",
        local_root_path="cache_dir/20220101_000000Z/DataDog-repo/v1.0",
        local_full_path="cache_dir/20220101_000000Z/DataDog-repo/v1.0/apis",
    )
    staging_dir = _assert_staging_dir(
        mock_create_dirs.call_args.args[0],
        "cache_dir/20220101_000000Z/DataDog-repo/v1.0",
    )
    mock_run_command.assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=release-1",
            "https://mirror.example/DataDog/repo",
            staging_dir,
        ],
        env=NONINTERACTIVE_GIT_ENV,
        timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    )


@patch(
    "dd_license_attribution.artifact_management.source_code_manager.output_from_command"
)
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_unadvertised_full_sha_stays_provisional_until_checkout(
    mock_path_exists: Mock,
    mock_list_dir: Mock,
    mock_output_from_command: Mock,
) -> None:
    mock_path_exists.return_value = True
    mock_list_dir.return_value = []
    mock_output_from_command.return_value = ""
    scm = SourceCodeManager("cache_dir", Mock())
    sha = "a1b2c3d4e5f60718293a4b5c6d7e8f9012345678"
    url = f"https://github.com/DataDog/repo/tree/{sha}/apis"

    with patch.object(
        scm,
        "get_canonical_urls",
        return_value=(
            "https://github.com/DataDog/repo",
            "https://api.github.com/repos/DataDog/repo",
        ),
    ):
        assert scm.get_subdirectory_path(url) == "/apis"

    # Format-only SHA resolution is provisional and must not mark the path verified.
    assert scm.has_resolved_path(url) is False
