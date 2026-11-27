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
from unittest.mock import Mock, patch

import pytest

from dd_license_attribution.adaptors.os import output_from_command, rename_path
from dd_license_attribution.artifact_management.source_code_manager import (
    MirrorSpec,
    RefType,
    SourceCodeManager,
)

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
    dest.mkdir(exist_ok=True)
    _git(["init", "--quiet"], dest, env)
    _git(["config", "remote.origin.url", repo_url], dest, env)
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

    def test_tag_checkout_is_retryable_in_same_dir_after_failed_fetch(
        self,
        repo_with_same_named_branch_and_tag: tuple[str, str, str],
        tmp_path: Path,
    ) -> None:
        repo_url, tag_commit, _ = repo_with_same_named_branch_and_tag
        dest = tmp_path / "dest"
        with pytest.raises(subprocess.CalledProcessError):
            _checkout_tag((tmp_path / "missing.git").as_uri(), dest)

        _checkout_tag(repo_url, dest)

        assert _git(["rev-parse", "HEAD"], dest) == tag_commit
        assert _git(["remote", "get-url", "origin"], dest) == repo_url

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


@pytest.mark.parametrize("branch", ["main", "a" * 240])
def test_forced_refresh_preserves_readers_and_updates_future_cache_lookups(
    tmp_path: Path, branch: str
) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(["init", "--quiet", f"--initial-branch={branch}"], origin)
    (origin / "LICENSE").write_text("old snapshot")
    _git(["add", "LICENSE"], origin)
    _git(["commit", "--quiet", "-m", "old"], origin)
    cache = tmp_path / "cache"
    cache.mkdir()
    url = "https://github.com/example/repo"
    mirrors = [MirrorSpec(url, origin.as_uri())]
    scm = SourceCodeManager(str(cache), Mock(), mirrors=mirrors)

    def lookup(
        args: list[str], env: dict[str, str] | None = None, timeout: int | None = None
    ) -> str:
        if url in args:
            return f"ref: refs/heads/{branch}\tHEAD\n"
        return output_from_command(args, env=env, timeout=timeout)

    with patch(
        "dd_license_attribution.artifact_management.source_code_manager.output_from_command",
        side_effect=lookup,
    ):
        old = scm.get_code(url, skip_canonical_lookup=True)
        assert old is not None
        old_root = Path(old.local_root_path)
        _git(["commit", "--quiet", "--allow-empty", "-m", "new revision"], origin)
        (origin / "LICENSE").write_text("new snapshot")
        _git(["add", "LICENSE"], origin)
        _git(["commit", "--quiet", "-m", "new contents"], origin)

        def observe_publication(source: str, destination: str) -> None:
            assert (old_root / "LICENSE").read_text() == "old snapshot"
            rename_path(source, destination)
            assert (old_root / "LICENSE").read_text() == "old snapshot"

        with patch(
            "dd_license_attribution.artifact_management.source_code_manager.rename_path",
            side_effect=observe_publication,
        ) as publish:
            fresh = scm.get_code(url, force_update=True, skip_canonical_lookup=True)
            publish.assert_called()
        assert fresh is not None
        assert fresh.local_root_path != old.local_root_path
        assert (old_root / "LICENSE").read_text() == "old snapshot"
        assert (Path(fresh.local_root_path) / "LICENSE").read_text() == "new snapshot"
        assert scm.get_code(url, skip_canonical_lookup=True) == fresh
        another_reader = SourceCodeManager(str(cache), Mock(), mirrors=mirrors)
        assert another_reader.get_code(url, skip_canonical_lookup=True) == fresh

        (origin / "LICENSE").write_text("failed refresh")
        _git(["add", "LICENSE"], origin)
        _git(["commit", "--quiet", "-m", "unpublished"], origin)
        with patch(
            "dd_license_attribution.artifact_management.source_code_manager.replace_path",
            side_effect=OSError("pointer publication failed"),
        ) as replace:
            assert (
                scm.get_code(url, force_update=True, skip_canonical_lookup=True) is None
            )
            replace.assert_called_once()
        assert scm.get_code(url, skip_canonical_lookup=True) == fresh
        assert (old_root / "LICENSE").read_text() == "old snapshot"
        assert (Path(fresh.local_root_path) / "LICENSE").read_text() == "new snapshot"


@pytest.mark.parametrize("source_type", [RefType.BRANCH, RefType.TAG])
def test_explicit_mapping_beats_opposite_type_ref_in_real_mirror(
    tmp_path: Path, source_type: RefType
) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(["init", "--quiet", "--initial-branch=review"], origin)
    _git(["commit", "--quiet", "--allow-empty", "-m", "unmapped"], origin)
    old_commit = _git(["rev-parse", "HEAD"], origin)
    if source_type == RefType.BRANCH:
        _git(["tag", "main"], origin)
    else:
        _git(["branch", "main"], origin)
    _git(["commit", "--quiet", "--allow-empty", "-m", "mapped"], origin)
    mapped_commit = _git(["rev-parse", "HEAD"], origin)
    assert old_commit != mapped_commit

    cache = tmp_path / "cache"
    cache.mkdir()
    repository_url = "https://github.com/example/repo"
    mirror = MirrorSpec(
        repository_url,
        origin.as_uri(),
        {(source_type, "main"): (RefType.BRANCH, "review")},
    )
    scm = SourceCodeManager(str(cache), Mock(), mirrors=[mirror])

    def lookup(
        args: list[str], env: dict[str, str] | None = None, timeout: int | None = None
    ) -> str:
        if args[3] == repository_url:
            raise OSError("original repository unavailable")
        return output_from_command(args, env=env, timeout=timeout)

    with patch(
        "dd_license_attribution.artifact_management.source_code_manager.output_from_command",
        side_effect=lookup,
    ) as lookup_mock:
        result = scm.get_code(f"{repository_url}/tree/main", skip_canonical_lookup=True)
        lookup_mock.assert_any_call(
            ["git", "ls-remote", "--", origin.as_uri(), "refs/heads/review"],
            env={"GIT_TERMINAL_PROMPT": "0"},
            timeout=30,
        )
    assert result is not None
    assert result.branch == "main"
    root = Path(result.local_root_path)
    assert _git(["branch", "--show-current"], root) == "review"
    assert _git(["rev-parse", "HEAD"], root) == mapped_commit


@pytest.mark.parametrize("target_type", [RefType.BRANCH, RefType.TAG])
@pytest.mark.parametrize("annotated", [False, True])
def test_mapped_target_namespace_skips_a_wrong_type_mirror(
    tmp_path: Path, target_type: RefType, annotated: bool
) -> None:
    mirrors: list[Path] = []
    expected_commit = ""
    for name in ["wrong", "healthy"]:
        origin = tmp_path / name
        origin.mkdir()
        _git(["init", "--quiet", "--initial-branch=work"], origin)
        _git(["commit", "--quiet", "--allow-empty", "-m", "opposite type"], origin)
        if target_type == RefType.TAG:
            _git(["branch", "stable"], origin)
        else:
            _git(["tag", "stable"], origin)
        if name == "healthy":
            _git(["commit", "--quiet", "--allow-empty", "-m", "requested type"], origin)
            expected_commit = _git(["rev-parse", "HEAD"], origin)
            if target_type == RefType.BRANCH:
                _git(["branch", "stable"], origin)
            elif annotated:
                _git(["tag", "-a", "stable", "-m", "stable"], origin)
            else:
                _git(["tag", "stable"], origin)
        mirrors.append(origin)
    cache = tmp_path / "cache"
    cache.mkdir()
    url = "https://github.com/example/repo"
    mapping = {(RefType.BRANCH, "main"): (target_type, "stable")}
    scm = SourceCodeManager(
        str(cache),
        Mock(),
        mirrors=[MirrorSpec(url, path.as_uri(), mapping) for path in mirrors],
    )

    def lookup(
        args: list[str], env: dict[str, str] | None = None, timeout: int | None = None
    ) -> str:
        if args[3] == url:
            raise OSError("original repository unavailable")
        return output_from_command(args, env=env, timeout=timeout)

    with patch(
        "dd_license_attribution.artifact_management.source_code_manager.output_from_command",
        side_effect=lookup,
    ) as advertised:
        result = scm.get_code(url + "/tree/main", skip_canonical_lookup=True)
        namespace = "heads" if target_type == RefType.BRANCH else "tags"
        for mirror in mirrors:
            advertised.assert_any_call(
                ["git", "ls-remote", "--", mirror.as_uri(), f"refs/{namespace}/stable"],
                env={"GIT_TERMINAL_PROMPT": "0"},
                timeout=30,
            )
    assert result is not None
    root = Path(result.local_root_path)
    assert _git(["remote", "get-url", "origin"], root) == mirrors[1].as_uri()
    assert _git(["rev-parse", "HEAD"], root) == expected_commit


def test_provisional_commit_fetch_continues_to_a_healthy_mirror(tmp_path: Path) -> None:
    mirrors: list[Path] = []
    requested = ""
    for name in ["missing", "healthy"]:
        origin = tmp_path / name
        origin.mkdir()
        _git(["init", "--quiet", "--initial-branch=main"], origin)
        _git(["commit", "--quiet", "--allow-empty", "-m", name], origin)
        if name == "healthy":
            requested = _git(["rev-parse", "HEAD"], origin)
        mirrors.append(origin)
    cache = tmp_path / "cache"
    cache.mkdir()
    url = "https://github.com/example/repo"
    scm = SourceCodeManager(
        str(cache), Mock(), mirrors=[MirrorSpec(url, path.as_uri()) for path in mirrors]
    )

    def lookup(
        args: list[str], env: dict[str, str] | None = None, timeout: int | None = None
    ) -> str:
        if args[3] == url:
            raise OSError("original lookup timed out")
        return output_from_command(args, env=env, timeout=timeout)

    with patch(
        "dd_license_attribution.artifact_management.source_code_manager.output_from_command",
        side_effect=lookup,
    ) as lookup_mock:
        result = scm.get_code(f"{url}/tree/{requested}", skip_canonical_lookup=True)
        lookup_mock.assert_any_call(
            ["git", "ls-remote", "--", url, requested],
            env={"GIT_TERMINAL_PROMPT": "0"},
            timeout=30,
        )
    assert result is not None
    assert result.branch == requested
    assert _git(["rev-parse", "HEAD"], Path(result.local_root_path)) == requested
    assert (
        _git(["remote", "get-url", "origin"], Path(result.local_root_path))
        == mirrors[1].as_uri()
    )


@pytest.mark.parametrize("target_type", [RefType.BRANCH, RefType.TAG])
def test_sha_checkout_retry_does_not_publish_partial_checkout_files(
    tmp_path: Path, target_type: RefType
) -> None:
    first = tmp_path / "broken-filter"
    healthy = tmp_path / "healthy"
    for origin in [first, healthy]:
        origin.mkdir()
        _git(["init", "--quiet", "--initial-branch=main"], origin)
    (first / ".gitattributes").write_text("b_fail filter=broken\n")
    (first / "a_extra").write_text("from failed checkout")
    (first / "b_fail").write_text("smudge fails")
    _git(["add", "."], first)
    _git(["commit", "--quiet", "-m", "broken checkout"], first)
    requested = _git(["rev-parse", "HEAD"], first)
    (healthy / "ok").write_text("healthy checkout")
    (healthy / ".gitignore").write_text("a_extra\n")
    _git(["add", "."], healthy)
    _git(["commit", "--quiet", "-m", "healthy checkout"], healthy)
    expected = _git(["rev-parse", "HEAD"], healthy)
    target = "main"
    if target_type == RefType.TAG:
        target = "stable"
        _git(["tag", target], healthy)
    cache = tmp_path / "cache"
    cache.mkdir()
    url = "https://github.com/example/repo"
    mapping = {(RefType.COMMIT, requested): (target_type, target)}
    scm = SourceCodeManager(
        str(cache),
        Mock(),
        mirrors=[
            MirrorSpec(url, first.as_uri()),
            MirrorSpec(url, healthy.as_uri(), mapping),
        ],
    )

    def lookup(
        args: list[str],
        env: dict[str, str] | None = None,
        timeout: int | None = None,
        cwd: str | None = None,
    ) -> str:
        if args[3] == url:
            raise OSError("original lookup timed out")
        return output_from_command(args, cwd=cwd, env=env, timeout=timeout)

    filter_env = {
        "GIT_CONFIG_COUNT": "3",
        "GIT_CONFIG_KEY_0": "filter.broken.required",
        "GIT_CONFIG_VALUE_0": "true",
        "GIT_CONFIG_KEY_1": "filter.broken.smudge",
        "GIT_CONFIG_VALUE_1": "false",
        "GIT_CONFIG_KEY_2": "init.defaultBranch",
        "GIT_CONFIG_VALUE_2": "main",
    }
    with (
        patch.dict(os.environ, filter_env),
        patch(
            "dd_license_attribution.artifact_management.source_code_manager.output_from_command",
            side_effect=lookup,
        ) as advertised,
    ):
        result = scm.get_code(url + "/tree/" + requested, skip_canonical_lookup=True)
        advertised.assert_called()
    assert result is not None
    root = Path(result.local_root_path)
    assert _git(["rev-parse", "HEAD"], root) == expected
    assert (root / "ok").read_text() == "healthy checkout"
    assert not (root / "a_extra").exists()
    assert not (root / ".gitattributes").exists()

    fresh = SourceCodeManager(str(cache), Mock(), mirrors=scm.mirrors)
    with (
        patch(
            "dd_license_attribution.artifact_management.source_code_manager.output_from_command",
            side_effect=lookup,
        ) as cached_lookup,
        patch(
            "dd_license_attribution.artifact_management.source_code_manager.run_command",
            return_value=1,
        ) as unavailable_checkout,
    ):
        assert (
            fresh.get_code(url + "/tree/" + requested, skip_canonical_lookup=True)
            == result
        )
        unavailable_checkout.assert_not_called()
        cached_lookup.assert_any_call(
            ["git", "rev-parse", "--verify", "HEAD"],
            cwd=str(root),
            env={"GIT_TERMINAL_PROMPT": "0"},
            timeout=30,
        )


@pytest.mark.parametrize("ref_type", [RefType.BRANCH, RefType.TAG])
def test_at_sign_ref_is_retrievable(tmp_path: Path, ref_type: RefType) -> None:
    origin = tmp_path / "origin"
    origin.mkdir()
    _git(["init", "--quiet"], origin)
    _git(["commit", "--quiet", "--allow-empty", "-m", "at sign"], origin)
    commit = _git(["rev-parse", "HEAD"], origin)
    _git(["branch" if ref_type == RefType.BRANCH else "tag", "@"], origin)
    cache = tmp_path / "cache"
    cache.mkdir()
    url = "https://github.com/example/repo"
    scm = SourceCodeManager(
        str(cache), Mock(), mirrors=[MirrorSpec(url, origin.as_uri())]
    )
    namespace = "heads" if ref_type == RefType.BRANCH else "tags"
    with patch(
        "dd_license_attribution.artifact_management.source_code_manager.output_from_command",
        return_value=f"{commit}\trefs/{namespace}/@\n",
    ) as advertised:
        result = scm.get_code(url + "/tree/@", skip_canonical_lookup=True)
        advertised.assert_called_once_with(
            ["git", "ls-remote", "--", url, "@"],
            env={"GIT_TERMINAL_PROMPT": "0"},
            timeout=30,
        )
    assert result is not None
    assert _git(["rev-parse", "HEAD"], Path(result.local_root_path)) == commit
