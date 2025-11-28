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

import os

import pytest
from agithub.GitHub import GitHub


@pytest.fixture
def github_client() -> GitHub:
    """Create a GitHub client for testing.

    Uses GITHUB_TOKEN environment variable if available, otherwise uses unauthenticated access.
    """
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        return GitHub(token=token)
    return GitHub()


def test_repos_get_returns_expected_structure(github_client: GitHub) -> None:
    """Ensure repos.get() returns expected repository structure.

    We depend on: owner, license, html_url, url fields from the API response.
    """
    # Use DataDog/dd-license-attribution as a known public repository
    status, result = github_client.repos["DataDog"]["dd-license-attribution"].get()

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
    status, result = github_client.repos["DataDog"]["ospo-tools"].get()

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
    status, result = github_client.repos["NonExistentOwner"]["NonExistentRepo"].get()

    assert status == 404, f"Expected status 404 for non-existent repo, got {status}"


def test_dependency_graph_sbom_get_returns_expected_structure(
    github_client: GitHub,
) -> None:
    """Ensure dependency-graph.sbom.get() returns expected SBOM structure.

    We depend on: sbom.packages field with name, SPDXID in package data.
    """
    # Use DataDog/dd-license-attribution as a known public repository with dependencies
    status, result = github_client.repos["DataDog"]["dd-license-attribution"][
        "dependency-graph"
    ].sbom.get()

    if status == 404:
        pytest.skip(
            "SBOM API returned 404 - may require specific permissions or repo may not have SBOM"
        )

    # Validate successful response
    assert status == 200, f"Expected status 200, got {status}"
    assert isinstance(result, dict), "Result should be a dictionary"

    # Validate SBOM structure
    assert "sbom" in result, "Response should contain 'sbom' field"
    sbom = result["sbom"]
    assert isinstance(sbom, dict), "SBOM should be a dictionary"

    # Validate packages structure
    assert "packages" in sbom, "SBOM should contain 'packages' field"
    packages = sbom["packages"]
    assert isinstance(packages, list), "Packages should be a list"

    if len(packages) > 0:
        # Validate package structure
        first_package = packages[0]
        assert "name" in first_package, "Package should contain 'name' field"
        assert isinstance(first_package["name"], str), "Package name should be a string"

        # SPDXID is used to filter out GitHub Actions
        if "SPDXID" in first_package:
            assert isinstance(first_package["SPDXID"], str), "SPDXID should be a string"


def test_dependency_graph_sbom_get_handles_404(github_client: GitHub) -> None:
    """Ensure dependency-graph.sbom.get() returns 404 for repos without access/SBOM."""
    # Use a non-existent repository
    status, result = github_client.repos["NonExistentOwner"]["NonExistentRepo"][
        "dependency-graph"
    ].sbom.get()

    assert status == 404, f"Expected status 404 for non-existent repo, got {status}"


def test_github_client_chaining_syntax() -> None:
    """Validate that the GitHub client chaining syntax works as expected.

    We depend on the bracket notation: client.repos[owner][repo].get()
    """
    # Test without authentication (just syntax validation)
    client = GitHub()

    # Validate that we can chain the API calls
    endpoint = client.repos["DataDog"]["dd-license-attribution"]
    assert hasattr(endpoint, "get"), "Endpoint should have 'get' method"

    # Validate dependency-graph endpoint
    endpoint = client.repos["DataDog"]["dd-license-attribution"]["dependency-graph"]
    assert hasattr(endpoint, "sbom"), "Endpoint should have 'sbom' attribute"
