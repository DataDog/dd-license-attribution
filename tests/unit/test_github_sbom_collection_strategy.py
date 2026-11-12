# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json
import logging
from typing import Any

import pytest
import pytest_mock

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.cleanup_copyright_metadata_strategy import (
    CleanupCopyrightMetadataStrategy,
)
from dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy import (
    GitHubSbomMetadataCollectionStrategy,
    ProjectScope,
)

STRATEGY_MODULE = "dd_license_attribution.metadata_collector.strategies.github_sbom_collection_strategy"
SOURCE_CODE_MANAGER_MODULE = (
    "dd_license_attribution.artifact_management.source_code_manager"
)
# Distinctive sentinel values used by the redaction tests: no log record may
# ever contain the report id or the signed download URL.
REPORT_ID = "rpt-SENTINEL-7f3a"
SBOM_URL = (
    "https://api.github.com/repos/test_owner/test_repo"
    f"/dependency-graph/sbom/fetch-report/{REPORT_ID}"
)
DOWNLOAD_URL = "https://storage.invalid/sbom-reports/SENTINEL?sig=SECRETSIG"


class GitUrlParseMock:
    def __init__(
        self, valid: bool, platform: str, owner: str | None, repo: str | None
    ) -> None:
        self.valid = valid
        self.platform = platform
        self.owner = owner
        self.repo = repo
        self.github = platform == "github"


class EndpointMock:
    """One agithub endpoint whose .get() pops configured responses.

    Each call records the response's headers on the client, mirroring how
    agithub exposes the headers of the most recent request through
    getheaders() (which is idempotent, so the retry helper and the strategy
    can both read them). The last configured response repeats forever, so a
    single-entry list models a persistent status.
    """

    def __init__(
        self,
        client: "AsyncSbomGitHubClientMock",
        responses: list[tuple[int, object]],
        headers: list[dict[str, str] | None] | None = None,
    ) -> None:
        assert responses, "EndpointMock requires at least one response"
        self._client = client
        self._responses = responses
        self._headers = headers if headers is not None else []
        self.calls = 0

    def set_responses(
        self,
        responses: list[tuple[int, object]],
        headers: list[dict[str, str] | None] | None = None,
    ) -> None:
        """Reconfigure the response sequence (used after make_client)."""
        assert responses, "EndpointMock requires at least one response"
        self._responses = responses
        self._headers = headers if headers is not None else []

    def get(self) -> tuple[int, object]:
        index = min(self.calls, len(self._responses) - 1)
        status, body = self._responses[index]
        self.calls += 1
        self._client.set_latest_headers(
            self._headers[index] if index < len(self._headers) else None
        )
        return (status, body)


class AsyncSbomGitHubClientMock:
    """agithub-style client mock for the asynchronous SBOM flow.

    Exposes repos[owner][repo]["dependency-graph"]["sbom"]["generate-report"]
    and repos[...]["sbom"]["fetch-report"][report_id] as EndpointMocks, plus
    an idempotent getheaders() returning the latest response's headers.
    """

    def __init__(self) -> None:
        self.repos: dict[str, Any] = {}
        self._latest_headers: dict[str, str] | None = None

    def set_latest_headers(self, headers: dict[str, str] | None) -> None:
        self._latest_headers = headers

    def getheaders(self) -> dict[str, str] | None:
        return self._latest_headers


def make_client(
    generate_responses: list[tuple[int, object]],
    fetch_responses: list[tuple[int, object]],
    fetch_headers: list[dict[str, str] | None] | None = None,
    generate_headers: list[dict[str, str] | None] | None = None,
    sbom_url: str = SBOM_URL,
) -> tuple[AsyncSbomGitHubClientMock, EndpointMock, EndpointMock]:
    """Build an async-flow client mock for test_owner/test_repo."""
    client = AsyncSbomGitHubClientMock()
    generate = EndpointMock(client, generate_responses, generate_headers)
    fetch = EndpointMock(client, fetch_responses, fetch_headers)
    report_id = sbom_url.rsplit("/", 1)[-1]
    client.repos = {
        "test_owner": {
            "test_repo": {
                "dependency-graph": {
                    "sbom": {
                        "generate-report": generate,
                        "fetch-report": {report_id: fetch},
                    }
                }
            }
        }
    }
    return client, generate, fetch


def make_success_client(
    mocker: pytest_mock.MockFixture,
    document: dict[str, Any],
    download_content: bytes | None = None,
) -> tuple[AsyncSbomGitHubClientMock, EndpointMock, EndpointMock, Any]:
    """Client mock for the happy path: 201 -> immediate 302 -> download."""
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(302, None)],
        fetch_headers=[{"location": DOWNLOAD_URL}],
    )
    content = (
        download_content
        if download_content is not None
        else json.dumps(document).encode()
    )
    download_mock = mocker.patch(
        f"{STRATEGY_MODULE}.download_bounded", return_value=content
    )
    return client, generate, fetch, download_mock


def patch_sleeps(mocker: pytest_mock.MockFixture) -> tuple[Any, Any]:
    """Patch both sleep bindings: the strategy's pending-poll sleep and the
    retry helper's transient backoff sleep."""
    strategy_sleep = mocker.patch(f"{STRATEGY_MODULE}.sleep")
    scm_sleep = mocker.patch(f"{SOURCE_CODE_MANAGER_MODULE}.sleep")
    return strategy_sleep, scm_sleep


def make_source_code_manager_mock(mocker: pytest_mock.MockFixture) -> Any:
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "https://github.com/test_owner/test_repo",
        "https://api.github.com/repos/test_owner/test_repo",
    )
    return source_code_manager_mock


def parse_git_url_mock(mocker: pytest_mock.MockFixture) -> Any:
    return mocker.patch(
        f"{STRATEGY_MODULE}.parse_git_url",
        return_value=GitUrlParseMock(
            valid=True, platform="github", owner="test_owner", repo="test_repo"
        ),
    )


def error_records(
    caplog: pytest.LogCaptureFixture, error_type: type[BaseException]
) -> list[str]:
    """Return the stringified exceptions of caught-and-logged failures."""
    return [
        str(record.exc_info[1])
        for record in caplog.records
        if record.exc_info is not None and isinstance(record.exc_info[1], error_type)
    ]


def test_github_sbom_collection_strategy_returns_same_metadata_if_not_a_github_repo(
    mocker: pytest_mock.MockFixture,
) -> None:
    github_client_mock = mocker.Mock(spec_set=object)
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.return_value = (
        "not_a_github_purl",
        None,
    )

    github_parse_mock = mocker.patch(
        f"{STRATEGY_MODULE}.parse_git_url",
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


def test_github_sbom_collection_strategy_raise_exception_if_error_calling_github_sbom_api(
    mocker: pytest_mock.MockFixture,
) -> None:
    """A persistent 500 on generation is retried with backoff before the package is skipped."""
    client, generate, fetch = make_client(
        generate_responses=[(500, "Server Error")], fetch_responses=[(302, None)]
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    github_parse_mock = parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    # Package should be returned with updated origin but no SBOM data
    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    # A transient 500 is retried: 3 attempts with 2s/4s exponential backoff
    assert generate.calls == 3
    scm_sleep.assert_has_calls([mocker.call(2.0), mocker.call(4.0)])
    strategy_sleep.assert_not_called()
    assert fetch.calls == 0
    download_mock.assert_not_called()


def test_github_sbom_collection_strategy_raise_special_exception_if_error_calling_github_sbom_api_is_404(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(404, "Not Found")], fetch_responses=[(302, None)]
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    github_parse_mock = parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    assert generate.calls == 1
    assert fetch.calls == 0
    download_mock.assert_not_called()
    # The retrieval failure is recoverable and logged with the exception
    errors = error_records(caplog, Exception)
    assert any("Inexistent repository or private repository" in e for e in errors)
    strategy_sleep.assert_not_called()
    scm_sleep.assert_not_called()


def test_github_sbom_collection_strategy_raise_special_exception_if_error_calling_github_sbom_api_is_401(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(401, "Unauthorized")], fetch_responses=[(302, None)]
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    github_parse_mock = parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"

    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")
    assert generate.calls == 1
    assert fetch.calls == 0
    download_mock.assert_not_called()
    errors = error_records(caplog, Exception)
    assert any("doesn't have enough permissions" in e for e in errors)
    strategy_sleep.assert_not_called()
    scm_sleep.assert_not_called()


def test_github_sbom_collection_strategy_with_no_new_info_skips_actions_and_returns_original_info(
    mocker: pytest_mock.MockFixture,
) -> None:
    document = {
        "packages": [
            {
                "SPDXID": "SPDXRef-githubactions-somthing-that-acts"
            },  # this should be skipped
            # No other packages in SBOM for this test
        ]
    }
    client, generate, fetch, download_mock = make_success_client(mocker, document)
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    github_parse_mock = parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
    assert generate.calls == 1
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)
    strategy_sleep.assert_not_called()


def test_github_sbom_collection_strategy_with_new_info_is_not_lost_in_repeated_package(
    mocker: pytest_mock.MockFixture,
) -> None:
    document = {
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
    client, generate, fetch, download_mock = make_success_client(mocker, document)
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

    giturlparse_mock = parse_git_url_mock(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert generate.calls == 1
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_strategy_does_not_add_dependencies_with_transitive_dependencies_is_false(
    mocker: pytest_mock.MockFixture,
) -> None:
    document = {
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
    client, generate, fetch, download_mock = make_success_client(mocker, document)
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    github_parse_mock = parse_git_url_mock(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
    assert generate.calls == 1
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_strategy_does_not_keep_root_when_with_root_project_is_false(
    mocker: pytest_mock.MockFixture,
) -> None:
    document = {
        "packages": [
            {
                "name": "com.github.test_owner/test_repo",
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
    client, generate, fetch, download_mock = make_success_client(mocker, document)
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    github_parse_mock = parse_git_url_mock(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
    assert generate.calls == 1
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_github_sbom_collection_strategy_handles_company_names_in_copyright(
    mocker: pytest_mock.MockFixture,
) -> None:
    document = {
        "packages": [
            {
                "name": "test-package",
                "copyrightText": "Company A, Copyright 2024 Company B, Inc. and its affiliates, Company C, llc, Company Datadog",
            }
        ]
    }
    client, generate, fetch, download_mock = make_success_client(mocker, document)
    source_code_manager_mock = make_source_code_manager_mock(mocker)

    mocker.patch(
        f"{STRATEGY_MODULE}.parse_git_url",
        return_value=GitUrlParseMock(True, "github", "test_owner", "test_repo"),
    )

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
        source_code_manager=source_code_manager_mock,
        project_scope=ProjectScope.ALL,
    )
    cleanup_copyright_metadata_strategy = CleanupCopyrightMetadataStrategy()

    initial_metadata = [
        Metadata(
            name="test-package",
            version=None,
            origin="https://github.com/test_owner/test_repo",
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
    download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_github_sbom_collection_strategy_uses_name_as_origin_if_download_location_is_empty_or_noassertion(
    mocker: pytest_mock.MockFixture,
) -> None:
    document = {
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
    client, generate, fetch, download_mock = make_success_client(mocker, document)
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    giturlparse_mock = parse_git_url_mock(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
    assert generate.calls == 1
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_github_sbom_collection_strategy_retries_429_rate_limit(
    mocker: pytest_mock.MockFixture,
) -> None:
    """A 429 secondary rate limit on generation is retried with backoff before succeeding."""
    sbom_content = {
        "SPDXID": "SPDXRef-Document",
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-test_owner-test_repo",
                "name": "test_owner/test_repo",
                "licenseConcluded": "MIT",
                "versionInfo": "1.0.0",
            }
        ],
    }
    client, generate, fetch, download_mock = make_success_client(mocker, sbom_content)
    # Reconfigure generation to hit a 429 first, then succeed
    generate.set_responses(
        [
            (429, {"message": "You have exceeded a secondary rate limit"}),
            (201, {"sbom_url": SBOM_URL}),
        ]
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    github_parse_mock = parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    # The SBOM should have been retrieved on the second attempt: generation
    # was called once for the 429 and once for the successful retry, waiting
    # the exponential backoff between them
    scm_sleep.assert_called_once_with(2.0)
    strategy_sleep.assert_not_called()
    assert len(updated_metadata) >= 1
    assert generate.calls == 2
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)
    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")


def test_github_sbom_collection_strategy_does_not_retry_permanent_403(
    mocker: pytest_mock.MockFixture,
) -> None:
    """A permanent (non-rate-limit) 403 is not retried."""
    client, generate, fetch = make_client(
        generate_responses=[
            (403, {"message": "Resource not accessible by integration"})
        ],
        fetch_responses=[(302, None)],
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    github_parse_mock = parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    # Errors are caught and packages are skipped rather than raising. The
    # package should be returned with the canonical origin but no SBOM data,
    # without any retry.
    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert generate.calls == 1
    assert fetch.calls == 0
    download_mock.assert_not_called()
    strategy_sleep.assert_not_called()
    scm_sleep.assert_not_called()
    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")


def test_github_sbom_collection_strategy_honors_retry_after_header(
    mocker: pytest_mock.MockFixture,
) -> None:
    """The generation retry waits the server-advised Retry-After (plus buffer)."""
    sbom_content = {
        "SPDXID": "SPDXRef-Document",
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-test_owner-test_repo",
                "name": "test_owner/test_repo",
                "licenseConcluded": "MIT",
                "versionInfo": "1.0.0",
            }
        ],
    }
    client, generate, fetch, download_mock = make_success_client(mocker, sbom_content)
    # The 429 response carries the Retry-After advice read after that call
    generate.set_responses(
        [
            (429, {"message": "You have exceeded a secondary rate limit"}),
            (201, {"sbom_url": SBOM_URL}),
        ],
        headers=[{"Retry-After": "3"}, None],
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    github_parse_mock = parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    # Generation was retried on the second attempt, waiting the advised 3s
    # plus the 1s buffer
    scm_sleep.assert_called_once_with(4.0)
    strategy_sleep.assert_not_called()
    assert len(updated_metadata) >= 1
    assert generate.calls == 2
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)
    source_code_manager_mock.get_canonical_urls.assert_called_once_with("test_purl")
    github_parse_mock.assert_called_once_with("https://github.com/test_owner/test_repo")


# ---------------------------------------------------------------------------
# Asynchronous-flow regression tests
# ---------------------------------------------------------------------------


def test_async_flow_success_on_first_fetch_enriches_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    """201 -> immediate 302 -> download: full enrichment with one round trip per stage."""
    document = {
        "packages": [
            {
                "name": "package1",
                "versionInfo": "2.0",
                "licenseDeclared": "APACHE-2.0",
                "downloadLocation": "test_purl",
            }
        ]
    }
    client, generate, fetch, download_mock = make_success_client(mocker, document)
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata == [
        Metadata(
            name="package1",
            version="2.0",
            origin="https://github.com/test_owner/test_repo",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        )
    ]
    # One generation request, one immediate fetch, one download, no waiting
    assert generate.calls == 1
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)
    strategy_sleep.assert_not_called()
    scm_sleep.assert_not_called()


def test_async_flow_accepts_cross_host_download_location(
    mocker: pytest_mock.MockFixture,
) -> None:
    """The signed download URL is not on api.github.com and must be accepted."""
    cross_host_url = "https://dgpproduction.blob.core.windows.net/sbom-reports/SENTINEL?sig=SECRETSIG"
    document = {"packages": [{"name": "package1", "versionInfo": "2.0"}]}
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(302, None)],
        fetch_headers=[{"location": cross_host_url}],
    )
    download_mock = mocker.patch(
        f"{STRATEGY_MODULE}.download_bounded",
        return_value=json.dumps(document).encode(),
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata[0].version == "2.0"
    assert generate.calls == 1
    assert fetch.calls == 1
    download_mock.assert_called_once_with(cross_host_url)
    strategy_sleep.assert_not_called()


def test_async_flow_pending_then_ready_retries_same_report(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Two 202 responses are followed by sleeps of 1 and 2 seconds, then the ready report is downloaded; generation is requested once."""
    document = {"packages": [{"name": "package1", "versionInfo": "2.0"}]}
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(202, None), (202, None), (302, None)],
        fetch_headers=[None, None, {"location": DOWNLOAD_URL}],
    )
    download_mock = mocker.patch(
        f"{STRATEGY_MODULE}.download_bounded",
        return_value=json.dumps(document).encode(),
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata[0].version == "2.0"
    # Generation happens exactly once; the same report is fetched three times
    assert generate.calls == 1
    assert fetch.calls == 3
    # Exact backoff: 1s after the first 202, 2s after the second
    strategy_sleep.assert_has_calls([mocker.call(1), mocker.call(2)])
    assert strategy_sleep.call_count == 2
    scm_sleep.assert_not_called()
    download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_async_flow_exhausts_pending_retries_after_six_fetches(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Six 202 responses exhaust the retry budget: six fetches, five sleeps (1, 2, 4, 8, 16 s)."""
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(202, None)],
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    # Recoverable failure: package kept with canonical origin, no SBOM data
    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert generate.calls == 1
    assert fetch.calls == 6
    strategy_sleep.assert_has_calls(
        [
            mocker.call(1),
            mocker.call(2),
            mocker.call(4),
            mocker.call(8),
            mocker.call(16),
        ]
    )
    assert strategy_sleep.call_count == 5
    scm_sleep.assert_not_called()
    download_mock.assert_not_called()
    errors = error_records(caplog, ValueError)
    assert errors == [
        "GitHub SBOM report for 'test_owner/test_repo' was not ready after 31 seconds"
    ]


def test_async_flow_mixed_pending_and_transient_sequence(
    mocker: pytest_mock.MockFixture,
) -> None:
    """A 202, then a transient 500 retried by the shared helper, then 302: the two retry layers stay separate."""
    document = {"packages": [{"name": "package1", "versionInfo": "2.0"}]}
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        # 202 (pending), 500 (transient, retried inside github_api_get_with_retry), 302 (ready)
        fetch_responses=[(202, None), (500, "Server Error"), (302, None)],
        fetch_headers=[None, None, {"location": DOWNLOAD_URL}],
    )
    download_mock = mocker.patch(
        f"{STRATEGY_MODULE}.download_bounded",
        return_value=json.dumps(document).encode(),
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata[0].version == "2.0"
    assert generate.calls == 1
    assert fetch.calls == 3
    # One pending sleep (1 s) from the strategy, one backoff sleep (2 s)
    # from the transient-retry helper
    strategy_sleep.assert_called_once_with(1)
    scm_sleep.assert_called_once_with(2.0)
    download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_async_flow_fetch_404_is_terminal_and_recoverable(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A 404 on fetch-report stops immediately with a distinct message (not the generate-404 repository message)."""
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(404, "Not Found")],
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert generate.calls == 1
    assert fetch.calls == 1
    strategy_sleep.assert_not_called()
    download_mock.assert_not_called()
    errors = error_records(caplog, ValueError)
    assert errors == [
        "GitHub SBOM report for 'test_owner/test_repo' expired or is unavailable"
    ]


def test_async_flow_fetch_401_raises_unauthorized_repository(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(401, "Unauthorized")],
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert fetch.calls == 1
    strategy_sleep.assert_not_called()
    download_mock.assert_not_called()
    errors = error_records(caplog, Exception)
    assert any("doesn't have enough permissions" in e for e in errors)


def test_async_flow_persistent_fetch_500_is_retried_then_fails(
    mocker: pytest_mock.MockFixture,
) -> None:
    """A persistent 500 on fetch is retried by the shared helper (3 attempts) before failing recoverably."""
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(500, "Server Error")],
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert generate.calls == 1
    assert fetch.calls == 3
    scm_sleep.assert_has_calls([mocker.call(2.0), mocker.call(4.0)])
    strategy_sleep.assert_not_called()
    download_mock.assert_not_called()


@pytest.mark.parametrize(
    "body",
    [{}, "", b"", []],
)
def test_async_flow_generation_201_without_sbom_url_is_rejected(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
    body: object,
) -> None:
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(201, body)], fetch_responses=[(302, None)]
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert fetch.calls == 0
    download_mock.assert_not_called()
    strategy_sleep.assert_not_called()
    errors = error_records(caplog, ValueError)
    assert errors == [
        "SBOM generation response for 'test_owner/test_repo' did not contain a sbom_url string"
    ]


@pytest.mark.parametrize(
    "sbom_url,expected_message",
    [
        (
            "http://api.github.com/repos/test_owner/test_repo/dependency-graph/sbom/fetch-report/rpt1",
            "sbom_url for 'test_owner/test_repo' must use https",
        ),
        (
            "https://evil.example.com/repos/test_owner/test_repo/dependency-graph/sbom/fetch-report/rpt1",
            "sbom_url for 'test_owner/test_repo' must be on api.github.com",
        ),
        (
            "https://user:secret@api.github.com/repos/test_owner/test_repo/dependency-graph/sbom/fetch-report/rpt1",
            "sbom_url for 'test_owner/test_repo' must not carry credentials",
        ),
        (
            "https://api.github.com:443/repos/test_owner/test_repo/dependency-graph/sbom/fetch-report/rpt1",
            "sbom_url for 'test_owner/test_repo' must not carry an explicit port",
        ),
        (
            "https://api.github.com/repos/test_owner/test_repo/dependency-graph/sbom/fetch-report/rpt1?sig=abc",
            "sbom_url for 'test_owner/test_repo' must not carry a query or fragment",
        ),
        (
            "https://api.github.com/repos/test_owner/test_repo/dependency-graph/sbom/fetch-report/rpt1#frag",
            "sbom_url for 'test_owner/test_repo' must not carry a query or fragment",
        ),
        (
            "https://api.github.com/some/other/path",
            "sbom_url for 'test_owner/test_repo' does not point at the dependency-graph SBOM fetch-report endpoint",
        ),
        (
            "https://api.github.com/repos/other_owner/test_repo/dependency-graph/sbom/fetch-report/rpt1",
            "sbom_url for 'test_owner/test_repo' points at a different repository",
        ),
        (
            "https://api.github.com/repos/test_owner/other_repo/dependency-graph/sbom/fetch-report/rpt1",
            "sbom_url for 'test_owner/test_repo' points at a different repository",
        ),
        (
            "https://api.github.com/repos/test_owner/test_repo/dependency-graph/sbom/fetch-report/rpt-1%21",
            "sbom_url for 'test_owner/test_repo' does not point at the dependency-graph SBOM fetch-report endpoint",
        ),
        (
            "https://api.github.com/repos/test_owner/test_repo/dependency-graph/sbom/fetch-report/..",
            "sbom_url for 'test_owner/test_repo' carries an invalid report id",
        ),
    ],
)
def test_async_flow_rejects_malformed_sbom_urls(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
    sbom_url: str,
    expected_message: str,
) -> None:
    """Each sbom_url rejection reason fails with its own redacted message."""
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": sbom_url})],
        fetch_responses=[(302, None)],
        sbom_url=sbom_url,
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert generate.calls == 1
    assert fetch.calls == 0
    download_mock.assert_not_called()
    strategy_sleep.assert_not_called()
    errors = error_records(caplog, ValueError)
    assert errors == [expected_message]


def test_async_flow_accepts_case_only_owner_repo_difference(
    mocker: pytest_mock.MockFixture,
) -> None:
    """GitHub owner/repo names are case-insensitive; a case-only mismatch must not fail."""
    case_url = (
        "https://api.github.com/repos/Test_Owner/Test_Repo"
        "/dependency-graph/sbom/fetch-report/rpt1"
    )
    document = {"packages": [{"name": "package1", "versionInfo": "2.0"}]}
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": case_url})],
        fetch_responses=[(302, None)],
        fetch_headers=[{"location": DOWNLOAD_URL}],
        sbom_url=case_url,
    )
    download_mock = mocker.patch(
        f"{STRATEGY_MODULE}.download_bounded",
        return_value=json.dumps(document).encode(),
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    assert updated_metadata[0].version == "2.0"
    assert generate.calls == 1
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)
    strategy_sleep.assert_not_called()


@pytest.mark.parametrize(
    "headers",
    [None, {}, {"content-type": "text/plain"}],
)
def test_async_flow_302_without_usable_location_is_rejected(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
    headers: dict[str, str] | None,
) -> None:
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(302, None)],
        fetch_headers=[headers],
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert fetch.calls == 1
    download_mock.assert_not_called()
    strategy_sleep.assert_not_called()
    errors = error_records(caplog, ValueError)
    assert errors == [
        "GitHub SBOM report for 'test_owner/test_repo' was ready but carried no usable Location header"
    ]


def test_async_flow_rejects_invalid_location_url(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(302, None)],
        fetch_headers=[{"location": "http://storage.invalid/report"}],
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert fetch.calls == 1
    download_mock.assert_not_called()
    errors = error_records(caplog, ValueError)
    assert errors == [
        "GitHub SBOM report download URL for 'test_owner/test_repo' is not a valid https URL"
    ]


@pytest.mark.parametrize(
    "download_content,expected_message",
    [
        (
            b"not json at all",
            "GitHub SBOM report for 'test_owner/test_repo' is not valid JSON",
        ),
        (
            b"\xff",
            "GitHub SBOM report for 'test_owner/test_repo' is not valid JSON",
        ),
        (
            b"[1, 2]",
            "Malformed GitHub SBOM report for 'test_owner/test_repo': the report is not a JSON object",
        ),
        (
            b'"a string"',
            "Malformed GitHub SBOM report for 'test_owner/test_repo': the report is not a JSON object",
        ),
        (
            b"{}",
            "Malformed GitHub SBOM report for 'test_owner/test_repo': 'packages' is missing or not a list",
        ),
        (
            b'{"packages": {"a": 1}}',
            "Malformed GitHub SBOM report for 'test_owner/test_repo': 'packages' is missing or not a list",
        ),
        (
            b'{"packages": ["bad"]}',
            "Malformed GitHub SBOM report for 'test_owner/test_repo': package entries must be JSON objects",
        ),
        (
            b'{"packages": [{"name": 42}]}',
            "Malformed GitHub SBOM report for 'test_owner/test_repo': package 'name' must be a string",
        ),
        (
            b'{"packages": [{"name": "x", "SPDXID": 5}]}',
            "Malformed GitHub SBOM report for 'test_owner/test_repo': package 'SPDXID' must be a string",
        ),
        (
            b'{"packages": [{"SPDXID": "SPDXRef-Other"}]}',
            "Malformed GitHub SBOM report for 'test_owner/test_repo': package entries must carry a 'name'",
        ),
        (
            b'{"packages": [{"name": null, "SPDXID": "SPDXRef-Other"}]}',
            "Malformed GitHub SBOM report for 'test_owner/test_repo': package entries must carry a 'name'",
        ),
    ],
)
def test_async_flow_rejects_malformed_downloaded_documents(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
    download_content: bytes,
    expected_message: str,
) -> None:
    """Malformed download payloads are rejected at the retrieval boundary with redacted messages."""
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch, download_mock = make_success_client(
        mocker, {}, download_content=download_content
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    # Recoverable: the package survives with its canonical origin
    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    assert fetch.calls == 1
    download_mock.assert_called_once_with(DOWNLOAD_URL)
    errors = error_records(caplog, ValueError)
    assert errors == [expected_message]


def test_async_flow_accepts_nameless_action_package(
    mocker: pytest_mock.MockFixture,
) -> None:
    """A package entry without a name is allowed when it is a skip-eligible CI action dependency."""
    document = {
        "packages": [
            {"SPDXID": "SPDXRef-githubactions-somthing-that-acts"},
            {"name": "package1", "versionInfo": "2.0"},
        ]
    }
    client, generate, fetch, download_mock = make_success_client(mocker, document)
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
        )
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    # The action entry is skipped; only package1 is enriched
    assert len(updated_metadata) == 1
    assert updated_metadata[0].name == "package1"
    assert updated_metadata[0].version == "2.0"
    download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_async_flow_download_failure_is_redacted(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A download failure (whose OSError message embeds the signed URL) is logged redacted, not verbatim."""
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(302, None)],
        fetch_headers=[{"location": DOWNLOAD_URL}],
    )
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")
    download_mock.side_effect = OSError(
        f"Download from {DOWNLOAD_URL} exceeds maximum size of 104857600 bytes"
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    strategy_sleep, _ = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    # Recoverable failure: package survives with canonical origin
    assert len(updated_metadata) == 1
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    download_mock.assert_called_once_with(DOWNLOAD_URL)
    # The redacted message is present; the signed URL never appears anywhere
    errors = error_records(caplog, OSError)
    assert errors == ["Failed to download GitHub SBOM report for test_owner/test_repo"]
    assert "SECRETSIG" not in caplog.text
    assert "storage.invalid" not in caplog.text
    assert "sig=" not in caplog.text


def test_async_flow_never_logs_report_url_or_id(
    mocker: pytest_mock.MockFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Across the full failure path (exhaustion), the sbom_url and report id never reach the logs."""
    caplog.set_level(logging.DEBUG, logger="dd_license_attribution")
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(202, None)],
    )
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)
    patch_sleeps(mocker)
    download_mock = mocker.patch(f"{STRATEGY_MODULE}.download_bounded")

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert len(updated_metadata) == 1
    download_mock.assert_not_called()
    assert "SENTINEL" not in caplog.text
    assert "SECRETSIG" not in caplog.text
    # The sbom_url path (with its report id) is never logged either
    assert "fetch-report" not in caplog.text


def test_async_flow_failure_on_one_package_does_not_block_the_next(
    mocker: pytest_mock.MockFixture,
) -> None:
    """A recoverable SBOM failure for the first package leaves the second package fully enriched."""
    document = {
        "packages": [
            {"name": "package2", "versionInfo": "3.0", "licenseDeclared": "MIT"}
        ]
    }
    client, generate, fetch = make_client(
        generate_responses=[(201, {"sbom_url": SBOM_URL})],
        fetch_responses=[(302, None)],
        fetch_headers=[{"location": DOWNLOAD_URL}],
    )
    # First package's generation fails persistently (3 retried attempts),
    # second package's generation succeeds
    generate.set_responses(
        [
            (500, "Server Error"),
            (500, "Server Error"),
            (500, "Server Error"),
            (201, {"sbom_url": SBOM_URL}),
        ]
    )
    download_mock = mocker.patch(
        f"{STRATEGY_MODULE}.download_bounded",
        return_value=json.dumps(document).encode(),
    )
    source_code_manager_mock = mocker.Mock()
    source_code_manager_mock.get_canonical_urls.side_effect = [
        (
            "https://github.com/test_owner/test_repo",
            "https://api.github.com/repos/test_owner/test_repo",
        ),
        (
            "https://github.com/test_owner/test_repo",
            "https://api.github.com/repos/test_owner/test_repo",
        ),
    ]
    parse_git_url_mock(mocker)
    strategy_sleep, scm_sleep = patch_sleeps(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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
        Metadata(
            name="package2",
            version=None,
            origin="test_purl",
            local_src_path=None,
            license=[],
            copyright=[],
        ),
    ]

    updated_metadata = strategy.augment_metadata(initial_metadata)

    # package1 survives unenriched (canonical origin only), package2 enriched
    by_name = {metadata.name: metadata for metadata in updated_metadata}
    assert by_name["package1"].version is None
    assert by_name["package1"].origin == "https://github.com/test_owner/test_repo"
    assert by_name["package2"].version == "3.0"
    assert by_name["package2"].license == ["MIT"]
    assert generate.calls == 4  # 3 attempts for package1 + 1 for package2
    assert fetch.calls == 1
    strategy_sleep.assert_not_called()
    scm_sleep.assert_has_calls([mocker.call(2.0), mocker.call(4.0)])
    download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_async_flow_null_named_action_package_survives_scope_filters(
    mocker: pytest_mock.MockFixture,
) -> None:
    """An action entry with an explicit "name": null must not crash any scope.

    json.dumps serializes None to null, so an entry carrying an explicit null
    name (as opposed to no name key at all) reaches the scope filters; the
    transitive filter must tolerate it instead of raising AttributeError
    outside the per-package recovery handler.
    """
    document = {
        "packages": [
            {"name": None, "SPDXID": "SPDXRef-githubactions-somthing-that-acts"},
            {
                "name": "package1",
                "versionInfo": "1.0",
                "licenseDeclared": "APACHE-2.0",
                "downloadLocation": "test_purl",
            },
        ]
    }
    for scope in (
        ProjectScope.ALL,
        ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES,
        ProjectScope.ONLY_ROOT_PROJECT,
    ):
        client, generate, fetch, download_mock = make_success_client(mocker, document)
        source_code_manager_mock = make_source_code_manager_mock(mocker)
        parse_git_url_mock(mocker)

        strategy = GitHubSbomMetadataCollectionStrategy(
            github_client=client,
            source_code_manager=source_code_manager_mock,
            project_scope=scope,
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

        # No crash in any scope; the null-named action entry is skipped and
        # package1 keeps its enrichment
        assert [metadata.name for metadata in updated_metadata] == ["package1"]
        assert updated_metadata[0].version == "1.0"
        assert generate.calls == 1
        assert fetch.calls == 1
        download_mock.assert_called_once_with(DOWNLOAD_URL)


def test_async_flow_nameless_action_package_survives_scope_filters(
    mocker: pytest_mock.MockFixture,
) -> None:
    """Nameless action entries must not crash the scope filters that run before the action-skip."""
    document = {
        "packages": [
            {"SPDXID": "SPDXRef-githubactions-somthing-that-acts"},
            {
                "name": "com.github.test_owner/test_repo",
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

    # ONLY_TRANSITIVE_DEPENDENCIES: the root-exclusion filter keeps the
    # nameless action entry, which then reaches the action-skip and is dropped
    client, generate, fetch, download_mock = make_success_client(mocker, document)
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    assert updated_metadata == [
        Metadata(
            name="package2",
            version="3.0",
            origin="test_purl_2",
            local_src_path=None,
            license=["APACHE-2.0"],
            copyright=[],
        )
    ]
    download_mock.assert_called_once_with(DOWNLOAD_URL)

    # ONLY_ROOT_PROJECT: the transitive filter drops the nameless action
    # entry (no metadata package name starts with "") before the action-skip;
    # the outcome is the same and no crash occurs
    client, generate, fetch, download_mock = make_success_client(mocker, document)
    source_code_manager_mock = make_source_code_manager_mock(mocker)
    parse_git_url_mock(mocker)

    strategy = GitHubSbomMetadataCollectionStrategy(
        github_client=client,
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

    # package1 matches no SBOM package after filtering, so it survives with
    # its canonical origin only; the run does not crash
    assert len(updated_metadata) == 1
    assert updated_metadata[0].name == "package1"
    assert updated_metadata[0].origin == "https://github.com/test_owner/test_repo"
    download_mock.assert_called_once_with(DOWNLOAD_URL)
