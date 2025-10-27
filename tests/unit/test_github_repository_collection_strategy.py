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


def test_github_repository_collection_strategy_follows_redirects_on_301(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Create separate mocks for old and new repos
    old_repo_mock = mocker.Mock()
    old_repo_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repos/new_owner/new_repo"},
    )

    new_repo_mock = mocker.Mock()
    new_repo_mock.get.return_value = (
        200,
        {
            "owner": {"login": "new_owner"},
            "license": {"spdx_id": "test_license"},
        },
    )

    # Create a mock GitHub client that handles both repos
    gh_mock = mocker.Mock()
    gh_mock.repos = {
        "old_owner": {"old_repo": old_repo_mock},
        "new_owner": {"new_repo": new_repo_mock},
    }

    # Mock parse_git_url to handle both original and redirect URLs
    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url"
    )
    github_parse_mock.side_effect = [
        GitUrlParseMock(True, "github", "old_owner", "old_repo"),
        GitUrlParseMock(True, "github", "new_owner", "new_repo"),
    ]

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
            copyright=["new_owner"],
        )
    ]

    assert updated_metadata == expected_metadata

    # Should be called twice: once for original URL, once for redirect URL
    assert github_parse_mock.call_count == 2
    github_parse_mock.assert_has_calls(
        [call("test_purl"), call("https://api.github.com/repos/new_owner/new_repo")]
    )
    # Should be called once for old repo (301), once for new repo (200)
    old_repo_mock.get.assert_called_once_with()
    new_repo_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_follows_multiple_redirects(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Create mocks for a chain of redirects: repo1 -> repo2 -> repo3 -> final_repo
    repo1_mock = mocker.Mock()
    repo1_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repos/owner2/repo2"},
    )

    repo2_mock = mocker.Mock()
    repo2_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repos/owner3/repo3"},
    )

    repo3_mock = mocker.Mock()
    repo3_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repos/final_owner/final_repo"},
    )

    final_repo_mock = mocker.Mock()
    final_repo_mock.get.return_value = (
        200,
        {
            "owner": {"login": "final_owner"},
            "license": {"spdx_id": "MIT"},
        },
    )

    # Create a mock GitHub client that handles all repos
    gh_mock = mocker.Mock()
    gh_mock.repos = {
        "owner1": {"repo1": repo1_mock},
        "owner2": {"repo2": repo2_mock},
        "owner3": {"repo3": repo3_mock},
        "final_owner": {"final_repo": final_repo_mock},
    }

    # Mock parse_git_url to handle all URLs in the redirect chain
    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url"
    )
    github_parse_mock.side_effect = [
        GitUrlParseMock(True, "github", "owner1", "repo1"),
        GitUrlParseMock(True, "github", "owner2", "repo2"),
        GitUrlParseMock(True, "github", "owner3", "repo3"),
        GitUrlParseMock(True, "github", "final_owner", "final_repo"),
    ]

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
            license=["MIT"],
            copyright=["final_owner"],
        )
    ]

    assert updated_metadata == expected_metadata

    # Should follow all redirects
    assert github_parse_mock.call_count == 4
    repo1_mock.get.assert_called_once_with()
    repo2_mock.get.assert_called_once_with()
    repo3_mock.get.assert_called_once_with()
    final_repo_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_skips_repo_on_too_many_redirects(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Create a mock that always returns 301 to simulate infinite redirects
    redirect_mock = mocker.Mock()
    redirect_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repos/owner/repo"},
    )

    gh_mock = mocker.Mock()
    gh_mock.repos = {"owner": {"repo": redirect_mock}}

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url"
    )
    # Return the same repo each time to simulate a redirect loop
    github_parse_mock.return_value = GitUrlParseMock(True, "github", "owner", "repo")

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

    # Repository should be completely dropped when too many redirects occur
    assert updated_metadata == []
    assert len(updated_metadata) == 0

    # Should stop after MAX_REDIRECTS (5) + initial request = 6 calls
    assert redirect_mock.get.call_count == 6


def test_github_repository_collection_strategy_follows_repository_id_redirect(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Test redirect to /repositories/{id} format (the actual GitHub behavior)
    old_repo_mock = mocker.Mock()
    old_repo_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repositories/48783244"},
    )

    new_repo_mock = mocker.Mock()
    new_repo_mock.get.return_value = (
        200,
        {
            "owner": {"login": "sindresorhus"},
            "license": {"spdx_id": "MIT"},
        },
    )

    # Create a mock GitHub client
    gh_mock = mocker.Mock()
    gh_mock.repos = {"avajs": {"find-cache-dir": old_repo_mock}}
    gh_mock.repositories = {"48783244": new_repo_mock}

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "avajs", "find-cache-dir"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="git+https://github.com/avajs/find-cache-dir.git",
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
            origin="git+https://github.com/avajs/find-cache-dir.git",
            local_src_path=None,
            license=["MIT"],
            copyright=["sindresorhus"],
        )
    ]

    assert updated_metadata == expected_metadata

    # Should be called once for original URL only
    github_parse_mock.assert_called_once_with(
        "git+https://github.com/avajs/find-cache-dir.git"
    )
    old_repo_mock.get.assert_called_once_with()
    new_repo_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_handles_mixed_redirect_formats(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Test chain with both repository ID and git URL format redirects
    repo1_mock = mocker.Mock()
    repo1_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repositories/12345"},
    )

    repo2_mock = mocker.Mock()
    repo2_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repos/intermediate/repo"},
    )

    repo3_mock = mocker.Mock()
    repo3_mock.get.return_value = (
        200,
        {
            "owner": {"login": "final_owner"},
            "license": {"spdx_id": "Apache-2.0"},
        },
    )

    gh_mock = mocker.Mock()
    gh_mock.repos = {
        "owner1": {"repo1": repo1_mock},
        "intermediate": {"repo": repo2_mock},
    }
    gh_mock.repositories = {"12345": repo2_mock}

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url"
    )
    github_parse_mock.side_effect = [
        GitUrlParseMock(True, "github", "owner1", "repo1"),
        GitUrlParseMock(True, "github", "intermediate", "repo"),
    ]

    repo2_mock.get.side_effect = [
        (301, {"url": "https://api.github.com/repos/intermediate/repo"}),
        (
            200,
            {"owner": {"login": "final_owner"}, "license": {"spdx_id": "Apache-2.0"}},
        ),
    ]

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
            license=["Apache-2.0"],
            copyright=["final_owner"],
        )
    ]

    assert updated_metadata == expected_metadata
    assert repo1_mock.get.call_count == 1
    assert repo2_mock.get.call_count == 2


def test_github_repository_collection_strategy_skips_repo_on_unparseable_redirect(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Test redirect with unparseable URL - package should be dropped
    repo_mock = mocker.Mock()
    repo_mock.get.return_value = (
        301,
        {"url": "https://not-github.com/some/path"},
    )

    gh_mock = mocker.Mock()
    gh_mock.repos = {"owner": {"repo": repo_mock}}

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url"
    )
    github_parse_mock.side_effect = [
        GitUrlParseMock(True, "github", "owner", "repo"),
        GitUrlParseMock(False, "unknown", None, None),  # Unparseable redirect
    ]

    logger_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.logger"
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

    # Package should be dropped when redirect can't be parsed
    assert updated_metadata == []

    repo_mock.get.assert_called_once_with()
    logger_mock.warning.assert_called_once_with(
        "Unable to parse redirect URL: https://not-github.com/some/path"
    )
