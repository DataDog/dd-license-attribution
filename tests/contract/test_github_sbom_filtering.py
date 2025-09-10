# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from unittest.mock import Mock, patch

import pytest
import pytest_mock
from agithub.GitHub import GitHub


class SbomMockWrapper:
    def __init__(self, sbom_input: str) -> None:
        self.sbom = sbom_input


class GitHubClientMock:
    def __init__(self, sbom_input: SbomMockWrapper) -> None:
        # this needs to be accessed: self.repos[owner][repo].sbom and return sbom_input
        self.repos = {"test_owner": {"test_repo": {"dependency-graph": sbom_input}}}

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy import (
    GitHubSbomMetadataCollectionStrategy,
)


def test_full_package_inclusion_integration(mocker: pytest_mock.MockFixture) -> None:
    """Integration test for the complete package inclusion process"""
    # Set up test data
    packages = [
        {"name": "root", "SPDXID": "SPDXRef-1"},
        {"name": "direct-dep", "SPDXID": "SPDXRef-2"},
        {"name": "transitive-dep", "SPDXID": "SPDXRef-3"},
        {"name": "unrelated-dep", "SPDXID": "SPDXRef-4"}
    ]

    relationships = [
        {
            "relationshipType": "DEPENDS_ON",
            "spdxElementId": "SPDXRef-2",  # direct-dep is depended on by root
            "relatedSpdxElement": "SPDXRef-1"
        },
        {
            "relationshipType": "DEPENDS_ON",
            "spdxElementId": "SPDXRef-3",  # transitive-dep is depended on by direct-dep
            "relatedSpdxElement": "SPDXRef-2"
        }
    ]

    # Mock the SBOM API response
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {
            "sbom": {
                "packages": packages,
                "relationships": relationships
            }
        }
    )

    # Set up the GitHub client mock using the helper classes
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))
    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        project_scope=ProjectScope.ALL,
    )
    

    # Mock the filter method to use our filenames
    original_filter = strategy._GitHubSbomMetadataCollectionStrategy__filter_sbom_to_include_only_dependencies_from_chosen_files
    def filter_with_our_files(filenames_to_include, packages_in_sbom, owner, repo, relationships):
        # Override the empty list with our desired files
        result = original_filter(["pyproject.toml"], packages_in_sbom, owner, repo, relationships)
        return result
    
    mocker.patch.object(
        strategy,
        '_GitHubSbomMetadataCollectionStrategy__filter_sbom_to_include_only_dependencies_from_chosen_files',
        side_effect=filter_with_our_files
    )

    # Mock the GraphQL response for file dependencies
    mocker.patch.object(
        strategy,
        '_GitHubSbomMetadataCollectionStrategy__get_info_from_graphql',
        return_value={"pyproject.toml": {"direct-dep"}}
    )

    # Mock the git URL parsing
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=Mock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
            github=True
        )
    )

    # Test the full pipeline
    initial_metadata = [
        Metadata(
            name="root",
            version=None,
            origin="https://github.com/test_owner/test_repo",
            local_src_path=None,
            license=[],
            copyright=[],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    # Verify results
    # We expect:
    # 1. direct-dep because it's in pyproject.toml
    # 2. root because it depends on direct-dep
    # We don't expect:
    # 1. transitive-dep because we only include upward dependencies
    # 2. unrelated-dep because it's not connected to our included deps
    assert len(updated_metadata) == 2
    package_names = {pkg.name for pkg in updated_metadata}
    assert package_names == {"root", "direct-dep"}

    # Verify the SBOM API was called
    sbom_mock.get.assert_called_once_with()