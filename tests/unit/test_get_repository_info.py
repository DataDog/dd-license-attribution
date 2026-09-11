# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from unittest.mock import Mock, call, patch

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
    repo_mock.get.assert_called_once_with()
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


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
    first_repo_mock.get.assert_called_once_with()
    final_repo_mock.get.assert_called_once_with()
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


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
    repo_mock.get.assert_called_once_with()
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


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
    repo_mock.get.assert_called_once_with()
    git_url_parse_mock.assert_called_once_with(
        "https://github.com/DataDog/dd-license-attribution"
    )
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


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
    repo_mock.get.assert_called_once_with()
    git_url_parse_mock.assert_called_once_with(
        "https://github.com/DataDog/dd-license-attribution"
    )
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_retries_rate_limit_403_and_succeeds(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """Test that get_repository_info retries confirmed rate limit 403 responses with exponential backoff and succeeds."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock GitHub API client: two rate limit 403 responses, then a 200
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.side_effect = [
        (403, {"message": "API rate limit exceeded for 1.2.3.4."}),
        (403, {"message": "API rate limit exceeded for 1.2.3.4."}),
        (
            200,
            {
                "html_url": "https://github.com/DataDog/dd-license-attribution",
                "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
                "license": {"spdx_id": "Apache-2.0"},
                "owner": {"login": "DataDog"},
            },
        ),
    ]
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # Call get_repository_info - should retry and succeed on the third attempt
    status, result = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )

    assert status == 200
    assert result is not None
    assert result["html_url"] == "https://github.com/DataDog/dd-license-attribution"

    # Verify 3 API attempts and backoff delays of 2 then 4 seconds
    assert repo_mock.get.mock_calls == [call(), call(), call()]
    assert sleep_mock.mock_calls == [call(2.0), call(4.0)]

    # Verify the successful result is cached (no further API calls)
    status2, result2 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status2 == 200
    assert result2 == result
    assert repo_mock.get.mock_calls == [call(), call(), call()]
    sleep_mock.assert_has_calls([call(2.0), call(4.0)])
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_exhausts_retries_on_persistent_rate_limit(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """Test that get_repository_info exhausts retries on a persistent rate limit 403, returns the error, and does not cache it."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock GitHub API client to always return a rate limit 403
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        403,
        {"message": "You have exceeded a secondary rate limit"},
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # First call: 3 attempts (initial + 2 retries), backoff delays of 2 then 4 seconds
    status1, result1 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status1 == 403
    assert result1 is not None
    assert "rate limit" in result1["message"].lower()
    assert repo_mock.get.mock_calls == [call(), call(), call()]
    assert sleep_mock.mock_calls == [call(2.0), call(4.0)]

    # Second call: the rate limit 403 is not cached, so the API is retried again
    status2, result2 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status2 == 403
    assert result2 == result1
    assert repo_mock.get.mock_calls == [
        call(),
        call(),
        call(),
        call(),
        call(),
        call(),
    ]
    assert sleep_mock.mock_calls == [
        call(2.0),
        call(4.0),
        call(2.0),
        call(4.0),
    ]
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_does_not_retry_permanent_403(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """Test that get_repository_info does not retry permanent 403 responses (non-rate-limit) and caches them."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock GitHub API client to return a permanent 403 (access denied, not a
    # rate limit)
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        403,
        {"message": "Resource not accessible by integration"},
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # First call: no retry, single API attempt
    status1, result1 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status1 == 403
    assert result1 is not None
    assert result1["message"] == "Resource not accessible by integration"
    repo_mock.get.assert_called_once_with()
    sleep_mock.assert_not_called()

    # Second call: the permanent 403 is cached, no further API calls
    status2, result2 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status2 == 403
    assert result2 == result1
    repo_mock.get.assert_called_once_with()
    sleep_mock.assert_not_called()
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_retries_when_redirect_target_is_rate_limited(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """Test that get_repository_info retries when following a 301 redirect lands on a 403 rate limit."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Redirect target returns a rate limit 403
    final_repo_mock = Mock()
    final_repo_mock.get.return_value = (
        403,
        {"message": "API rate limit exceeded for 1.2.3.4."},
    )

    # Initial endpoint: first call returns a 301 redirect, retry returns 200
    first_repo_mock = Mock()
    first_repo_mock.get.side_effect = [
        (
            301,
            {"url": "https://api.github.com/repos/DataDog/dd-license-attribution"},
        ),
        (
            200,
            {
                "html_url": "https://github.com/DataDog/dd-license-attribution",
                "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
                "license": {"spdx_id": "Apache-2.0"},
                "owner": {"login": "DataDog"},
            },
        ),
    ]

    github_client_mock = Mock()

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

    # Setup mock chain for initial call repos/DataDog/ospo-tools
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=first_repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # First attempt follows the redirect and hits a 403, retry succeeds on the
    # original endpoint
    status, result = source_code_manager.get_repository_info("DataDog", "ospo-tools")

    assert status == 200
    assert result is not None
    assert result["html_url"] == "https://github.com/DataDog/dd-license-attribution"
    assert first_repo_mock.get.mock_calls == [call(), call()]
    final_repo_mock.get.assert_called_once_with()
    sleep_mock.assert_called_once_with(2.0)

    # Verify the result is cached (no further API calls)
    status2, result2 = source_code_manager.get_repository_info("DataDog", "ospo-tools")
    assert status2 == 200
    assert result2 == result
    assert first_repo_mock.get.mock_calls == [call(), call()]
    final_repo_mock.get.assert_called_once_with()
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_canonical_urls_does_not_cache_rate_limit_fallback(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
    git_url_parse_mock: Mock,
) -> None:
    """Test that get_canonical_urls does not cache the fallback when rate limited (403)."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    git_url_parse_mock.return_value.valid = True
    git_url_parse_mock.return_value.github = True
    git_url_parse_mock.return_value.owner = "DataDog"
    git_url_parse_mock.return_value.repo = "dd-license-attribution"
    git_url_parse_mock.return_value.protocol = "https"
    git_url_parse_mock.return_value.host = "github.com"

    # Mock GitHub API client to always return a rate limit 403
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        403,
        {"message": "API rate limit exceeded for 1.2.3.4."},
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)
    request_url = "https://github.com/DataDog/dd-license-attribution"

    # First call: 3 attempts, returns the fallback original URL
    canonical_url, api_url = source_code_manager.get_canonical_urls(request_url)
    assert canonical_url == request_url
    assert api_url is None
    assert repo_mock.get.mock_calls == [call(), call(), call()]
    assert sleep_mock.mock_calls == [call(2.0), call(4.0)]

    # Second call: the rate limit fallback is not cached, so the API is retried
    canonical_url2, api_url2 = source_code_manager.get_canonical_urls(request_url)
    assert canonical_url2 == request_url
    assert api_url2 is None
    assert repo_mock.get.mock_calls == [
        call(),
        call(),
        call(),
        call(),
        call(),
        call(),
    ]
    assert sleep_mock.mock_calls == [
        call(2.0),
        call(4.0),
        call(2.0),
        call(4.0),
    ]
    git_url_parse_mock.assert_has_calls([call(request_url), call(request_url)])
    assert request_url not in source_code_manager._canonical_urls_cache
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_canonical_urls_caches_permanent_failure_fallback(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
) -> None:
    """Test that get_canonical_urls caches the fallback for permanent failures (404 and non-rate-limit 403)."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    git_url_parse_mock.return_value.valid = True
    git_url_parse_mock.return_value.github = True
    git_url_parse_mock.return_value.owner = "DataDog"
    git_url_parse_mock.return_value.repo = "dd-license-attribution"
    git_url_parse_mock.return_value.protocol = "https"
    git_url_parse_mock.return_value.host = "github.com"

    # Mock GitHub API client to return a permanent error
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        404,
        {"message": "Not Found"},
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)
    request_url = "https://github.com/DataDog/dd-license-attribution"

    # First call: returns the fallback original URL and caches it
    canonical_url, api_url = source_code_manager.get_canonical_urls(request_url)
    assert canonical_url == request_url
    assert api_url is None
    repo_mock.get.assert_called_once_with()

    # Second call: served from the cache, no further API calls
    canonical_url2, api_url2 = source_code_manager.get_canonical_urls(request_url)
    assert canonical_url2 == request_url
    assert api_url2 is None
    repo_mock.get.assert_called_once_with()
    git_url_parse_mock.assert_called_once_with(request_url)
    assert source_code_manager._canonical_urls_cache[request_url] == (
        request_url,
        None,
    )
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.parse_git_url")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_canonical_urls_caches_permanent_403_fallback(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    git_url_parse_mock: Mock,
) -> None:
    """Test that get_canonical_urls caches the fallback for a permanent (non-rate-limit) 403."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    git_url_parse_mock.return_value.valid = True
    git_url_parse_mock.return_value.github = True
    git_url_parse_mock.return_value.owner = "DataDog"
    git_url_parse_mock.return_value.repo = "dd-license-attribution"
    git_url_parse_mock.return_value.protocol = "https"
    git_url_parse_mock.return_value.host = "github.com"

    # Mock GitHub API client to return a permanent 403 (access denied, not a
    # rate limit)
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        403,
        {"message": "Resource not accessible by integration"},
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)
    request_url = "https://github.com/DataDog/dd-license-attribution"

    # First call: returns the fallback original URL and caches it
    canonical_url, api_url = source_code_manager.get_canonical_urls(request_url)
    assert canonical_url == request_url
    assert api_url is None
    repo_mock.get.assert_called_once_with()

    # Second call: served from the cache, no further API calls
    canonical_url2, api_url2 = source_code_manager.get_canonical_urls(request_url)
    assert canonical_url2 == request_url
    assert api_url2 is None
    repo_mock.get.assert_called_once_with()
    git_url_parse_mock.assert_called_once_with(request_url)
    assert source_code_manager._canonical_urls_cache[request_url] == (
        request_url,
        None,
    )
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_retries_429_responses(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """Test that get_repository_info retries 429 (secondary rate limit) responses with exponential backoff."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock GitHub API client: a 429 response, then a 200
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.side_effect = [
        (429, {"message": "You have exceeded a secondary rate limit"}),
        (
            200,
            {
                "html_url": "https://github.com/DataDog/dd-license-attribution",
                "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
                "license": {"spdx_id": "Apache-2.0"},
                "owner": {"login": "DataDog"},
            },
        ),
    ]
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # Call get_repository_info - should retry the 429 and succeed
    status, result = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )

    assert status == 200
    assert result is not None
    assert result["html_url"] == "https://github.com/DataDog/dd-license-attribution"
    repo_mock.get.assert_has_calls([call(), call()])
    sleep_mock.assert_called_once_with(2.0)

    # Verify the successful result is cached (no further API calls)
    status2, result2 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status2 == 200
    assert result2 == result
    repo_mock.get.assert_has_calls([call(), call()])
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_exhausts_retries_on_persistent_429(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """Test that get_repository_info exhausts retries on a persistent 429, returns the error, and does not cache it."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock GitHub API client to always return 429
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (
        429,
        {"message": "You have exceeded a secondary rate limit"},
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # First call: 3 attempts (initial + 2 retries), backoff delays of 2 then 4 seconds
    status1, result1 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status1 == 429
    assert result1 is not None
    repo_mock.get.assert_has_calls([call(), call(), call()])
    sleep_mock.assert_has_calls([call(2.0), call(4.0)])

    # Second call: the 429 is not cached, so the API is retried again
    status2, result2 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status2 == 429
    assert result2 == result1
    repo_mock.get.assert_has_calls([call(), call(), call(), call(), call(), call()])
    sleep_mock.assert_has_calls([call(2.0), call(4.0), call(2.0), call(4.0)])
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.current_time")
@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_confirms_rate_limit_from_headers_over_message(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
    current_time_mock: Mock,
) -> None:
    """Test that X-RateLimit-Remaining: 0 confirms a rate limit 403 even when the message does not mention one."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []
    current_time_mock.return_value = 1000.0

    # Mock GitHub API client: a 403 with a non-rate-limit message, then 200.
    # The response headers confirm the 403 is a rate limit (remaining: 0) and
    # advise waiting 5 seconds via Retry-After.
    github_client_mock = Mock()
    github_client_mock.getheaders.return_value = [
        ("X-RateLimit-Remaining", "0"),
        ("Retry-After", "5"),
    ]
    repo_mock = Mock()
    repo_mock.get.side_effect = [
        (403, {"message": "Forbidden"}),
        (
            200,
            {
                "html_url": "https://github.com/DataDog/dd-license-attribution",
                "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
                "license": {"spdx_id": "Apache-2.0"},
                "owner": {"login": "DataDog"},
            },
        ),
    ]
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    status, result = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )

    assert status == 200
    assert result is not None
    assert result["html_url"] == "https://github.com/DataDog/dd-license-attribution"
    # One initial attempt plus one retry, waiting the server-advised
    # Retry-After (5s) plus the buffer (1s)
    repo_mock.get.assert_has_calls([call(), call()])
    sleep_mock.assert_called_once_with(6.0)
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_retries_secondary_rate_limit_with_positive_primary_quota(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """A secondary rate limit 403 is detected even when the primary quota (X-RateLimit-Remaining) is positive."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # A 403 whose message confirms a secondary rate limit while the primary
    # quota header is still positive (it only tracks the primary quota).
    github_client_mock = Mock()
    # The primary X-RateLimit-Reset epoch is present but must NOT be used
    # as advice - the primary quota is not the thing that was exceeded.
    github_client_mock.getheaders.return_value = [
        ("X-RateLimit-Remaining", "4899"),
        ("X-RateLimit-Reset", "1699999999"),
    ]
    repo_mock = Mock()
    repo_mock.get.side_effect = [
        (403, {"message": "You have exceeded a secondary rate limit"}),
        (
            200,
            {
                "html_url": "https://github.com/DataDog/dd-license-attribution",
                "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
                "license": {"spdx_id": "Apache-2.0"},
                "owner": {"login": "DataDog"},
            },
        ),
    ]
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    status, result = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )

    assert status == 200
    assert result is not None
    repo_mock.get.assert_has_calls([call(), call()])
    # No Retry-After or X-RateLimit-Reset advice: exponential backoff
    sleep_mock.assert_called_once_with(2.0)
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_retry_after_header_wins_over_positive_quota(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """A 403 with a Retry-After header is a secondary rate limit even when the primary quota is positive."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    github_client_mock = Mock()
    github_client_mock.getheaders.return_value = [
        ("X-RateLimit-Remaining", "4899"),
        ("Retry-After", "5"),
    ]
    repo_mock = Mock()
    repo_mock.get.side_effect = [
        (403, {"message": "You have exceeded a secondary rate limit"}),
        (
            200,
            {
                "html_url": "https://github.com/DataDog/dd-license-attribution",
                "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
                "license": {"spdx_id": "Apache-2.0"},
                "owner": {"login": "DataDog"},
            },
        ),
    ]
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    status, result = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )

    assert status == 200
    assert result is not None
    repo_mock.get.assert_has_calls([call(), call()])
    # The Retry-After advice (5s + 1s buffer) is honored
    sleep_mock.assert_called_once_with(6.0)
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.current_time")
@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_waits_until_rate_limit_reset_epoch(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
    current_time_mock: Mock,
) -> None:
    """Test that the retry waits until the X-RateLimit-Reset epoch (plus buffer)."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []
    current_time_mock.return_value = 1000.0

    # A 403 with exhausted quota; the window resets 30 seconds from now
    github_client_mock = Mock()
    github_client_mock.getheaders.return_value = [
        ("X-RateLimit-Remaining", "0"),
        ("X-RateLimit-Reset", "1030"),
    ]
    repo_mock = Mock()
    repo_mock.get.side_effect = [
        (403, {"message": "API rate limit exceeded for 1.2.3.4."}),
        (
            200,
            {
                "html_url": "https://github.com/DataDog/dd-license-attribution",
                "url": "https://api.github.com/repos/DataDog/dd-license-attribution",
                "license": {"spdx_id": "Apache-2.0"},
                "owner": {"login": "DataDog"},
            },
        ),
    ]
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    status, result = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )

    assert status == 200
    assert result is not None
    repo_mock.get.assert_has_calls([call(), call()])
    # Wait until the reset epoch (1030) minus now (1000), plus the buffer (1s)
    sleep_mock.assert_called_once_with(31.0)
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_does_not_retry_when_advised_wait_exceeds_cap(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """Test that an advised wait longer than the cap is not retried and not cached."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # A 429 whose Retry-After (600s) exceeds the retry cap: no retry, no sleep
    github_client_mock = Mock()
    github_client_mock.getheaders.return_value = [("Retry-After", "600")]
    repo_mock = Mock()
    repo_mock.get.return_value = (
        429,
        {"message": "You have exceeded a secondary rate limit"},
    )
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # First call: single API attempt, no sleep (retrying before the server
    # allows would be aggressive)
    status1, result1 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status1 == 429
    assert result1 is not None
    repo_mock.get.assert_called_once_with()
    sleep_mock.assert_not_called()

    # Second call: the rate limit result is not cached, so the API is retried
    status2, result2 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status2 == 429
    assert result2 == result1
    repo_mock.get.assert_has_calls([call(), call()])
    sleep_mock.assert_not_called()
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")


@patch("dd_license_attribution.artifact_management.source_code_manager.sleep")
@patch("dd_license_attribution.artifact_management.artifact_manager.list_dir")
@patch("dd_license_attribution.artifact_management.artifact_manager.path_exists")
def test_get_repository_info_retries_5xx_server_errors(
    path_exists_mock: Mock,
    list_dir_mock: Mock,
    sleep_mock: Mock,
) -> None:
    """Test that 5xx server errors are retried with exponential backoff and not cached."""
    # Configure mocks
    path_exists_mock.return_value = True
    list_dir_mock.return_value = []

    # Mock GitHub API client to always return 500 (transient server error)
    github_client_mock = Mock()
    repo_mock = Mock()
    repo_mock.get.return_value = (500, {"message": "Internal Server Error"})
    owner_mock = Mock()
    owner_mock.__getitem__ = Mock(return_value=repo_mock)
    repos_mock = Mock()
    repos_mock.__getitem__ = Mock(return_value=owner_mock)
    github_client_mock.repos = repos_mock

    source_code_manager = SourceCodeManager("cache_dir", github_client_mock, 86400)

    # First call: 3 attempts (initial + 2 retries), backoff delays of 2 then 4 seconds
    status1, result1 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status1 == 500
    repo_mock.get.assert_has_calls([call(), call(), call()])
    sleep_mock.assert_has_calls([call(2.0), call(4.0)])

    # Second call: the transient 500 is not cached, so the API is retried again
    status2, result2 = source_code_manager.get_repository_info(
        "DataDog", "dd-license-attribution"
    )
    assert status2 == 500
    assert result2 == result1
    repo_mock.get.assert_has_calls([call(), call(), call(), call(), call(), call()])
    sleep_mock.assert_has_calls([call(2.0), call(4.0), call(2.0), call(4.0)])
    path_exists_mock.assert_called_once_with("cache_dir")
    list_dir_mock.assert_called_once_with("cache_dir")
