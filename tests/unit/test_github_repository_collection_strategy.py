# SPDX-License-Identifier: Apache-2.0
#
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
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "not_a_github_purl",
        None,
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(False, "not_github", None, None),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=github_client_mock, source_code_manager=source_code_manager_mock
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

    # parse_git_url is not called when api_url is None (early return)
    github_parse_mock.assert_not_called()


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

    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=gh_mock, source_code_manager=source_code_manager_mock
    )

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

    # parse_git_url is called with the canonical URL returned by get_canonical_urls
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
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

    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=gh_mock, source_code_manager=source_code_manager_mock
    )

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
            origin="https://github.com/test_owner/test_repo",
            local_src_path=None,
            license=["test_license"],
            copyright=["test_owner"],
        )
    ]

    assert updated_metadata == expected_metadata

    # parse_git_url is called with the canonical URL returned by get_canonical_urls
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
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

    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=gh_mock, source_code_manager=source_code_manager_mock
    )

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

    expected_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="https://github.com/test_owner/test_repo",
            local_src_path=None,
            license=["test_license"],
            copyright=[
                "test_owner"
            ],  # Copyright is populated even though license was already set
        ),
        Metadata(
            name=None,
            version=None,
            origin="https://github.com/test_owner/test_repo",
            local_src_path=None,
            license=[],
            copyright=["test_owner"],
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == expected_metadata

    # parse_git_url is called with the canonical URL returned by get_canonical_urls
    github_parse_mock.assert_has_calls(
        [
            call("https://github.com/test_owner/test_repo"),
            call("https://github.com/test_owner/test_repo"),
        ]
    )

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

    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=gh_mock, source_code_manager=source_code_manager_mock
    )

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
            origin="https://github.com/test_owner/test_repo",
            local_src_path=None,
            license=["test_license_preset"],
            copyright=["test_owner"],
        )
    ]

    assert updated_metadata == expected_metadata

    # parse_git_url is called with the canonical URL returned by get_canonical_urls
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
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

    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=gh_mock, source_code_manager=source_code_manager_mock
    )

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
            origin="https://github.com/test_owner/test_repo",
            local_src_path=None,
            license=["test_license"],
            copyright=["test_copyright"],
        )
    ]

    assert updated_metadata == expected_metadata

    # parse_git_url is called with the canonical URL returned by get_canonical_urls
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    repo_info_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_follows_redirects(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Mock the repositories endpoint
    new_repo_mock = mocker.Mock()
    new_repo_mock.get.return_value = (
        200,
        {
            "owner": {"login": "aboutcode-org"},
            "license": {"spdx_id": "MIT"},
        },
    )

    gh_mock = mocker.Mock()
    gh_mock.repos = {
        "aboutcode-org": {"pkginfo": new_repo_mock},
    }

    # Mock source_code_manager to simulate get_canonical_urls following the redirect
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/aboutcode-org/pkginfo",  # Canonical URL after redirect
        "https://api.github.com/repos/aboutcode-org/pkginfo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "aboutcode-org", "pkginfo"),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=gh_mock, source_code_manager=source_code_manager_mock
    )

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
            origin="https://github.com/aboutcode-org/pkginfo",
            local_src_path=None,
            license=["MIT"],
            copyright=["aboutcode-org"],
        )
    ]

    assert updated_metadata == expected_metadata

    # parse_git_url is called with the canonical URL returned by get_canonical_urls
    github_parse_mock.assert_called_once_with(
        "https://github.com/aboutcode-org/pkginfo"
    )
    new_repo_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_raises_on_unparseable_redirect(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Test that we handle the case when get_canonical_urls returns None for api_url
    # (e.g., when redirect points to a non-GitHub URL)
    gh_mock = mocker.Mock()

    # Mock source_code_manager to return None for api_url (redirect failed or not a GitHub URL)
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://not-github.com/some/path",  # Unparseable URL
        None,  # No API URL because it's not a valid GitHub URL
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_repository_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(False, "not-github", None, None),
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=gh_mock, source_code_manager=source_code_manager_mock
    )

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

    # Should return the original metadata unchanged when not a GitHub URL
    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == initial_metadata
    # parse_git_url is not called when api_url is None (early return)
    github_parse_mock.assert_not_called()
