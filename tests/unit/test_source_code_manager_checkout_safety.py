# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import posixpath
from collections.abc import Iterator
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import Mock, call, patch

import pytest

from dd_license_attribution.artifact_management.source_code_manager import (
    NONINTERACTIVE_GIT_ENV,
    NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    SourceCodeManager,
)

MODULE = "dd_license_attribution.artifact_management."
ROOT = "cache/20261127_120000Z/owner-repo/main"
STAGE = ROOT + ".tmp-unique"
BACKUP = ROOT + ".old-unique"
URL = "https://github.com/owner/repo"


@pytest.fixture
def checkout_mocks() -> Iterator[dict[str, Mock]]:
    targets = {
        "exists": "artifact_manager.path_exists",
        "artifact_dirs": "artifact_manager.list_dir",
        "now": "artifact_manager.get_datetime_now",
        "dirs": "source_code_manager.list_dir",
        "cached": "source_code_manager.path_exists",
        "mkdir": "source_code_manager.create_dirs",
        "lookup": "source_code_manager.output_from_command",
        "run": "source_code_manager.run_command",
        "rename": "source_code_manager.rename_path",
        "remove": "source_code_manager.remove_tree",
        "is_dir": "source_code_manager.is_dir",
        "resolve": "source_code_manager.real_path",
        "unique": "source_code_manager.uuid.uuid4",
    }
    with ExitStack() as stack:
        mocks = {
            key: stack.enter_context(patch(MODULE + value))
            for key, value in targets.items()
        }
        mocks["exists"].return_value = True
        mocks["artifact_dirs"].return_value = []
        mocks["now"].return_value = datetime.fromisoformat("2026-11-27T12:00:00+00:00")
        mocks["dirs"].return_value = []
        mocks["cached"].return_value = False
        mocks["run"].return_value = 0
        mocks["is_dir"].return_value = True
        mocks["resolve"].side_effect = lambda path: posixpath.normpath("/" + path)
        mocks["unique"].return_value.hex = "unique"
        mocks["lookup"].return_value = "ref: refs/heads/main\tHEAD\n"
        yield mocks
        mocks["exists"].assert_called_once_with("cache")
        mocks["artifact_dirs"].assert_called_once_with("cache")
        mocks["now"].assert_called_once_with()


@pytest.mark.parametrize("failed", [False, True])
def test_clone_only_writes_and_cleans_its_own_staging_directory(
    checkout_mocks: dict[str, Mock], failed: bool
) -> None:
    checkout_mocks["run"].return_value = 1 if failed else 0
    scm = SourceCodeManager("cache", Mock())
    result = scm.get_code(URL, skip_canonical_lookup=True)
    assert (result is None) == failed
    checkout_mocks["mkdir"].assert_called_once_with(STAGE)
    checkout_mocks["run"].assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=main",
            URL,
            STAGE,
        ],
        env=NONINTERACTIVE_GIT_ENV,
        timeout=NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    )
    if failed:
        checkout_mocks["rename"].assert_not_called()
        checkout_mocks["remove"].assert_called_once_with(STAGE)
    else:
        assert result is not None
        assert result.local_full_path == ROOT
        checkout_mocks["rename"].assert_called_once_with(STAGE, ROOT)
        checkout_mocks["remove"].assert_not_called()


@pytest.mark.parametrize("valid_target", [False, True])
def test_concurrent_publication_accepts_only_a_verified_existing_checkout(
    checkout_mocks: dict[str, Mock], valid_target: bool
) -> None:
    checkout_mocks["is_dir"].side_effect = lambda path: path == STAGE or (
        valid_target and path == ROOT + "/.git"
    )
    checkout_mocks["rename"].side_effect = OSError("destination exists")
    scm = SourceCodeManager("cache", Mock())
    assert scm._publish_staging_checkout(STAGE, ROOT, False) == valid_target
    checkout_mocks["rename"].assert_called_once_with(STAGE, ROOT)
    checkout_mocks["remove"].assert_called_once_with(STAGE)


@pytest.mark.parametrize(
    "stage_exists,valid_target", [(False, False), (False, True), (True, False)]
)
def test_publication_checks_missing_staging_and_normal_success(
    checkout_mocks: dict[str, Mock], stage_exists: bool, valid_target: bool
) -> None:
    checkout_mocks["is_dir"].side_effect = lambda path: (
        stage_exists and path == STAGE
    ) or (valid_target and path == ROOT + "/.git")
    scm = SourceCodeManager("cache", Mock())
    assert scm._publish_staging_checkout(STAGE, ROOT, False) == (
        stage_exists or valid_target
    )
    if stage_exists:
        checkout_mocks["rename"].assert_called_once_with(STAGE, ROOT)
    else:
        checkout_mocks["rename"].assert_not_called()
    checkout_mocks["remove"].assert_not_called()


@pytest.mark.parametrize("failure", ["none", "backup", "publish", "rollback"])
def test_forced_update_preserves_the_old_checkout_on_failure(
    checkout_mocks: dict[str, Mock], failure: str
) -> None:
    effects = {
        "none": [None, None],
        "backup": [OSError("busy")],
        "publish": [None, OSError("publish failed"), None],
        "rollback": [None, OSError("publish failed"), OSError("rollback failed")],
    }
    checkout_mocks["rename"].side_effect = effects[failure]
    checkout_mocks["is_dir"].side_effect = lambda path: path in {
        STAGE,
        ROOT,
        BACKUP,
        ROOT + "/.git",
    }
    scm = SourceCodeManager("cache", Mock())
    assert scm._publish_staging_checkout(STAGE, ROOT, True) == (failure == "none")
    expected = [call(ROOT, BACKUP)]
    if failure != "backup":
        expected.append(call(STAGE, ROOT))
    if failure in ("publish", "rollback"):
        expected.append(call(BACKUP, ROOT))
    assert checkout_mocks["rename"].call_args_list == expected
    checkout_mocks["remove"].assert_called_once_with(
        BACKUP if failure == "none" else STAGE
    )


@pytest.mark.parametrize("escaping", ["checkout", "staging", "subdirectory"])
def test_escaping_resolved_paths_never_produce_a_checkout(
    checkout_mocks: dict[str, Mock], escaping: str
) -> None:
    def resolve(path: str) -> str:
        if (
            (escaping == "checkout" and path == ROOT)
            or (escaping == "staging" and path == STAGE)
            or (escaping == "subdirectory" and path == ROOT + "/pkg")
        ):
            return "/outside"
        return posixpath.normpath("/" + path)

    checkout_mocks["resolve"].side_effect = resolve
    if escaping == "subdirectory":
        checkout_mocks["lookup"].return_value = "1234\trefs/heads/main\n"
    scm = SourceCodeManager("cache", Mock())
    result = scm.get_code(
        URL + ("/tree/main/pkg" if escaping == "subdirectory" else ""),
        skip_canonical_lookup=True,
    )
    assert result is None
    if escaping != "subdirectory":
        checkout_mocks["mkdir"].assert_not_called()
        checkout_mocks["rename"].assert_not_called()
        checkout_mocks["run"].assert_not_called()
    checkout_mocks["remove"].assert_not_called()


@pytest.mark.parametrize(
    "valid_git,valid_path", [(False, True), (True, False), (True, True)]
)
def test_cache_hit_requires_git_checkout_and_valid_scoped_directory(
    checkout_mocks: dict[str, Mock], valid_git: bool, valid_path: bool
) -> None:
    checkout_mocks["dirs"].return_value = ["20261127_120000Z"]
    checkout_mocks["cached"].return_value = True
    checkout_mocks["lookup"].return_value = "1234\trefs/heads/main\n"
    checkout_mocks["is_dir"].side_effect = lambda path: (
        valid_git if path.endswith("/.git") else valid_path
    )
    scm = SourceCodeManager("cache", Mock())
    result = scm.get_code(URL + "/tree/main/pkg", skip_canonical_lookup=True)
    if valid_git and valid_path:
        assert result is not None
        assert result.local_full_path == ROOT + "/pkg"
        checkout_mocks["run"].assert_not_called()
        checkout_mocks["mkdir"].assert_not_called()
    elif valid_git:
        assert result is None
        checkout_mocks["run"].assert_not_called()
    else:
        checkout_mocks["run"].assert_called_once()
        checkout_mocks["mkdir"].assert_called_once_with(STAGE)


@pytest.mark.parametrize(
    "path,inside_cache,inside_checkout",
    [
        ("cache/repo", True, True),
        ("cache/repo/src", True, True),
        ("cache-other/repo", False, False),
        ("cache/repo-other", True, False),
        ("cache/../outside", False, False),
        ("cache", False, False),
    ],
)
def test_containment_requires_a_directory_boundary(
    checkout_mocks: dict[str, Mock],
    path: str,
    inside_cache: bool,
    inside_checkout: bool,
) -> None:
    scm = SourceCodeManager("cache", Mock())
    assert scm._is_within_cache_dir(path) == inside_cache
    assert scm._is_within_checkout_root("cache/repo", path) == inside_checkout
    checkout_mocks["resolve"].assert_has_calls(
        [call("cache"), call(path), call("cache/repo"), call(path)]
    )
