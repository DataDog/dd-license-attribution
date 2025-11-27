# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from typing import Any
from unittest.mock import Mock

import pytest_mock
from agithub.GitHub import GitHub

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.cleanup_copyright_metadata_strategy import (
    CleanupCopyrightMetadataStrategy,
)
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


def create_mock_spdx_package(
    name: str | None = None,
    spdx_id: str | None = None,
    version: str | None = None,
    download_location: str | None = None,
    license_declared: str | None = None,
    license_concluded: str | None = None,
    copyright_text: str | None = None,
) -> Mock:
    """Create a mock SPDX Package object.

    Note: spdx-tools 0.8.2 still uses the same attribute names as 0.7:
    version, conc_lics (not license_concluded), cr_text (not copyright_text).
    """
    package = Mock()
    package.name = name
    package.spdx_id = spdx_id
    package.version = version
    package.download_location = download_location
    package.license_declared = license_declared
    package.conc_lics = license_concluded  # spdx uses conc_lics
    package.cr_text = copyright_text  # spdx uses cr_text
    return package


def create_mock_spdx_document(packages: list[Any]) -> Mock:
    """Create a mock SPDX Document object."""
    document = Mock()
    document.packages = packages
    return document


def test_github_sbom_collection_strategy_returns_same_metadata_if_not_a_github_repo(
    mocker: pytest_mock.MockFixture,
) -> None:
    github_client_mock = mocker.Mock(spec_set=GitHub)
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "not_a_github_purl",
        None,
    )

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
        source_code_manager=source_code_manager_mock,
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

    source_code_manager_mock.get_canonical_urls.assert_called_once_with(
        "not_a_github_purl"
    )


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
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
    )

    # Mock JSONParser - it won't be called since API call fails
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.JSONParser"
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        source_code_manager=source_code_manager_mock,
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

    # With the new logging, errors are caught and packages are skipped rather than raising
    # The metadata should be updated with canonical URL but no SBOM data
    updated_metadata = strategy.augment_metadata(initial_metadata)

    # Package should be returned with updated origin but no additional data
    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_raise_special_exception_if_error_calling_github_sbom_api_is_404(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (404, "Not Found")
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
    )

    # Mock JSONParser - it won't be called since API call fails
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.JSONParser"
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        source_code_manager=source_code_manager_mock,
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

    updated_metadata = strategy.augment_metadata(initial_metadata)

    # Package should be returned with updated origin but no additional data
    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_raise_special_exception_if_error_calling_github_sbom_api_is_401(
    mocker: pytest_mock.MockFixture,
) -> None:
    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (401, "Unauthorized")
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
    )

    # Mock JSONParser - it won't be called since API call fails
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.JSONParser"
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        source_code_manager=source_code_manager_mock,
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

    updated_metadata = strategy.augment_metadata(initial_metadata)

    # Package should be returned with updated origin but no additional data
    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    sbom_mock.get.assert_called_once_with()


def test_github_sbom_collection_strategy_with_no_new_info_skips_actions_and_returns_original_info(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Create SPDX document with a GitHub Actions package (should be skipped)
    packages = [
        create_mock_spdx_package(
            spdx_id="SPDXRef-githubactions-somthing-that-acts"
        ),  # this should be skipped
        # No other packages in SBOM for this test
    ]
    spdx_document = create_mock_spdx_document(packages)

    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {"sbom": {}},  # Actual content doesn't matter, parse_file will be mocked
    )
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
    )

    # Mock JSONParser to return our SPDX document
    parser_instance_mock = mocker.Mock()
    parser_instance_mock.document = spdx_document
    json_parser_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.JSONParser",
        return_value=parser_instance_mock,
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        source_code_manager=source_code_manager_mock,
        project_scope=ProjectScope.ALL,
    )

    initial_metadata = [
        Metadata(
            name="github.com/test_owner/old_name",  # A github.com format name
            version="1.0",
            origin="test_purl",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        )
    ]

    expected_metadata = [
        Metadata(
            name="github.com/test_owner/test_repo",  # Updated to canonical name
            version="1.0",
            origin="https://github.com/test_owner/test_repo",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=["Datadog Inc."],
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)
    assert updated_metadata == expected_metadata

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    sbom_mock.get.assert_called_once_with()
    json_parser_mock.assert_called_once()  # Verify parser was instantiated
    json_parser_mock.assert_called_once()  # Verify parser was instantiated
    parser_instance_mock.parse.assert_called_once()  # Verify parse was called  # Verify parse was called


def test_github_sbom_collection_strategy_with_new_info_is_not_lost_in_repeated_package(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Create SPDX document with multiple packages
    packages = [
        create_mock_spdx_package(
            spdx_id="SPDXRef-githubactions-somthing-that-acts"
        ),  # this should be skipped
        create_mock_spdx_package(  # this is the package from the original metadata with new information
            name="package1",
            version="2.0",
            license_declared="APACHE-2.0",
            download_location="test_purl",
        ),
        create_mock_spdx_package(  # this was already in the previous line, we keep the new information and not override with this.
            name="package1"
        ),
        create_mock_spdx_package(  # this is a package that is not in the original metadata and has downloadLocation declared
            name="package3",
            version="3.0",
            license_declared="APACHE-2.0",
            download_location="test_purl_2",
        ),
    ]
    spdx_document = create_mock_spdx_document(packages)

    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {"sbom": {}},  # Actual content doesn't matter, parse_file will be mocked
    )
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))
    source_code_manager_mock = mocker.Mock()
    # First call is for package1 with origin="test_purl"
    # Second call would be for package2 with origin=None but it returns None API URL so parse_git_url won't be called
    source_code_manager_mock.get_canonical_urls.side_effect = [
        (
            "https://github.com/test_owner/test_repo",
            "https://api.github.com/repos/test_owner/test_repo",
        ),
        (None, None),
    ]

    giturlparse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    # Mock JSONParser to return our SPDX document
    parser_instance_mock = mocker.Mock()
    parser_instance_mock.document = spdx_document
    json_parser_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.JSONParser",
        return_value=parser_instance_mock,
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        source_code_manager=source_code_manager_mock,
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
            origin="https://github.com/test_owner/test_repo",
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

    # parse_git_url is only called once for the first package with a valid GitHub URL
    giturlparse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")

    sbom_mock.get.assert_called_once_with()
    json_parser_mock.assert_called_once()  # Verify parser was instantiated
    parser_instance_mock.parse.assert_called_once()  # Verify parse was called


def test_strategy_does_not_add_dependencies_with_transitive_dependencies_is_false(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Create SPDX document with multiple packages
    packages = [
        create_mock_spdx_package(
            name="package1",
            version="2.0",
            license_declared="APACHE-2.0",
            download_location="test_purl",
        ),
        create_mock_spdx_package(
            name="package2",
            version="3.0",
            license_declared="APACHE-2.0",
            download_location="test_purl_2",
        ),
    ]
    spdx_document = create_mock_spdx_document(packages)

    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {"sbom": {}},  # Actual content doesn't matter, parse_file will be mocked
    )
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True,
            platform="github",
            owner="test_owner",
            repo="test_repo",
        ),
    )

    # Mock JSONParser to return our SPDX document
    parser_instance_mock = mocker.Mock()
    parser_instance_mock.document = spdx_document
    json_parser_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.JSONParser",
        return_value=parser_instance_mock,
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        source_code_manager=source_code_manager_mock,
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
            origin="https://github.com/test_owner/test_repo",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        )
    ]

    assert updated_metadata == expected_metadata

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    sbom_mock.get.assert_called_once_with()
    json_parser_mock.assert_called_once()  # Verify parser was instantiated
    parser_instance_mock.parse.assert_called_once()  # Verify parse was called


def test_strategy_does_not_keep_root_when_with_root_project_is_false(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Create SPDX document with root project and a dependency
    packages = [
        create_mock_spdx_package(
            name="com.github.test_owner/test_repo",
            version="2.0",
            license_declared="APACHE-2.0",
            download_location="test_purl",
        ),
        create_mock_spdx_package(
            name="package2",
            version="3.0",
            license_declared="APACHE-2.0",
            download_location="test_purl_2",
        ),
    ]
    spdx_document = create_mock_spdx_document(packages)

    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {"sbom": {}},  # Actual content doesn't matter, parse_file will be mocked
    )
    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    github_parse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    # Mock JSONParser to return our SPDX document
    parser_instance_mock = mocker.Mock()
    parser_instance_mock.document = spdx_document
    json_parser_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.JSONParser",
        return_value=parser_instance_mock,
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        source_code_manager=source_code_manager_mock,
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

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    sbom_mock.get.assert_called_once_with()
    json_parser_mock.assert_called_once()  # Verify parser was instantiated
    parser_instance_mock.parse.assert_called_once()  # Verify parse was called


def test_github_sbom_collection_strategy_handles_company_names_in_copyright(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Create SPDX document with copyright text
    packages = [
        create_mock_spdx_package(
            name="test-package",
            copyright_text="Company A, Copyright 2024 Company B, Inc. and its affiliates, Company C, llc, Company Datadog",
        )
    ]
    spdx_document = create_mock_spdx_document(packages)

    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {"sbom": {}},  # Actual content doesn't matter, parse_file will be mocked
    )
    mock_client = mocker.Mock()
    mock_client.repos = {
        "test-owner": {"test-repo": {"dependency-graph": SbomMockWrapper(sbom_mock)}}
    }
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test-owner/test-repo",
        "https://api.github.com/repos/test-owner/test-repo",
    )

    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test-owner", "test-repo"),
    )

    # Mock JSONParser to return our SPDX document
    parser_instance_mock = mocker.Mock()
    parser_instance_mock.document = spdx_document
    json_parser_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.JSONParser",
        return_value=parser_instance_mock,
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=mock_client,
        source_code_manager=source_code_manager_mock,
        project_scope=ProjectScope.ALL,
    )
    cleanup_copyright_metadata_strategy = CleanupCopyrightMetadataStrategy()

    initial_metadata = [
        Metadata(
            name="test-package",
            version=None,
            origin="https://github.com/test-owner/test-repo",
            local_src_path=None,
            license=[],
            copyright=[],
        )
    ]
    updated_metadata = strategy.augment_metadata(initial_metadata)
    cleaned_updated_metadata = cleanup_copyright_metadata_strategy.augment_metadata(
        updated_metadata
    )

    assert cleaned_updated_metadata[0].copyright == [
        "Company A",
        "Company B, Inc. and its affiliates",
        "Company C, llc",
        "Company Datadog",
    ]
    json_parser_mock.assert_called_once()  # Verify parser was instantiated
    parser_instance_mock.parse.assert_called_once()  # Verify parse was called


def test_github_sbom_collection_strategy_uses_name_as_origin_if_download_location_is_empty_or_noassertion(
    mocker: pytest_mock.MockFixture,
) -> None:
    # Create SPDX document with packages having different download locations
    packages = [
        create_mock_spdx_package(
            name="package0",
            version="4.0",
            license_declared="MIT",
            copyright_text="Copyright 1",
            download_location="test_purl",
        ),
        create_mock_spdx_package(
            name="github.com/package1",
            version="2.0",
            license_concluded="MIT",
            copyright_text="Copyright 2",
            download_location="",
        ),
        create_mock_spdx_package(
            name="github.com/package2",
            version="3.0",
            license_concluded="MIT",
            copyright_text="Copyright 3",
            download_location="NOASSERTION",
        ),
    ]
    spdx_document = create_mock_spdx_document(packages)

    sbom_mock = mocker.Mock()
    sbom_mock.get.return_value = (
        200,
        {"sbom": {}},  # Actual content doesn't matter, parse_file will be mocked
    )

    github_client_mock = GitHubClientMock(sbom_input=SbomMockWrapper(sbom_mock))
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )

    giturlparse_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    # Mock JSONParser to return our SPDX document
    parser_instance_mock = mocker.Mock()
    parser_instance_mock.document = spdx_document
    json_parser_mock = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy.JSONParser",
        return_value=parser_instance_mock,
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=github_client_mock,
        source_code_manager=source_code_manager_mock,
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
            origin="https://github.com/test_owner/test_repo",
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

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    giturlparse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    sbom_mock.get.assert_called_once_with()
    json_parser_mock.assert_called_once()  # Verify parser was instantiated
    parser_instance_mock.parse.assert_called_once()  # Verify parse was called
