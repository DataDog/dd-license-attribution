from ospo_tools.metadata_collector.purl_parser import PurlParser

import pytest


@pytest.mark.parametrize(
    "purl",
    [
        (None),
        ("gitlab.com/user/repo@3.0.0"),
    ],
)
def test_get_github_owner_repo_path_from_no_github_purls_is_none(purl):
    purl_parser = PurlParser()
    owner, repo, path = purl_parser.get_github_owner_repo_path(purl)
    assert owner is None
    assert repo is None
    assert path is None


@pytest.mark.parametrize(
    "purl, expected_owner, expected_repo, expected_path",
    [
        ("http://github.com/user/repo@1.0.0", "user", "repo", ""),
        ("http://github.com/user/repo", "user", "repo", ""),
        ("github.com/aws/aws-sdk-go-v2/config", "aws", "aws-sdk-go-v2", "/config"),
        (
            "github.com/aws/aws-sdk-go-v2/feature/ec2/imds",
            "aws",
            "aws-sdk-go-v2",
            "/feature/ec2/imds",
        ),
        ("github.com/user/repo@2.0.0", "user", "repo", ""),
        ("github.com/user/repo", "user", "repo", ""),
    ],
)
def test_get_github_owner_repo_path_with_different_purl_formats(
    purl, expected_owner, expected_repo, expected_path
):
    purl_parser = PurlParser()
    owner, repo, path = purl_parser.get_github_owner_repo_path(purl)
    assert owner == expected_owner
    assert repo == expected_repo
    assert path == expected_path


@pytest.mark.parametrize(
    "purl",
    [
        (None),
        ("github.com/user/repo@3.0.0"),
    ],
)
def test_get_gitlab_owner_repo_path_from_no_gitlab_purls_is_none(purl):
    purl_parser = PurlParser()
    owner, repo, path = purl_parser.get_gitlab_owner_repo_path(purl)
    assert owner is None
    assert repo is None
    assert path is None


@pytest.mark.parametrize(
    "purl, expected_owner, expected_repo, expected_path",
    [
        ("http://gitlab.com/user/repo@1.0.0", "user", "repo", ""),
        ("http://gitlab.com/user/repo", "user", "repo", ""),
        ("http://gitlab.com/user/repo/folder", "user", "repo", "/folder"),
        ("gitlab.com/user/repo@2.0.0", "user", "repo", ""),
        ("gitlab.com/user/repo", "user", "repo", ""),
    ],
)
def test_get_gitlab_owner_repo_path_with_different_purl_formats(
    purl, expected_owner, expected_repo, expected_path
):
    purl_parser = PurlParser()
    owner, repo, path = purl_parser.get_gitlab_owner_repo_path(purl)
    assert owner == expected_owner
    assert repo == expected_repo
    assert path == expected_path
