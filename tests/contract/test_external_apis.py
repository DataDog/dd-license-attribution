# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

"""Contract tests for external package registry APIs.

These tests validate the structure and behavior of PyPI and npm registry APIs
that our code depends on. They ensure that API changes don't break our assumptions.

Note: These tests make real HTTP requests and may be affected by network issues.
"""

import requests


def test_pypi_api_returns_expected_structure() -> None:
    """Ensure PyPI API returns expected package metadata structure.

    We depend on: info.name, info.version, info.license, info.author, info.project_urls
    from the PyPI JSON API response.
    """
    # Use a known stable package for testing
    package = "requests"
    version = "2.31.0"

    response = requests.get(f"https://pypi.org/pypi/{package}/{version}/json")

    assert (
        response.status_code == 200
    ), f"Expected status 200, got {response.status_code}"

    data = response.json()
    assert isinstance(data, dict), "Response should be a dictionary"

    # Validate 'info' field structure
    assert "info" in data, "Response should contain 'info' field"
    info = data["info"]
    assert isinstance(info, dict), "Info should be a dictionary"

    # Fields our code depends on
    assert "name" in info, "Info should contain 'name' field"
    assert isinstance(info["name"], str), "Name should be a string"

    assert "version" in info, "Info should contain 'version' field"
    assert isinstance(info["version"], str), "Version should be a string"

    # License field (can be null/None)
    assert "license" in info, "Info should contain 'license' field"
    if info["license"]:
        assert isinstance(
            info["license"], str
        ), "License should be a string when present"

    # Author field (can be null/None)
    assert "author" in info, "Info should contain 'author' field"
    if info["author"]:
        assert isinstance(info["author"], str), "Author should be a string when present"

    # Project URLs field (can be null/None)
    assert "project_urls" in info, "Info should contain 'project_urls' field"
    if info["project_urls"]:
        assert isinstance(
            info["project_urls"], dict
        ), "Project URLs should be a dict when present"
        # Common keys we check for
        possible_keys = [
            "Homepage",
            "GitHub",
            "Repository",
            "Code",
            "Source Code",
            "Source",
        ]
        # At least some of these keys might be present


def test_pypi_api_handles_404_for_nonexistent_package() -> None:
    """Ensure PyPI API returns 404 for non-existent packages."""
    response = requests.get(
        "https://pypi.org/pypi/nonexistent-package-xyz-123/1.0.0/json"
    )

    assert (
        response.status_code == 404
    ), f"Expected status 404, got {response.status_code}"


def test_pypi_api_handles_404_for_nonexistent_version() -> None:
    """Ensure PyPI API returns 404 for non-existent package versions."""
    response = requests.get("https://pypi.org/pypi/requests/99.99.99/json")

    assert (
        response.status_code == 404
    ), f"Expected status 404, got {response.status_code}"


def test_npm_registry_api_returns_expected_structure() -> None:
    """Ensure npm registry API returns expected package metadata structure.

    We depend on: license, author (name or string), repository (url or string),
    homepage from the npm registry API response.
    """
    # Use dd-trace (a Datadog package) for testing
    dep_name = "dd-trace"
    version = "5.0.0"

    response = requests.get(
        f"https://registry.npmjs.org/{dep_name}/{version}",
        timeout=5,
    )

    assert (
        response.status_code == 200
    ), f"Expected status 200, got {response.status_code}"

    pkg_data = response.json()
    assert isinstance(pkg_data, dict), "Response should be a dictionary"

    # License field (our code depends on this)
    assert "license" in pkg_data, "Response should contain 'license' field"
    # License can be a string or absent
    if pkg_data["license"]:
        assert isinstance(
            pkg_data["license"], str
        ), "License should be a string when present"

    # Author field (can be dict with 'name' or a string, or null)
    if "author" in pkg_data and pkg_data["author"]:
        author = pkg_data["author"]
        if isinstance(author, dict):
            assert "name" in author, "Author dict should contain 'name' field"
            assert isinstance(author["name"], str), "Author name should be a string"
        elif isinstance(author, str):
            # Author can also be a plain string
            pass
        else:
            raise AssertionError(f"Author should be dict or string, got {type(author)}")

    # Repository field (can be dict with 'url' or a string, or null)
    if "repository" in pkg_data and pkg_data["repository"]:
        repo = pkg_data["repository"]
        if isinstance(repo, dict):
            assert "url" in repo, "Repository dict should contain 'url' field"
            assert isinstance(repo["url"], str), "Repository URL should be a string"
        elif isinstance(repo, str):
            # Repository can also be a plain string
            pass
        else:
            raise AssertionError(
                f"Repository should be dict or string, got {type(repo)}"
            )

    # Homepage field (optional string)
    if "homepage" in pkg_data and pkg_data["homepage"]:
        assert isinstance(
            pkg_data["homepage"], str
        ), "Homepage should be a string when present"


def test_npm_registry_api_handles_scoped_packages() -> None:
    """Ensure npm registry API works with scoped packages (e.g., @scope/package).

    Our code processes scoped packages, so we need to ensure the API structure is consistent.
    """
    # Use a known scoped package
    dep_name = "@types/node"
    version = "20.0.0"

    response = requests.get(
        f"https://registry.npmjs.org/{dep_name}/{version}",
        timeout=5,
    )

    assert (
        response.status_code == 200
    ), f"Expected status 200, got {response.status_code}"

    pkg_data = response.json()
    assert isinstance(pkg_data, dict), "Response should be a dictionary"

    # Validate name field contains the scope
    assert "name" in pkg_data, "Response should contain 'name' field"
    assert (
        pkg_data["name"] == "@types/node"
    ), "Name should match the scoped package name"


def test_npm_registry_api_handles_404_for_nonexistent_package() -> None:
    """Ensure npm registry API returns 404 for non-existent packages."""
    response = requests.get(
        "https://registry.npmjs.org/nonexistent-package-xyz-123/1.0.0",
        timeout=5,
    )

    # npm might return 404 or other error status
    assert response.status_code in [
        404,
        400,
    ], f"Expected error status code, got {response.status_code}"


def test_requests_library_json_parsing() -> None:
    """Validate that requests library .json() method works as expected.

    Our code calls response.json() to parse API responses.
    """
    response = requests.get("https://pypi.org/pypi/requests/2.31.0/json")
    assert response.status_code == 200

    # Validate .json() method exists and returns a dict
    data = response.json()
    assert isinstance(data, dict), "json() method should return a dictionary"
