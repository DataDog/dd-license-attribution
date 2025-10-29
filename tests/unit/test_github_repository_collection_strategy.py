# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from unittest.mock import call

import pytest
import pytest_mock
from agithub.GitHub import GitHub

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy import (
    GitHubRepositoryMetadataCollectionStrategy,
)


class GitUrlParseMock:
    def __init__(
        self, valid: bool, platform: str, owner: str | None, repo: str | None
    ) -> None:
        self.valid = valid
        self.platform = platform
        self.owner = owner
        self.repo = repo
        self.github = platform == "github"


def test_github_repository_collection_strategy_returns_same_metadata_if_not_a_github_repo(
    mocker: pytest_mock.MockFixture,
) -> None:
    github_client_mock = mocker.Mock(spec_set=GitHub)

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(False, "not_github", None, None),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=github_client_mock
    )

    initial_metadata = [
        Metadata(
            name="",
            version="",
            origin="not_a_github_purl",
            local_src_path="",
            license=[],
            copyright=[],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)
    assert updated_metadata == initial_metadata

    github_parse_mock.assert_called_once_with("not_a_github_purl")


class GitHubClientMock:
    def __init__(self, repo_info: str) -> None:
        # this needs to be accessed: self.repos[owner][repo].sbom and return sbom_input
        self.repos = {"test_owner": {"test_repo": repo_info}}


def test_github_repository_collection_strategy_raise_exception_if_error_calling_github_repo_api(
    mocker: pytest_mock.MockFixture,
) -> None:
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (404, "Not Found")
    gh_mock = GitHubClientMock(repo_info_mock)

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=[],
            copyright=[],
        )
    ]

    with pytest.raises(
        ValueError,
        match="Failed to get repository information for test_owner/test_repo",
    ):
        strategy.augment_metadata(initial_metadata)

    github_parse_mock.assert_called_once_with("test_purl")
    repo_info_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_returns_uses_repo_owner_when_no_copyright_set(
    mocker: pytest_mock.MockFixture,
) -> None:
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (
        200,
        {"owner": {"login": "test_owner"}, "license": {"spdx_id": "test_license"}},
    )
    gh_mock = GitHubClientMock(repo_info_mock)

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=[],
            copyright=[],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=["test_license"],
            copyright=["test_owner"],
        )
    ]

    assert updated_metadata == expected_metadata

    github_parse_mock.assert_called_once_with("test_purl")
    repo_info_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_do_not_override_license_on_noassertion_result(
    mocker: pytest_mock.MockFixture,
) -> None:
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (
        200,
        {"owner": {"login": "test_owner"}, "license": {"spdx_id": "NOASSERTION"}},
    )
    gh_mock = GitHubClientMock(repo_info_mock)

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl_1",
            local_src_path=None,
            license=["test_license"],
            copyright=[],
        ),
        Metadata(
            name=None,
            version=None,
            origin="test_purl_2",
            local_src_path=None,
            license=[],
            copyright=[],
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == initial_metadata

    github_parse_mock.assert_has_calls([call("test_purl_1"), call("test_purl_2")])

    assert repo_info_mock.get.call_count == 2


def test_github_repository_collection_strategy_do_not_override_license_if_previously_set_and_updating_copyright(
    mocker: pytest_mock.MockFixture,
) -> None:
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (
        200,
        {"owner": {"login": "test_owner"}, "license": {"spdx_id": "test_license"}},
    )
    gh_mock = GitHubClientMock(repo_info_mock)

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=["test_license_preset"],
            copyright=[],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=["test_license_preset"],
            copyright=["test_owner"],
        )
    ]

    assert updated_metadata == expected_metadata

    github_parse_mock.assert_called_once_with("test_purl")
    repo_info_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_do_not_override_copyright_if_previously_set_and_updating_license(
    mocker: pytest_mock.MockFixture,
) -> None:
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (
        200,
        {"owner": {"login": "test_owner"}, "license": {"spdx_id": "test_license"}},
    )
    gh_mock = GitHubClientMock(repo_info_mock)

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=[],
            copyright=["test_copyright"],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=["test_license"],
            copyright=["test_copyright"],
        )
    ]

    assert updated_metadata == expected_metadata

    github_parse_mock.assert_called_once_with("test_purl")
    repo_info_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_follows_redirects(
    mocker: pytest_mock.MockFixture,
) -> None:
    # GitHub API returns 301 with a redirect URL for moved repositories
    old_repo_mock = mocker.Mock()
    old_repo_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repositories/95208491"},
    )

    # Mock the repositories endpoint
    new_repo_mock = mocker.Mock()
    new_repo_mock.get.return_value = (
        200,
        {
            "owner": {"login": "aboutcode-org"},
            "license": {"spdx_id": "MIT"},
        },
    )

    # Create a mock that supports [] operator
    repositories_mock = mocker.Mock()
    repositories_mock.__getitem__ = mocker.Mock(return_value=new_repo_mock)

    gh_mock = mocker.Mock()
    gh_mock.repos = {
        "nexB": {"pkginfo2": old_repo_mock},
    }
    # Mock the repositories endpoint to be subscriptable
    gh_mock.__getitem__ = mocker.Mock(
        side_effect=lambda key: (
            repositories_mock if key == "repositories" else mocker.Mock()
        )
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "nexB", "pkginfo2"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="https://github.com/nexB/pkginfo2",
            local_src_path=None,
            license=[],
            copyright=[],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="https://github.com/nexB/pkginfo2",
            local_src_path=None,
            license=["MIT"],
            copyright=["aboutcode-org"],
        )
    ]

    assert updated_metadata == expected_metadata

    github_parse_mock.assert_called_once_with("https://github.com/nexB/pkginfo2")
    old_repo_mock.get.assert_called_once_with()
    new_repo_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_raises_on_unparseable_redirect(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Test that we raise an error when we can't parse the redirect URL
    repo_mock = mocker.Mock()
    repo_mock.get.return_value = (
        301,
        {"url": "https://not-github.com/some/path"},  # Unparseable URL
    )

    gh_mock = mocker.Mock()
    gh_mock.repos = {"owner": {"repo": repo_mock}}

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "owner", "repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=[],
            copyright=[],
        )
    ]

    # Should raise ValueError when redirect URL can't be parsed
    with pytest.raises(
        ValueError, match="Failed to get repository information for owner/repo"
    ):
        strategy.augment_metadata(initial_metadata)

    github_parse_mock.assert_called_once_with("test_purl")
    repo_mock.get.assert_called_once_with()
