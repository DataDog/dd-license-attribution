# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

from unittest.mock import Mock, patch

from dd_license_attribution.artifact_management.source_code_manager import (
    SourceCodeManager,
)

# Tests for get_repository_info function


@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_caches_results(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
) -> None:
    """Test that get_repository_info caches results on first call and returns cached data on subsequent calls."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock GitHub API client
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        200,
        {
            "html_url": "https://github.com/DataDog/dd-license-attribution",
            "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
            "license": {"spdx_id": "Apache-2.0"},
            "owner": {"login": "DataDog"},
        },
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # Call get_repository_info twice with the same owner/repo
    status1, result1 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    status2, result2 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )

    # Verify results are the same
    assert status1 == status2 == 200
    assert result1 == result2
    assert result1 is not None
    assert result1["html_url"] == "https://github.com/DataDog/dd-license-attribution"
    assert result1["license"]["spdx_id"] == "Apache-2.0"

    # Verify GitHub API was only called once (caching works)
    assert repo_mock.get.call_count == 1


@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_handles_301_redirects(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
) -> None:
    """Test that get_repository_info handles 301 redirects correctly and caches the final result."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock GitHub API client
    github_client_mock = Mock()

    # After following redirect, return 200
    final_repo_mock = Mock()
    final_repo_mock.get.return_value = (
        200,
        {
            "html_url": "https://github.com/DataDog/dd-license-attribution",
            "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
            "license": {"spdx_id": "Apache-2.0"},
            "owner": {"login": "DataDog"},
        },
    )

    # First call returns 301 redirect
    first_repo_mock = Mock()
    first_repo_mock.get.return_value = (
        301,
        {"url": "https://api.github.com/repos/DataDog/dd-license-attribution"},
    )

    # Setup mock chain for initial call
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=first_repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    # Setup mock for following the redirect path repos/DataDog/dd-license-attribution
    # After splitting the path, we'll access client["repos"]["DataDog"]["dd-license-attribution"]
    def mock_getitem(key: str) -> Mock:
        if key == "repos":
            datadog_mock = Mock()
            datadog_mock.__getitem__ = Mock(
                side_effect=lambda k: (
                    final_repo_mock if k == "dd-license-attribution" else Mock()
                )
            )
            redirect_repos_mock = Mock()
            redirect_repos_mock.__getitem__ = Mock(
                side_effect=lambda k: datadog_mock if k == "DataDog" else Mock()
            )
            return redirect_repos_mock
        return Mock()

    github_client_mock.__getitem__ = Mock(side_effect=mock_getitem)

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # Call get_repository_info
    status, result = source_code_manager.get_repository_info("DataDog", "ospo-tools")

    # Verify redirect was followed and final result cached
    assert status == 200
    assert result is not None
    assert result["html_url"] == "https://github.com/DataDog/dd-license-attribution"

    # Call again to verify caching
    status2, result2 = source_code_manager.get_repository_info("DataDog", "ospo-tools")
    assert status2 == 200
    assert result2 == result

    # Verify API calls happened only once (caching works after redirect)
    assert first_repo_mock.get.call_count == 1
    assert final_repo_mock.get.call_count == 1


@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_caches_error_responses(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
) -> None:
    """Test that get_repository_info caches error responses (404, etc.) without making new API calls."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock GitHub API client to return 404
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (404, None)
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # Call get_repository_info twice with a non-existent repo
    status1, result1 = source_code_manager.get_repository_info(
        "NonExistent", "NonExistentRepo"
    )
    status2, result2 = source_code_manager.get_repository_info(
        "NonExistent", "NonExistentRepo"
    )

    # Verify results are the same error
    assert status1 == status2 == 404
    assert result1 is None
    assert result2 is None

    # Verify GitHub API was only called once (error is cached)
    assert repo_mock.get.call_count == 1


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_canonical_urls_then_get_repository_info_reuses_cache(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
) -> None:
    """Test that calling get_canonical_urls first and then get_repository_info reuses the cache (one API call total)."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    git_url_parse_mock.return_value.valid = True
    git_url_parse_mock.return_value.github = True
    git_url_parse_mock.return_value.owner = "DataDog"
    git_url_parse_mock.return_value.repo = "dd-license-attribution"
    git_url_parse_mock.return_value.protocol = "https"
    git_url_parse_mock.return_value.host = "github.com"

    # Mock GitHub API client
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        200,
        {
            "html_url": "https://github.com/DataDog/dd-license-attribution",
            "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
            "license": {"spdx_id": "Apache-2.0"},
            "owner": {"login": "DataDog"},
        },
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # First call get_canonical_urls
    canonical_url, api_url = source_code_manager.get_canonical_urls(
        "https://github.com/DataDog/dd-license-attribution"
    )
    assert canonical_url == "https://github.com/DataDog/dd-license-attribution"

    # Then call get_repository_info (should use cache)
    status, result = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status == 200
    assert result is not None
    assert result["license"]["spdx_id"] == "Apache-2.0"

    # Verify GitHub API was only called once total
    assert repo_mock.get.call_count == 1


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_then_get_canonical_urls_reuses_cache(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
) -> None:
    """Test that calling get_repository_info first and then get_canonical_urls reuses the cache (one API call total)."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    git_url_parse_mock.return_value.valid = True
    git_url_parse_mock.return_value.github = True
    git_url_parse_mock.return_value.owner = "DataDog"
    git_url_parse_mock.return_value.repo = "dd-license-attribution"
    git_url_parse_mock.return_value.protocol = "https"
    git_url_parse_mock.return_value.host = "github.com"

    # Mock GitHub API client
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        200,
        {
            "html_url": "https://github.com/DataDog/dd-license-attribution",
            "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
            "license": {"spdx_id": "Apache-2.0"},
            "owner": {"login": "DataDog"},
        },
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # First call get_repository_info
    status, result = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status == 200
    assert result is not None
    assert result["license"]["spdx_id"] == "Apache-2.0"

    # Then call get_canonical_urls (should use cache)
    canonical_url, api_url = source_code_manager.get_canonical_urls(
        "https://github.com/DataDog/dd-license-attribution"
    )
    assert canonical_url == "https://github.com/DataDog/dd-license-attribution"

    # Verify GitHub API was only called once total
    assert repo_mock.get.call_count == 1
