from unittest.mock import call
import pytest
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy import (
    GitHubSbomMetadataCollectionStrategy,
)
from agithub.GitHub import GitHub


def test_github_sbom_collection_strategy_returns_same_metadata_if_not_a_github_repo(
    mocker,
):
    github_client_mock = mocker.Mock(spec_set=GitHub)
    purl_parser_object = mocker.Mock()

    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.return_value = (None, None)

    strategy = GitHubSbomMetadataCollectionStrategy(github_client=github_client_mock)

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


class SbomMockWrapper:
    def __init__(self, sbom_input):
        self.sbom = sbom_input


class GitHubClientMock:
    def __init__(self, sbom_input):
        # this needs to be accessed: self.repos[owner][repo].sbom and return sbom_input
        self.repos = {"owner": {"repo": {"dependency-graph": sbom_input}}}


def test_github_sbom_collection_strategy_raise_exception_if_error_calling_github_sbom_api(
    mocker,
):
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (404, "Not Found")
    gh_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.return_value = ("owner", "repo")

    strategy = GitHubSbomMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name="",
            version="",
            origin="test_purl",
            license="",
            copyright="",
        )
    ]

    with pytest.raises(ValueError, match="Failed to get SBOM for owner/repo"):
        strategy.augment_metadata(initial_metadata)

    purl_parser_object.get_github_owner_and_repo.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_with_no_new_info_skips_actions_and_returns_original_info(
    mocker,
):
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {
            "sbom": {
                "packages": [
                    {"name": "action_github_checkout"},  # this should be skipped
                    {
                        "name": "package1"
                    },  # this was already in the metadata, we keep the old information since there is none new
                ]
            }
        },
    )
    gh_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.return_value = ("owner", "repo")

    strategy = GitHubSbomMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name="package1",
            version="1.0",
            origin="test_purl",
            license="APACHE-2.0",
            copyright="Datadog Inc.",
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)
    assert updated_metadata == initial_metadata

    purl_parser_object.get_github_owner_and_repo.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_with_new_info_is_not_lost_in_repeated_package(
    mocker,
):
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {
            "sbom": {
                "packages": [
                    {"name": "action_github_checkout"},  # this should be skipped
                    {  # this is the package from the orignal metadata with new information
                        "name": "package1",
                        "versionInfo": "2.0",
                        "licenseDeclared": "APACHE-2.0",
                        "downloadLocation": "test_purl",
                    },
                    {  # this was already in the previous line, we keep the new information and not override with this.
                        "name": "package1"
                    },
                    {  # this is a package that is not in the original metadata and has downloadLocation declared
                        "name": "package3",
                        "versionInfo": "3.0",
                        "licenseDeclared": "APACHE-2.0",
                        "downloadLocation": "test_purl_2",
                    },
                ]
            }
        },
    )
    gh_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    purl_parser_object = mocker.Mock()
    mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.PurlParser",
        return_value=purl_parser_object,
    )
    purl_parser_object.get_github_owner_and_repo.side_effect = [
        ("owner", "repo"),
        (None, None),
    ]

    strategy = GitHubSbomMetadataCollectionStrategy(github_client=gh_mock)

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="test_purl",
            license=None,
            copyright=None,
        ),
        Metadata(  # this package is not in the sbom shouldn't be lost
            name="package2",
            version=None,
            origin=None,
            license=None,
            copyright=None,
        ),
    ]

    expected_metadata = [
        Metadata(
            name="package1",
            version="2.0",
            origin="test_purl",
            license="APACHE-2.0",
            copyright=[],
        ),
        Metadata(
            name="package2",
            version=None,
            origin=None,
            license=None,
            copyright=None,
        ),
        Metadata(
            name="package3",
            version="3.0",
            origin="test_purl_2",
            license="APACHE-2.0",
            copyright=[],
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)
    assert sorted(updated_metadata, key=str) == sorted(expected_metadata, key=str)

    purl_parser_object.get_github_owner_and_repo.assert_has_calls(
        [
            call("test_purl"),
            call(None),
        ]
    )

    sbom_mock.get.assert_called_once_with()
