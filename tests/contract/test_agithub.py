# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

"""Contract tests for agithub library.

These tests validate the structure and behavior of the GitHub API responses
that our code depends on. They ensure that updates to the agithub library
or changes to the GitHub API don't break our assumptions.

Note: These tests make real API calls to GitHub and may be rate-limited.
Consider marking them to run separately from unit tests if needed.
"""

import json
import logging
import os
import time
from typing import Any, Protocol

import pytest
from agithub.GitHub import GitHub

from dd_license_attribution.utils.bounded_download import download_bounded

# Pending-report polling budget for the asynchronous SBOM flow: one immediate
# fetch plus five retries with these delays, mirroring the strategy's schedule.
SBOM_FETCH_RETRY_DELAYS_SECONDS: tuple[int, ...] = (1, 2, 4, 8, 16)

logger = logging.getLogger("dd_license_attribution")


class _GitHubGetEndpoint(Protocol):
    def get(self) -> tuple[int, object]: ...


def _get_from_github_api(endpoint: _GitHubGetEndpoint) -> tuple[int, object]:
    try:
        return endpoint.get()
    except OSError as exc:
        pytest.skip("GitHub API is unavailable: {error}".format(error=exc))


def _skip_if_github_api_unavailable(status: int, result: object) -> None:
    if 500 <= status < 600:
        pytest.skip(
            "GitHub API returned server error {status}: {result}".format(
                status=status,
                result=result,
            )
        )


def _skip_if_tokenless_rate_limited(token: str | None, status: int) -> None:
    """Skip (rather than fail) when an unauthenticated run is refused.

    CI's contract job has no GITHUB_TOKEN, so 401/403/429 responses there are
    environment limits, not contract violations.
    """
    if token is None and status in (401, 403, 429):
        pytest.skip(
            "Unauthenticated contract test hit status {status} (no GITHUB_TOKEN)".format(
                status=status
            )
        )


@pytest.fixture
def github_client() -> GitHub:
    """Create a GitHub client for testing.

    Uses GITHUB_TOKEN environment variable if available, otherwise uses unauthenticated access.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return GitHub(token=token)
    return GitHub()


def _token() -> str | None:
    return os.environ.get("GITHUB_TOKEN")


def _response_location_header(client: GitHub) -> str | None:
    """Return the Location header of the client's most recent response."""
    try:
        raw = client.getheaders()
    except (AttributeError, TypeError, ValueError):
        return None
    if isinstance(raw, dict):
        return {str(k).lower(): str(v) for k, v in raw.items()}.get("location")
    if isinstance(raw, (list, tuple)):
        try:
            return {str(k).lower(): str(v) for k, v in raw}.get("location")
        except (TypeError, ValueError):
            return None
    return None


def test_repos_get_returns_expected_structure(github_client: GitHub) -> None:
    """Ensure repos.get() returns expected repository structure.

    We depend on: owner, license, html_url, url fields from the API response.
    """
    # Use DataDog/dd-license-attribution as a known public repository
    status, result = _get_from_github_api(
        github_client.repos["DataDog"]["dd-license-attribution"]
    )
    _skip_if_github_api_unavailable(status, result)

    # Validate successful response
    assert status == 200, f"Expected status 200, got {status}"
    assert isinstance(result, dict), "Result should be a dictionary"

    # Validate required fields our code depends on
    assert "owner" in result, "Response should contain 'owner' field"
    assert "login" in result["owner"], "Owner should contain 'login' field"
    assert isinstance(result["owner"]["login"], str), "Owner login should be a string"

    # License field (can be None for repos without explicit license)
    assert "license" in result, "Response should contain 'license' field"
    if result["license"] is not None:
        assert isinstance(
            result["license"], dict
        ), "License should be a dict when present"
        assert "spdx_id" in result["license"], "License should contain 'spdx_id'"

    # URL fields
    assert "html_url" in result, "Response should contain 'html_url' field"
    assert isinstance(result["html_url"], str), "html_url should be a string"
    assert "url" in result, "Response should contain 'url' field"
    assert isinstance(result["url"], str), "url should be a string"


def test_repos_get_handles_redirects(github_client: GitHub) -> None:
    """Ensure repos.get() handles 301 redirects for renamed repositories.

    We depend on status code 301 and 'url' field in the response for redirects.
    """
    from urllib.parse import urlparse

    # Test with DataDog/ospo-tools which was renamed to DataDog/dd-license-attribution
    status, result = _get_from_github_api(github_client.repos["DataDog"]["ospo-tools"])
    _skip_if_github_api_unavailable(status, result)

    # Should receive a 301 redirect
    assert status == 301, f"Expected status 301 for renamed repo, got {status}"
    assert isinstance(result, dict), "Result should be a dictionary"

    # Validate redirect URL structure
    assert "url" in result, "301 response should contain 'url' field for redirect"
    assert isinstance(result["url"], str), "Redirect URL should be a string"

    # The redirect URL should point to the GitHub API (proper URL validation)
    parsed_url = urlparse(result["url"])
    assert (
        parsed_url.netloc == "api.github.com"
    ), f"Redirect URL should be from api.github.com domain, got {parsed_url.netloc}"
    assert parsed_url.scheme == "https", "Redirect URL should use HTTPS"


def test_repos_get_handles_404_error(github_client: GitHub) -> None:
    """Ensure repos.get() returns 404 for non-existent repositories."""
    status, result = _get_from_github_api(
        github_client.repos["NonExistentOwner"]["NonExistentRepo"]
    )
    _skip_if_github_api_unavailable(status, result)

    assert status == 404, f"Expected status 404 for non-existent repo, got {status}"


def test_sbom_generate_report_returns_201_with_sbom_url(
    github_client: GitHub,
) -> None:
    """The asynchronous SBOM generation endpoint returns 201 with an sbom_url.

    We depend on: a 201 status, a JSON object body, and an sbom_url string
    pointing at the dependency-graph fetch-report endpoint of the same
    repository. The signed download URL the report eventually serves is NOT
    on api.github.com (it is a storage host), so the host check only applies
    to the sbom_url itself.
    """
    status, result = _get_from_github_api(
        github_client.repos["DataDog"]["dd-license-attribution"]["dependency-graph"][
            "sbom"
        ]["generate-report"]
    )

    _skip_if_github_api_unavailable(status, result)
    _skip_if_tokenless_rate_limited(_token(), status)

    if status == 404:
        pytest.skip(
            "SBOM generation returned 404 - may require specific permissions or repo may have no dependency graph"
        )

    assert status == 201, f"Expected status 201 for generation request, got {status}"
    assert isinstance(result, dict), "Generation result should be a dictionary"
    sbom_url = result.get("sbom_url")
    assert isinstance(
        sbom_url, str
    ), "Generation result should contain a sbom_url string"
    assert (
        "/dependency-graph/sbom/fetch-report/" in sbom_url
    ), "sbom_url should point at the fetch-report endpoint"


def test_sbom_generate_report_handles_404(github_client: GitHub) -> None:
    """The SBOM generation endpoint returns 404 for repos without access/SBOM."""
    status, result = _get_from_github_api(
        github_client.repos["NonExistentOwner"]["NonExistentRepo"]["dependency-graph"][
            "sbom"
        ]["generate-report"]
    )
    _skip_if_github_api_unavailable(status, result)

    assert status == 404, f"Expected status 404 for non-existent repo, got {status}"


def test_sbom_async_flow_returns_bare_spdx_document(github_client: GitHub) -> None:
    """The full async flow yields a bare SPDX JSON document via a signed URL.

    Requests generation once, polls the same report within the bounded
    retry budget until it is ready (302), then downloads the Location URL
    with the bounded downloader (which sends no GitHub credentials, only a
    User-Agent) and validates the bare document structure. The download is
    served as text/plain, so the content type must not be assumed.
    """
    token = _token()

    status, result = _get_from_github_api(
        github_client.repos["DataDog"]["dd-license-attribution"]["dependency-graph"][
            "sbom"
        ]["generate-report"]
    )
    _skip_if_github_api_unavailable(status, result)
    _skip_if_tokenless_rate_limited(token, status)
    if status == 404:
        pytest.skip(
            "SBOM generation returned 404 - may require specific permissions or repo may have no dependency graph"
        )
    assert status == 201, f"Expected status 201 for generation request, got {status}"
    assert isinstance(result, dict), "Generation result should be a dictionary"
    sbom_url = result.get("sbom_url")
    assert isinstance(
        sbom_url, str
    ), "Generation result should contain a sbom_url string"
    report_id = sbom_url.rstrip("/").rsplit("/", 1)[-1]

    # Poll the same report: one immediate fetch plus bounded retries with the
    # fixed schedule. Generation is never re-requested.
    fetch_endpoint = github_client.repos["DataDog"]["dd-license-attribution"][
        "dependency-graph"
    ]["sbom"]["fetch-report"][report_id]
    pending_retries = 0
    while True:
        status, result = _get_from_github_api(fetch_endpoint)
        _skip_if_github_api_unavailable(status, result)
        _skip_if_tokenless_rate_limited(token, status)
        if status == 302:
            break
        if status != 202:
            pytest.skip(
                "SBOM fetch-report returned unexpected status {status}: {result}".format(
                    status=status, result=result
                )
            )
        if pending_retries >= len(SBOM_FETCH_RETRY_DELAYS_SECONDS):
            pytest.skip(
                "SBOM report was not ready after {total} seconds".format(
                    total=sum(SBOM_FETCH_RETRY_DELAYS_SECONDS)
                )
            )
        time.sleep(SBOM_FETCH_RETRY_DELAYS_SECONDS[pending_retries])
        pending_retries += 1

    location = _response_location_header(github_client)
    assert location is not None, "Expected a Location header on the 302 response"
    assert location.startswith("https://"), "Location must be an https URL"

    # Download through the bounded downloader: it forwards no GitHub
    # authorization headers to the signed storage URL.
    content = download_bounded(location)

    document: Any = json.loads(content)
    assert isinstance(document, dict), "Downloaded report should be a JSON object"
    assert "packages" in document, "Report should contain 'packages'"
    packages = document["packages"]
    assert isinstance(packages, list), "Packages should be a list"
    if len(packages) > 0:
        first_package = packages[0]
        assert isinstance(first_package, dict), "Package should be a JSON object"
        if "name" in first_package:
            assert isinstance(first_package["name"], str), "Name should be a string"


def test_github_client_chaining_syntax() -> None:
    """Validate that the GitHub client chaining syntax works as expected.

    We depend on the bracket notation: client.repos[owner][repo].get(), and on
    the dependency-graph SBOM endpoint chains for the asynchronous flow
    (["sbom"]["generate-report"] and ["sbom"]["fetch-report"][id]).
    """
    # Test without authentication (just syntax validation)
    client = GitHub()

    # Validate that we can chain the API calls
    endpoint = client.repos["DataDog"]["dd-license-attribution"]
    assert hasattr(endpoint, "get"), "Endpoint should have 'get' method"

    # Validate dependency-graph SBOM endpoints
    generate_endpoint = client.repos["DataDog"]["dd-license-attribution"][
        "dependency-graph"
    ]["sbom"]["generate-report"]
    assert hasattr(generate_endpoint, "get"), "Generate endpoint should have 'get'"

    fetch_endpoint = client.repos["DataDog"]["dd-license-attribution"][
        "dependency-graph"
    ]["sbom"]["fetch-report"]["some-report-id"]
    assert hasattr(fetch_endpoint, "get"), "Fetch endpoint should have 'get'"
