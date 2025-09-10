# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from unittest.mock import call, Mock

import pytest
import pytest_mock
from agithub.GitHub import GitHub

from dd_license_attribution.artifact_management.source_code_manager import (
    NonAccessibleRepository,
    UnauthorizedRepository,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy import (
    GitHubSbomMetadataCollectionStrategy,
    ProjectScope,
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


def test_github_sbom_collection_strategy_returns_same_metadata_if_not_a_github_repo(
    mocker: pytest_mock.MockFixture,
) -> None:
    github_client_mock = mocker.Mock(spec_set=GitHub)

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="not_github",
            owner=None,
            repo=None,
        ),
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
            local_src_path="",
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
    sbom_mock.get.return_value = (500, "Not Found")
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
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
            local_src_path="",
            license=[],
            copyright=[],
        )
    ]

    with pytest.raises(ValueError, match="Failed to get SBOM for test_owner/test_repo"):
        strategy.augment_metadata(initial_metadata)

    github_parse_mock.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_raise_special_exception_if_error_calling_github_sbom_api_is_404(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (404, "Not Found")
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
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
            local_src_path="",
            license=[],
            copyright=[],
        )
    ]

    with pytest.raises(NonAccessibleRepository, match=".*test_owner/test_repo.*"):
        strategy.augment_metadata(initial_metadata)

    github_parse_mock.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_raise_special_exception_if_error_calling_github_sbom_api_is_401(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (401, "Unauthorized")
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
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
            local_src_path="",
            license=[],
            copyright=[],
        )
    ]

    with pytest.raises(UnauthorizedRepository, match=".*test_owner/test_repo.*"):
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

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
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
            local_src_path=None,
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
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
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
            local_src_path=None,
            license=[],
            copyright=[],
        ),
        Metadata(  # this package is not in the sbom shouldn't be lost
            name="package2",
            version=None,
            origin=None,
            local_src_path=None,
            license=[],
            copyright=[],
        ),
    ]

    expected_metadata = [
        Metadata(
            name="package1",
            version="2.0",
            origin="test_purl",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        ),
        Metadata(
            name="package2",
            version=None,
            origin=None,
            local_src_path=None,
            license=[],
            copyright=[],
        ),
        Metadata(
            name="package3",
            version="3.0",
            origin="test_purl_2",
            local_src_path=None,
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

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
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
            local_src_path=None,
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
            local_src_path=None,
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
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
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
            local_src_path=None,
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
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        )
    ]

    assert updated_metadata == expected_metadata

    github_parse_mock.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_uses_name_as_origin_if_download_location_is_empty_or_noassertion(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_data = (
        200,
        {
            "sbom": {
                "packages": [
                    {
                        "name": "package0",
                        "versionInfo": "4.0",
                        "licenseDeclared": "MIT",
                        "copyrightText": "Copyright 1",
                        "downloadLocation": "test_purl",
                    },
                    {
                        "name": "github.com/package1",
                        "versionInfo": "2.0",
                        "licenseConcluded": "MIT",
                        "copyrightText": "Copyright 2",
                        "downloadLocation": "",
                    },
                    {
                        "name": "github.com/package2",
                        "versionInfo": "3.0",
                        "licenseConcluded": "MIT",
                        "copyrightText": "Copyright 3",
                        "downloadLocation": "NOASSERTION",
                    },
                ]
            }
        },
    )
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = sbom_data

    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))

    giturlparse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )

    initial_metadata = [
        Metadata(
            name="package0",
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
            name="package0",
            version="4.0",
            origin="test_purl",
            local_src_path=None,
            license=["MIT"],
            copyright=["Copyright 1"],
        ),
        Metadata(
            name="github.com/package1",
            version="2.0",
            origin="https://github.com/package1",
            local_src_path=None,
            license=["MIT"],
            copyright=["Copyright 2"],
        ),
        Metadata(
            name="github.com/package2",
            version="3.0",
            origin="https://github.com/package2",
            local_src_path=None,
            license=["MIT"],
            copyright=["Copyright 3"],
        ),
    ]

    assert updated_metadata == expected_metadata

    giturlparse_mock.assert_called_once_with("test_purl")
    sbom_mock.get.assert_called_once_with()


def test_filter_sbom_empty_inputs() -> None:
    """Test filtering with empty inputs"""
    github_client_mock = Mock(spec_set=GitHub)
    
    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )
    result = strategy._GitHubSbomMetadataCollectionStrategy__filter_sbom_to_include_only_dependencies_from_chosen_files(
        [], [], "owner", "repo", []
    )
    assert result == []


def test_filter_sbom_no_files_to_include() -> None:
    """Test when no files are specified to include - should return all packages"""
    github_client_mock = Mock(spec_set=GitHub)
    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )
    packages = [{"name": "pkg1", "SPDXID": "SPDXRef-1"}]
    result = strategy._GitHubSbomMetadataCollectionStrategy__filter_sbom_to_include_only_dependencies_from_chosen_files(
        [], packages, "owner", "repo", []
    )
    assert result == packages  # Should return all packages when no files specified


def test_filter_sbom_with_specific_files(mocker: pytest_mock.MockFixture) -> None:
    """Test filtering to include only dependencies from specific files"""
    github_client_mock = Mock(spec_set=GitHub)
    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )
    packages = [
        {"name": "pkg1", "SPDXID": "SPDXRef-1"},
        {"name": "pkg2", "SPDXID": "SPDXRef-2"}
    ]
    
    mocker.patch.object(
        strategy,
        '_GitHubSbomMetadataCollectionStrategy__get_list_of_packages_mapped_to_filename',
        return_value={"pyproject.toml": ["pkg1"]}
    )
    
    result = strategy._GitHubSbomMetadataCollectionStrategy__filter_sbom_to_include_only_dependencies_from_chosen_files(
        ["pyproject.toml"], packages, "owner", "repo", []
    )
    
    assert len(result) == 1
    assert result[0]["name"] == "pkg1"


def test_handle_transitive_inclusion() -> None:
    """Test handling of transitive inclusion"""
    github_client_mock = Mock(spec_set=GitHub)
    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )
    packages = [
        {"name": "root", "SPDXID": "SPDXRef-1"},
        {"name": "dep1", "SPDXID": "SPDXRef-2"},
        {"name": "dep2", "SPDXID": "SPDXRef-3"}
    ]
    # Note: relationships show what depends on each package
    relationships = [
        {
            "relationshipType": "DEPENDS_ON",
            "spdxElementId": "SPDXRef-2",  # dep1 is depended on by root
            "relatedSpdxElement": "SPDXRef-1"
        },
        {
            "relationshipType": "DEPENDS_ON",
            "spdxElementId": "SPDXRef-3",  # dep2 is depended on by dep1
            "relatedSpdxElement": "SPDXRef-2"
        }
    ]
    deps_to_include = ["dep2"]
    
    result = strategy._GitHubSbomMetadataCollectionStrategy__handle_transitive_inclusion(
        packages, deps_to_include, relationships
    )
    
    # Should include dep2 and everything that depends on it (dep1 and root)
    assert len(result) == 3
    assert {pkg["name"] for pkg in result} == {"root", "dep1", "dep2"}


def test_handle_transitive_inclusion_with_cycles() -> None:
    """Test handling of cyclic dependencies in inclusion mode"""
    github_client_mock = Mock(spec_set=GitHub)
    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )
    packages = [
        {"name": "pkg1", "SPDXID": "SPDXRef-1"},
        {"name": "pkg2", "SPDXID": "SPDXRef-2"}
    ]
    relationships = [
        {
            "relationshipType": "DEPENDS_ON",
            "spdxElementId": "SPDXRef-1",  # pkg1 is depended on by pkg2
            "relatedSpdxElement": "SPDXRef-2"
        },
        {
            "relationshipType": "DEPENDS_ON",
            "spdxElementId": "SPDXRef-2",  # pkg2 is depended on by pkg1
            "relatedSpdxElement": "SPDXRef-1"
        }
    ]
    deps_to_include = ["pkg1"]
    
    result = strategy._GitHubSbomMetadataCollectionStrategy__handle_transitive_inclusion(
        packages, deps_to_include, relationships
    )
    
    # Should handle the cycle and include both packages since they depend on each other
    assert len(result) == 2
    assert {pkg["name"] for pkg in result} == {"pkg1", "pkg2"}


def test_get_packages_mapped_to_filename(mocker: pytest_mock.MockFixture) -> None:
    """Test mapping of packages to filenames"""
    github_client_mock = Mock(spec_set=GitHub)
    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )
    
    mocker.patch.object(
        strategy,
        '_GitHubSbomMetadataCollectionStrategy__get_info_from_graphql',
        return_value={
            "pyproject.toml": {"pkg1", "pkg2"},
            "requirements.txt": {"pkg3", "pkg4"}
        }
    )
    
    result = strategy._GitHubSbomMetadataCollectionStrategy__get_list_of_packages_mapped_to_filename(
        ["pyproject.toml"], "owner", "repo"
    )
    
    assert result == {"pyproject.toml": ["pkg1", "pkg2"]}


def test_get_info_from_graphql_pagination(mocker: pytest_mock.MockFixture) -> None:
    """Test GraphQL pagination for both manifests and dependencies"""
    github_client_mock = Mock(spec_set=GitHub)
    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )
    
    # Mock environment variable
    mocker.patch.dict('os.environ', {'GITHUB_TOKEN': 'fake-token'})
    
    mock_post = mocker.patch('requests.post')
    # Mock first manifest page
    mock_post.side_effect = [
        Mock(
            status_code=200,
            json=lambda: {
                "data": {
                    "repository": {
                        "dependencyGraphManifests": {
                            "pageInfo": {"hasNextPage": True, "endCursor": "cursor1"},
                            "nodes": [{
                                "id": "manifest1",
                                "filename": "pyproject.toml",
                                "dependencies": {
                                    "pageInfo": {"hasNextPage": True, "endCursor": "dep1"},
                                    "nodes": [{"packageName": "pkg1"}]
                                }
                            }]
                        }
                    }
                }
            }
        ),
        # Mock dependency pagination
        Mock(
            status_code=200,
            json=lambda: {
                "data": {
                    "node": {
                        "dependencies": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": [{"packageName": "pkg2"}]
                        }
                    }
                }
            }
        ),
        # Mock second manifest page
        Mock(
            status_code=200,
            json=lambda: {
                "data": {
                    "repository": {
                        "dependencyGraphManifests": {
                            "pageInfo": {"hasNextPage": False, "endCursor": None},
                            "nodes": []
                        }
                    }
                }
            }
        )
    ]
    
    result = strategy._GitHubSbomMetadataCollectionStrategy__get_info_from_graphql(
        "owner", "repo"
    )
    
    assert result == {"pyproject.toml": {"pkg1", "pkg2"}}
    assert mock_post.call_count == 3
