from unittest.mock import call
import pytest
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.github_repository_collection_strategy import (
    GitHubRepositoryMetadataCollectionStrategy,
)
from agithub.GitHub import GitHub


def test_github_repository_collection_strategy_returns_same_metadata_if_not_a_github_repo(
    mocker,
):
    github_client_mock = mocker.Mock(spec_set=GitHub)
    purl_parser_object = mocker.Mock()

    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_repository_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.return_value = (None, None)

    strategy = GitHubRepositoryMetadataCollectionStrategy(
        github_client=github_client_mock
    )

    initial_metadata = [
        Metadata(
            name="",
            version="",
            origin="not_a_github_purl",
            license="",
            copyright="",
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)
    assert updated_metadata == initial_metadata

    purl_parser_object.get_github_owner_and_repo.assert_called_once_with(
        "not_a_github_purl"
    )


class GitHubClientMock:
    def __init__(self, repo_info):
        # this needs to be accessed: self.repos[owner][repo].sbom and return sbom_input
        self.repos = {"test_owner": {"test_repo": repo_info}}


def test_github_repository_collection_strategy_raise_exception_if_error_calling_github_repo_api(
    mocker,
):
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (404, "Not Found")
    gh_mock = GitHubClientMock(repo_info_mock)

    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_repository_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.return_value = (
        "test_owner",
        "test_repo",
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            license=None,
            copyright=None,
        )
    ]

    with pytest.raises(
        ValueError,
        match="Failed to get repository information for test_owner/test_repo",
    ):
        strategy.augment_metadata(initial_metadata)

    purl_parser_object.get_github_owner_and_repo.assert_called_once_with("test_purl")
    repo_info_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_returns_uses_repo_owner_when_no_copyright_set(
    mocker,
):
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (
        200,
        {"owner": {"login": "test_owner"}, "license": {"spdx_id": "test_license"}},
    )
    gh_mock = GitHubClientMock(repo_info_mock)

    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_repository_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.return_value = (
        "test_owner",
        "test_repo",
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            license=None,
            copyright=None,
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            license=["test_license"],
            copyright=["test_owner"],
        )
    ]

    assert updated_metadata == expected_metadata

    purl_parser_object.get_github_owner_and_repo.assert_called_once_with("test_purl")
    repo_info_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_do_not_override_license_on_noassertion_result(
    mocker,
):
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (
        200,
        {"owner": {"login": "test_owner"}, "license": {"spdx_id": "NOASSERTION"}},
    )
    gh_mock = GitHubClientMock(repo_info_mock)

    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_repository_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.return_value = (
        "test_owner",
        "test_repo",
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl_1",
            license="test_license",
            copyright=None,
        ),
        Metadata(
            name=None,
            version=None,
            origin="test_purl_2",
            license=None,
            copyright=None,
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == initial_metadata

    purl_parser_object.get_github_owner_and_repo.assert_has_calls(
        [call("test_purl_1"), call("test_purl_2")]
    )

    assert repo_info_mock.get.call_count == 2


def test_github_repository_collection_strategy_do_not_override_license_if_previously_set_and_updating_copyright(
    mocker,
):
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (
        200,
        {"owner": {"login": "test_owner"}, "license": {"spdx_id": "test_license"}},
    )
    gh_mock = GitHubClientMock(repo_info_mock)

    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_repository_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.return_value = (
        "test_owner",
        "test_repo",
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            license=["test_license_preset"],
            copyright=None,
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            license=["test_license_preset"],
            copyright=["test_owner"],
        )
    ]

    assert updated_metadata == expected_metadata

    purl_parser_object.get_github_owner_and_repo.assert_called_once_with("test_purl")
    repo_info_mock.get.assert_called_once_with()


def test_github_repository_collection_strategy_do_not_override_copyright_if_previously_set_and_updating_license(
    mocker,
):
    repo_info_mock = mocker.Mock()
    repo_info_mock.get.return_value = (
        200,
        {"owner": {"login": "test_owner"}, "license": {"spdx_id": "test_license"}},
    )
    gh_mock = GitHubClientMock(repo_info_mock)

    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_repository_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.return_value = (
        "test_owner",
        "test_repo",
    )

    strategy = GitHubRepositoryMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            license=None,
            copyright=["test_copyright"],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name=None,
            version=None,
            origin="test_purl",
            license=["test_license"],
            copyright=["test_copyright"],
        )
    ]

    assert updated_metadata == expected_metadata

    purl_parser_object.get_github_owner_and_repo.assert_called_once_with("test_purl")
    repo_info_mock.get.assert_called_once_with()
