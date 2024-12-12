from unittest.mock import call
import pytest
from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy import (
    GitHubSbomMetadataCollectionStrategy,
    ProjectScope,
)
from agithub.GitHub import GitHub
import pytest_mock


class GitUrlParseMock:
    def __init__(
        self, valid: bool, platform: str, owner: str | None, repo: str | None
    ) -> None:
        self.valid = valid
        self.platform = platform
        self.owner = owner
        self.repo = repo


def test_github_sbom_collection_strategy_returns_same_metadata_if_not_a_github_repo(
    mocker: pytest_mock.MockFixture,
) -> None:
    github_client_mock = mocker.Mock(spec_set=GitHub)

    class GitUrlParseMock:
        def __init__(self) -> None:
            self.valid = True
            self.platform = "gitlab"

    github_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(),
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )

    initial_metadata = [
        Metadata(
            name="",
            version="",
            origin="not_a_github_purl",
            license=[],
            copyright=[],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)
    assert updated_metadata == initial_metadata

    github_parse_mock.assert_called_once_with("not_a_github_purl")


class SbomMockWrapper:
    def __init__(self, sbom_input: str) -> None:
        self.sbom = sbom_input


class GitHubClientMock:
    def __init__(self, sbom_input: SbomMockWrapper) -> None:
        # this needs to be accessed: self.repos[owner][repo].sbom and return sbom_input
        self.repos = {"test_owner": {"test_repo": {"dependency-graph": sbom_input}}}


def test_github_sbom_collection_strategy_raise_exception_if_error_calling_github_sbom_api(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (404, "Not Found")
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    class GitUrlParseMock:
        def __init__(self) -> None:
            self.valid = True
            self.platform = "github"
            self.owner = "test_owner"
            self.repo = "test_repo"

    github_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(),
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )

    initial_metadata = [
        Metadata(
            name="",
            version="",
            origin="test_purl",
            license=[],
            copyright=[],
        )
    ]

    with pytest.raises(ValueError, match="Failed to get SBOM for test_owner/test_repo"):
        strategy.augment_metadata(initial_metadata)

    github_parse_mock.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_with_no_new_info_skips_actions_and_returns_original_info(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {
            "sbom": {
                "packages": [
                    {
                        "SPDXID": "SPDXRef-githubactions-somthing-that-acts"
                    },  # this should be skipped
                    {
                        "name": "package1"
                    },  # this was already in the metadata, we keep the old information since there is none new
                ]
            }
        },
    )
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    class GitUrlParseMock:
        def __init__(self) -> None:
            self.valid = True
            self.platform = "github"
            self.owner = "test_owner"
            self.repo = "test_repo"

    github_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(),
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version="1.0",
            origin="test_purl",
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)
    assert updated_metadata == initial_metadata

    github_parse_mock.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_with_new_info_is_not_lost_in_repeated_package(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {
            "sbom": {
                "packages": [
                    {
                        "SPDXID": "SPDXRef-githubactions-somthing-that-acts"
                    },  # this should be skipped
                    {  # this is the package from the original metadata with new information
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
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    giturlparse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        side_effect=[
            GitUrlParseMock(True, "github", "test_owner", "test_repo"),
            GitUrlParseMock(True, "gitlab", None, None),
        ],
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="test_purl",
            license=[],
            copyright=[],
        ),
        Metadata(  # this package is not in the sbom shouldn't be lost
            name="package2",
            version=None,
            origin=None,
            license=[],
            copyright=[],
        ),
    ]

    expected_metadata = [
        Metadata(
            name="package1",
            version="2.0",
            origin="test_purl",
            license=["APACHE-2.0"],
            copyright=[],
        ),
        Metadata(
            name="package2",
            version=None,
            origin=None,
            license=[],
            copyright=[],
        ),
        Metadata(
            name="package3",
            version="3.0",
            origin="test_purl_2",
            license=["APACHE-2.0"],
            copyright=[],
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)
    assert sorted(updated_metadata, key=str) == sorted(expected_metadata, key=str)

    giturlparse_mock.assert_has_calls(
        [
            call("test_purl"),
            call(None),
        ]
    )

    sbom_mock.get.assert_called_once_with()


def test_strategy_does_not_add_dependencies_with_transitive_dependencies_is_false(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {
            "sbom": {
                "packages": [
                    {
                        "name": "package1",
                        "versionInfo": "2.0",
                        "licenseDeclared": "APACHE-2.0",
                        "downloadLocation": "test_purl",
                    },
                    {
                        "name": "package2",
                        "versionInfo": "3.0",
                        "licenseDeclared": "APACHE-2.0",
                        "downloadLocation": "test_purl_2",
                    },
                ]
            }
        },
    )
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    class GitUrlParseMock:
        def __init__(self) -> None:
            self.valid = True
            self.platform = "github"
            self.owner = "test_owner"
            self.repo = "test_repo"

    github_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(),
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ONLY_ROOT_PROJECT,
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="test_purl",
            license=[],
            copyright=[],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="package1",
            version="2.0",
            origin="test_purl",
            license=["APACHE-2.0"],
            copyright=[],
        )
    ]

    assert updated_metadata == expected_metadata

    github_parse_mock.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()


def test_strategy_does_not_keep_root_when_with_root_project_is_false(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {
            "sbom": {
                "packages": [
                    {
                        "name": "package1",
                        "versionInfo": "2.0",
                        "licenseDeclared": "APACHE-2.0",
                        "downloadLocation": "test_purl",
                    },
                    {
                        "name": "package2",
                        "versionInfo": "3.0",
                        "licenseDeclared": "APACHE-2.0",
                        "downloadLocation": "test_purl_2",
                    },
                ]
            }
        },
    )
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    github_parse_mock = mocker.patch(
        "ospo_tools.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES,
    )

    initial_metadata = [
        Metadata(
            name="package1",
            version=None,
            origin="test_purl",
            license=[],
            copyright=[],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    expected_metadata = [
        Metadata(
            name="package2",
            version="3.0",
            origin="test_purl_2",
            license=["APACHE-2.0"],
            copyright=[],
        )
    ]

    assert updated_metadata == expected_metadata

    github_parse_mock.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()
