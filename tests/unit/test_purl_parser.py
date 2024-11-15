from ospo_tools.metadata_collector.purl_parser import PurlParser

import pytest


@pytest.mark.parametrize(
    "purl",
    [
        (None),
        ("gitlab.com/user/repo@3.0.0"),
    ],
)
def test_get_github_owner_and_repo_from_no_github_purls_is_none(purl):
    purl_parser = PurlParser()
    owner, repo = purl_parser.get_github_owner_and_repo(purl)
    assert owner is None
    assert repo is None


@pytest.mark.parametrize(
    "purl, expected_owner, expected_repo",
    [
        ("http://github.com/user/repo@1.0.0", "user", "repo"),
        ("http://github.com/user/repo", "user", "repo"),
        ("github.com/user/repo@2.0.0", "user", "repo"),
        ("github.com/user/repo", "user", "repo"),
    ],
)
def test_get_github_owner_and_repo_with_different_purl_formats(
    purl, expected_owner, expected_repo
):
    purl_parser = PurlParser()
    owner, repo = purl_parser.get_github_owner_and_repo(purl)
    assert owner == expected_owner
    assert repo == expected_repo


@pytest.mark.parametrize(
    "purl",
    [
        (None),
        ("github.com/user/repo@3.0.0"),
    ],
)
def test_get_gitlab_owner_and_repo_from_no_gitlab_purls_is_none(purl):
    purl_parser = PurlParser()
    owner, repo = purl_parser.get_gitlab_owner_and_repo(purl)
    assert owner is None
    assert repo is None


@pytest.mark.parametrize(
    "purl, expected_owner, expected_repo",
    [
        ("http://gitlab.com/user/repo@1.0.0", "user", "repo"),
        ("http://gitlab.com/user/repo", "user", "repo"),
        ("gitlab.com/user/repo@2.0.0", "user", "repo"),
        ("gitlab.com/user/repo", "user", "repo"),
    ],
)
def test_get_gitlab_owner_and_repo_with_different_purl_formats(
    purl, expected_owner, expected_repo
):
    purl_parser = PurlParser()
    owner, repo = purl_parser.get_gitlab_owner_and_repo(purl)
    assert owner == expected_owner
    assert repo == expected_repo
