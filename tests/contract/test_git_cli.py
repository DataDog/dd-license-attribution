# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import os
import shutil
import subprocess
from pathlib import Path

import pytest

_ISOLATED_GIT_ENV = {
    **os.environ,
    "GIT_CONFIG_GLOBAL": os.devnull,
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_AUTHOR_NAME": "test",
    "GIT_AUTHOR_EMAIL": "test@example.com",
    "GIT_COMMITTER_NAME": "test",
    "GIT_COMMITTER_EMAIL": "test@example.com",
}


def _git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    return subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=env or _ISOLATED_GIT_ENV,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


@pytest.fixture(params=["lightweight", "annotated"])
def repo_with_same_named_branch_and_tag(
    request: pytest.FixtureRequest, tmp_path: Path
) -> tuple[str, str, str]:
    """Return (repo_url, tag_commit, branch_commit) for a repo where the
    branch and the tag `v1.0` point at different commits."""
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(["init", "--quiet"], origin)
    _git(["commit", "--quiet", "--allow-empty", "-m", "tagged"], origin)
    if request.param == "annotated":
        _git(["tag", "-a", "v1.0", "-m", "v1.0"], origin)
    else:
        _git(["tag", "v1.0"], origin)
    tag_commit = _git(["rev-parse", "HEAD"], origin)
    _git(["commit", "--quiet", "--allow-empty", "-m", "branch"], origin)
    _git(["branch", "v1.0"], origin)
    branch_commit = _git(["rev-parse", "HEAD"], origin)
    assert tag_commit != branch_commit
    return origin.as_uri(), tag_commit, branch_commit


def _checkout_tag(repo_url: str, dest: Path, env: dict[str, str] | None = None) -> None:
    """The command sequence SourceCodeManager uses for mirror tag targets."""
    dest.mkdir()
    _git(["init", "--quiet"], dest, env)
    _git(["remote", "add", "origin", repo_url], dest, env)
    _git(
        ["fetch", "--depth", "1", "origin", "refs/tags/v1.0:refs/tags/v1.0"],
        dest,
        env,
    )
    _git(["-c", "advice.detachedHead=False", "checkout", "FETCH_HEAD"], dest, env)


class TestGitCliContract:
    def test_clone_branch_prefers_branch_over_same_named_tag(
        self,
        repo_with_same_named_branch_and_tag: tuple[str, str, str],
        tmp_path: Path,
    ) -> None:
        repo_url, _, branch_commit = repo_with_same_named_branch_and_tag
        _git(
            ["clone", "--quiet", "--depth", "1", "--branch=v1.0", repo_url, "dest"],
            tmp_path,
        )

        assert _git(["rev-parse", "HEAD"], tmp_path / "dest") == branch_commit

    def test_fetch_qualified_tag_ref_selects_tag_over_same_named_branch(
        self,
        repo_with_same_named_branch_and_tag: tuple[str, str, str],
        tmp_path: Path,
    ) -> None:
        repo_url, tag_commit, _ = repo_with_same_named_branch_and_tag
        dest = tmp_path / "dest"
        _checkout_tag(repo_url, dest)

        assert _git(["rev-parse", "HEAD"], dest) == tag_commit
        # Tag-derived versioning needs the local tag ref.
        assert _git(["describe", "--tags", "--exact-match", "HEAD"], dest) == "v1.0"

    @pytest.mark.skipif(shutil.which("git-lfs") is None, reason="git-lfs missing")
    def test_tag_checkout_smudges_lfs_files_from_origin(self, tmp_path: Path) -> None:
        global_config = tmp_path / "gitconfig"
        global_config.touch()
        env = {**_ISOLATED_GIT_ENV, "GIT_CONFIG_GLOBAL": str(global_config)}
        _git(["lfs", "install"], tmp_path, env)
        src = tmp_path / "src"
        src.mkdir()
        _git(["init", "--quiet"], src, env)
        _git(["lfs", "track", "LICENSE"], src, env)
        (src / "LICENSE").write_text("MIT License\n")
        _git(["add", ".gitattributes", "LICENSE"], src, env)
        _git(["commit", "--quiet", "-m", "lfs"], src, env)
        _git(["tag", "v1.0"], src, env)
        bare = tmp_path / "origin.git"
        _git(["init", "--quiet", "--bare", str(bare)], tmp_path, env)
        _git(["push", "--quiet", bare.as_uri(), "refs/tags/v1.0"], src, env)

        dest = tmp_path / "dest"
        _checkout_tag(bare.as_uri(), dest, env)

        # Without an `origin` remote, Git LFS cannot resolve where to download
        # from and the checkout's smudge filter fails.
        assert (dest / "LICENSE").read_text() == "MIT License\n"
