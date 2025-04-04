# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from datetime import datetime
from unittest.mock import call

import pytest
import pytest_mock

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.source_code_manager import (
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
def test_source_code_manager_get_non_cached_code(
    mocker: pytest_mock.MockFixture,
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
    if mocked_parser_results.path_raw != "":
        run_command_mock = mocker.patch(
            "dd_license_attribution.artifact_management.source_code_manager.run_command",
            return_value=0,
        )
    if (
        mocked_parser_results.branch == ""
        and not "test_branch" in mocked_parser_results.path_raw
    ):
        output_from_command_mock = mocker.patch(
            "dd_license_attribution.artifact_management.source_code_manager.output_from_command",
            return_value="ref: refs/heads/main\tHEAD\n72a11341aa684010caf1ca5dee779f0e7e84dfe9\tHEAD\n",
        )
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[
            datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
        ],
    )
    git_url_parse_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.parse_git_url",
        return_value=mocked_parser_results,
    )
    artifact_file_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=[],
    )
    source_code_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.list_dir",
        return_value=[],
    )

    source_code_manager = SourceCodeManager("cache_dir", 86400)

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
    git_url_parse_mock.assert_called_once_with(resource_url)
    artifact_file_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")


def test_source_code_manager_get_cached_code(mocker: pytest_mock.MockFixture) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        return_value=datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
    )
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"
    git_url_parse_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            owner="test_owner",
            repo="test_repo",
            branch="test_branch",
            path="test_dir",
            path_raw="/tree/test_branch/test_dir",
        ),
    )
    artifact_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    source_code_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=["20211231_001000Z"],
    )
    source_code_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.list_dir",
        return_value=["20211231_001000Z"],
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.run_command",
        return_value=0,
    )

    source_code_manager = SourceCodeManager("cache_dir", 86400)
    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20211231_001000Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20211231_001000Z/test_owner-test_repo/test_branch/test_dir",
    )

    assert code_ref == expected_source_code_reference
    assert get_datetime_now_mock.call_count == 1
    git_url_parse_mock.assert_called_once_with(request_url)
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    source_code_path_exists_mock.assert_called_once_with(
        "cache_dir/20211231_001000Z/test_owner-test_repo/test_branch"
    )
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    source_code_list_dir_mock.assert_called_once_with("cache_dir")

    run_command_mock.assert_called_once_with(
        f"git ls-remote {expected_source_code_reference.repo_url} {expected_source_code_reference.branch} | grep -q {expected_source_code_reference.branch}"
    )


def test_source_code_manager_get_non_cached_code_because_it_expired(
    mocker: pytest_mock.MockFixture,
) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[
            datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
        ],
    )
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"

    mock_create_dirs = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.create_dirs"
    )

    git_url_parse_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            owner="test_owner",
            repo="test_repo",
            branch="test_branch",
            path="test_dir",
            path_raw="/tree/test_branch/test_dir",
        ),
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=["20210101_000000Z"],
    )
    source_code_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.list_dir",
        return_value=["20210101_000000Z"],
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.run_command",
        return_value=0,
    )

    source_code_manager = SourceCodeManager("cache_dir", 86400)
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
    git_url_parse_mock.assert_called_once_with(request_url)
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


def test_source_code_manager_get_non_cached_code_because_force_update(
    mocker: pytest_mock.MockFixture,
) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[
            datetime.fromisoformat("2022-01-01T00:00:05+00:00"),
        ],
    )
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"
    git_url_parse_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            owner="test_owner",
            repo="test_repo",
            branch="test_branch",
            path="test_dir",
            path_raw="/tree/test_branch/test_dir",
        ),
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.run_command",
        return_value=0,
    )

    artifact_mock_list_dir = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=["20210101_000000Z"],
    )
    source_code_mock_list_dir = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.list_dir",
        return_value=["20210101_000000Z"],
    )
    mock_create_dirs = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.create_dirs"
    )
    source_code_manager = SourceCodeManager("cache_dir", 86400)
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
    git_url_parse_mock.assert_called_once_with(request_url)
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


def test_non_github_returns_none(mocker: pytest_mock.MockFixture) -> None:
    git_url_parse_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.parse_git_url",
        return_value=GitUrlParseMock(
            valid=False,
            owner="",
            repo="",
            branch="",
            path="",
            path_raw="",
        ),
    )

    mock_path_exists = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    mock_list_dir = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=[],
    )

    source_code_manager = SourceCodeManager("cache_dir", 86400)
    request_url = (
        "https://non_github.com/test_owner/test_repo/tree/test_branch/test_dir"
    )
    code_ref = source_code_manager.get_code(request_url)

    assert code_ref is None
    git_url_parse_mock.assert_called_once_with(request_url)
    mock_path_exists.assert_called_once_with("cache_dir")
    mock_list_dir.assert_called_once_with("cache_dir")


def test_artifact_manager_get_non_cached_code_for_ambiguous_branch_names(
    mocker: pytest_mock.MockFixture,
) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        return_value=datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
    )
    request_url = "https://github.com/test_owner/test_repo/tree/test_branch/test_dir"
    git_url_parse_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            owner="test_owner",
            repo="test_repo",
            branch="test_branch/test_dir",
            path="",
            path_raw="/tree/test_branch/test_dir",
        ),
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=["20210101_000000Z"],
    )
    source_code_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.list_dir",
        return_value=["20210101_000000Z"],
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.source_code_manager.run_command",
        return_value=0,
    )

    source_code_manager = SourceCodeManager("cache_dir", 86400)

    code_ref = source_code_manager.get_code(request_url)

    expected_source_code_reference = SourceCodeReference(
        repo_url="https://github.com/test_owner/test_repo",
        branch="test_branch",
        local_root_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch",
        local_full_path="cache_dir/20220101_000000Z/test_owner-test_repo/test_branch/test_dir",
    )

    assert code_ref == expected_source_code_reference
    assert get_datetime_now_mock.call_count == 1
    git_url_parse_mock.assert_called_once_with(request_url)
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


def test_source_code_manager_fails_init_if_cache_dir_is_not_a_directory(
    mocker: pytest_mock.MockFixture,
) -> None:
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=False,
    )

    with pytest.raises(ValueError) as e:
        SourceCodeManager("cache_dir", 86400)

    assert str(e.value) == "Local cache directory cache_dir does not exist"
    path_exists_mock.assert_called_once_with("cache_dir")


def test_source_code_manager_fails_init_if_cache_dir_contains_unexpected_files(
    mocker: pytest_mock.MockFixture,
) -> None:
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=["unexpected_file"],
    )

    with pytest.raises(ValueError) as e:
        SourceCodeManager("cache_dir", 86400)

    assert (
        str(e.value)
        == "Local cache directory cache_dir has invalid subdirectory, are you sure it is a cache directory?"
    )
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")
