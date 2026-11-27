# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import json
import posixpath
from collections.abc import Iterator
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import Mock, call, patch

import pytest

from dd_license_attribution.artifact_management.source_code_manager import (
    NONINTERACTIVE_GIT_ENV,
    NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
    MirrorSpec,
    RefType,
    SourceCodeManager,
    extract_ref,
)

REPOSITORY = "https://github.com/owner/repo"
SHA = "1234567890abcdef1234567890abcdef12345678"
GENERATION = "cache/20261127_120000Z/owner-repo/.checkout-" + "a" * 32
STAGE = "cache/20261127_120000Z/owner-repo/.checkout-staging-" + "a" * 32
MODULE = "dd_license_attribution.artifact_management."
GIT_KWARGS = {
    "env": NONINTERACTIVE_GIT_ENV,
    "timeout": NONINTERACTIVE_GIT_TIMEOUT_SECONDS,
}


@pytest.fixture
def git_mocks() -> Iterator[dict[str, Mock]]:
    targets = {
        "exists": "artifact_manager.path_exists",
        "artifact_dirs": "artifact_manager.list_dir",
        "now": "artifact_manager.get_datetime_now",
        "cache_dirs": "source_code_manager.list_dir",
        "cached": "source_code_manager.path_exists",
        "mkdir": "source_code_manager.create_dirs",
        "lookup": "source_code_manager.output_from_command",
        "run": "source_code_manager.run_command",
        "is_dir": "source_code_manager.is_dir",
        "is_file": "source_code_manager.is_file",
        "read": "source_code_manager.open_file",
        "write": "source_code_manager.write_file",
        "replace": "source_code_manager.replace_path",
        "rename": "source_code_manager.rename_path",
        "unlink": "source_code_manager.remove_file",
        "remove": "source_code_manager.remove_tree",
        "real": "source_code_manager.real_path",
        "unique": "source_code_manager.uuid.uuid4",
    }
    with ExitStack() as stack:
        mocks = {
            name: stack.enter_context(patch(MODULE + target))
            for name, target in targets.items()
        }
        mocks["exists"].return_value = True
        mocks["artifact_dirs"].return_value = []
        mocks["now"].return_value = datetime.fromisoformat("2026-11-27T12:00:00+00:00")
        mocks["cache_dirs"].return_value = []
        mocks["cached"].return_value = False
        mocks["run"].return_value = 0
        mocks["is_dir"].return_value = True
        mocks["is_file"].return_value = False
        mocks["read"].return_value = ".checkout-" + "a" * 32
        mocks["unique"].return_value.hex = "a" * 32
        mocks["real"].side_effect = lambda path: posixpath.normpath("/" + path)
        yield mocks
        mocks["exists"].assert_called_once_with("cache")
        mocks["artifact_dirs"].assert_called_once_with("cache")
        mocks["now"].assert_called_once_with()
        if not mocks["cache_dirs"].return_value:
            mocks["cached"].assert_not_called()


@pytest.mark.parametrize("advertised_type", ["heads", "tags", "tags-peeled"])
@pytest.mark.parametrize(
    "url_path", ["tree/release/v2/pkg", "blob/release/v2/pkg/Cargo.toml"]
)
def test_checkout_preserves_explicit_ref_type(
    git_mocks: dict[str, Mock], advertised_type: str, url_path: str
) -> None:
    ref_type = "heads" if advertised_type == "heads" else "tags"
    suffix = "^{}" if advertised_type == "tags-peeled" else ""
    git_mocks["lookup"].return_value = (
        f"{SHA}\trefs/heads/release\n{SHA}\trefs/{ref_type}/release/v2{suffix}\n"
    )
    scm = SourceCodeManager("cache", Mock())
    result = scm.get_code(f"{REPOSITORY}/{url_path}", skip_canonical_lookup=True)
    assert result is not None
    assert result.branch == "release/v2"
    assert result.local_root_path == GENERATION
    assert result.local_full_path == result.local_root_path + "/pkg"
    lookup = [
        "git",
        "ls-remote",
        "--",
        REPOSITORY,
        "release/v2/pkg",
        "release/v2",
        "release",
    ]
    expected_lookups = [call(lookup, **GIT_KWARGS)]
    assert git_mocks["lookup"].call_args_list == expected_lookups
    root = result.local_root_path
    if ref_type == "tags":
        assert git_mocks["run"].call_args_list == [
            call(["git", "init", "--quiet"], cwd=STAGE, **GIT_KWARGS),
            call(
                ["git", "config", "remote.origin.url", REPOSITORY],
                cwd=STAGE,
                **GIT_KWARGS,
            ),
            call(
                [
                    "git",
                    "fetch",
                    "--depth",
                    "1",
                    "origin",
                    "refs/tags/release/v2:refs/tags/release/v2",
                ],
                cwd=STAGE,
                **GIT_KWARGS,
            ),
            call(
                ["git", "-c", "advice.detachedHead=False", "checkout", "FETCH_HEAD"],
                cwd=STAGE,
                **GIT_KWARGS,
            ),
        ]
    else:
        git_mocks["run"].assert_called_once_with(
            [
                "git",
                "clone",
                "-c",
                "advice.detachedHead=False",
                "--depth",
                "1",
                "--branch=release/v2",
                REPOSITORY,
                STAGE,
            ],
            **GIT_KWARGS,
        )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize("fail_fetch", [False, True])
def test_checkout_fetches_unadvertised_commit_sha(
    git_mocks: dict[str, Mock], fail_fetch: bool
) -> None:
    git_mocks["lookup"].return_value = ""
    git_mocks["run"].side_effect = [0, 0, 1] if fail_fetch else [0, 0, 0, 0, 0]
    scm = SourceCodeManager("cache", Mock())
    result = scm.get_code(f"{REPOSITORY}/tree/{SHA}", skip_canonical_lookup=True)
    assert (result is None) == fail_fetch
    root = GENERATION
    expected = [
        call(["git", "init", "--quiet"], cwd=STAGE, **GIT_KWARGS),
        call(
            ["git", "config", "remote.origin.url", REPOSITORY], cwd=STAGE, **GIT_KWARGS
        ),
        call(
            ["git", "fetch", "--force", "--depth", "1", "origin", SHA],
            cwd=STAGE,
            **GIT_KWARGS,
        ),
    ]
    if not fail_fetch:
        expected.append(
            call(
                [
                    "git",
                    "-c",
                    "advice.detachedHead=False",
                    "checkout",
                    "--force",
                    "FETCH_HEAD",
                ],
                cwd=STAGE,
                **GIT_KWARGS,
            )
        )
        expected.append(call(["git", "clean", "-ffdx"], cwd=STAGE, **GIT_KWARGS))
    assert git_mocks["run"].call_args_list == expected
    git_mocks["lookup"].assert_called_once_with(
        ["git", "ls-remote", "--", REPOSITORY, SHA], **GIT_KWARGS
    )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize("invalid_ref", ["missing", "main/../outside", "unsafe.lock"])
def test_unresolved_or_unsafe_ref_never_opens_checkout(
    git_mocks: dict[str, Mock], invalid_ref: str
) -> None:
    git_mocks["lookup"].return_value = (
        f"{SHA}\trefs/heads/main\n{SHA}\trefs/heads/unsafe.lock\n"
    )
    scm = SourceCodeManager("cache", Mock())
    assert (
        scm.get_code(f"{REPOSITORY}/tree/{invalid_ref}", skip_canonical_lookup=True)
        is None
    )
    git_mocks["lookup"].assert_any_call(
        [
            "git",
            "ls-remote",
            "--",
            REPOSITORY,
            *[
                "/".join(invalid_ref.split("/")[:i])
                for i in range(len(invalid_ref.split("/")), 0, -1)
            ],
        ],
        **GIT_KWARGS,
    )
    git_mocks["run"].assert_not_called()
    git_mocks["mkdir"].assert_not_called()
    git_mocks["cache_dirs"].assert_not_called()


def test_ref_lookup_timeout_never_opens_checkout(git_mocks: dict[str, Mock]) -> None:
    git_mocks["lookup"].side_effect = OSError("timeout")
    scm = SourceCodeManager("cache", Mock())
    assert scm.get_code(f"{REPOSITORY}/tree/main", skip_canonical_lookup=True) is None
    git_mocks["lookup"].assert_called_once_with(
        ["git", "ls-remote", "--", REPOSITORY, "main"], **GIT_KWARGS
    )
    git_mocks["run"].assert_not_called()
    git_mocks["mkdir"].assert_not_called()
    git_mocks["cache_dirs"].assert_not_called()


def test_matching_second_mirror_and_source_tag_mapping_are_preserved(
    git_mocks: dict[str, Mock],
) -> None:
    first = "https://mirror.example/first"
    second = "https://mirror.example/second"
    mirrors = [
        MirrorSpec(REPOSITORY, first),
        MirrorSpec(
            REPOSITORY, second, {(RefType.TAG, "v1"): (RefType.BRANCH, "release-1")}
        ),
    ]
    git_mocks["lookup"].side_effect = [
        "",
        "",
        "",
        "",
        "",
        "",
        f"{SHA}\trefs/heads/release-1\n",
    ]
    scm = SourceCodeManager("cache", Mock(), mirrors=mirrors)
    result = scm.get_code(f"{REPOSITORY}/tree/v1/pkg", skip_canonical_lookup=True)
    assert result is not None
    assert result.branch == "v1"
    assert result.local_full_path == result.local_root_path + "/pkg"
    lookup = git_mocks["lookup"]
    assert lookup.call_args_list == [
        call(["git", "ls-remote", "--", url, *refs], **GIT_KWARGS)
        for url, refs in [
            (REPOSITORY, ["v1/pkg", "v1"]),
            (REPOSITORY, []),
            (first, ["v1/pkg", "v1"]),
            (first, []),
            (second, ["v1/pkg", "v1"]),
            (second, []),
            (second, ["refs/heads/release-1"]),
        ]
    ]
    git_mocks["run"].assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=release-1",
            second,
            STAGE,
        ],
        **GIT_KWARGS,
    )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize(
    "ref,output,expected",
    [
        ("main", f"{SHA}\trefs/tags/main\n{SHA}\trefs/heads/main\n", "main"),
        ("main", f"{SHA}\trefs/heads/notmain\n", ""),
        ("", "", ""),
    ],
)
def test_ref_lookup_matches_exact_advertised_names(
    ref: str, output: str, expected: str
) -> None:
    with patch(
        MODULE + "source_code_manager.output_from_command", return_value=output
    ) as lookup:
        assert extract_ref(ref, REPOSITORY) == expected
        if not ref:
            lookup.assert_not_called()
        elif expected:
            lookup.assert_called_once_with(["git", "ls-remote", "--", REPOSITORY, ref])
        else:
            assert lookup.call_args_list == [
                call(["git", "ls-remote", "--", REPOSITORY, ref]),
                call(["git", "ls-remote", "--", REPOSITORY]),
            ]


@pytest.mark.parametrize("cached_head", [SHA, "", "f" * 40, "timeout"])
def test_commit_cache_requires_the_requested_commit(
    git_mocks: dict[str, Mock], cached_head: str
) -> None:
    git_mocks["cache_dirs"].return_value = ["20261127_120000Z"]
    git_mocks["cached"].return_value = True
    git_mocks["is_file"].return_value = True
    git_mocks["lookup"].side_effect = [
        "",
        OSError("timeout") if cached_head == "timeout" else cached_head,
    ]
    scm = SourceCodeManager("cache", Mock())
    result = scm.get_code(f"{REPOSITORY}/tree/{SHA}", skip_canonical_lookup=True)
    assert result is not None
    assert result.branch == SHA
    root = GENERATION
    assert git_mocks["lookup"].call_args_list == [
        call(["git", "ls-remote", "--", REPOSITORY, SHA], **GIT_KWARGS),
        call(["git", "rev-parse", "--verify", "HEAD"], cwd=root, **GIT_KWARGS),
    ]
    if cached_head == SHA:
        git_mocks["run"].assert_not_called()
        git_mocks["mkdir"].assert_not_called()
    else:
        git_mocks["run"].assert_has_calls(
            [
                call(["git", "init", "--quiet"], cwd=STAGE, **GIT_KWARGS),
                call(
                    ["git", "config", "remote.origin.url", REPOSITORY],
                    cwd=STAGE,
                    **GIT_KWARGS,
                ),
                call(
                    ["git", "fetch", "--force", "--depth", "1", "origin", SHA],
                    cwd=STAGE,
                    **GIT_KWARGS,
                ),
                call(
                    [
                        "git",
                        "-c",
                        "advice.detachedHead=False",
                        "checkout",
                        "--force",
                        "FETCH_HEAD",
                    ],
                    cwd=STAGE,
                    **GIT_KWARGS,
                ),
            ]
        )
        git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cached"].assert_called_once_with(root)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


def test_hexadecimal_named_branch_is_cloned_as_a_branch(
    git_mocks: dict[str, Mock],
) -> None:
    git_mocks["lookup"].return_value = f"{SHA}\trefs/heads/{SHA}\n"
    scm = SourceCodeManager("cache", Mock())
    result = scm.get_code(f"{REPOSITORY}/tree/{SHA}", skip_canonical_lookup=True)
    assert result is not None
    git_mocks["lookup"].assert_called_once_with(
        ["git", "ls-remote", "--", REPOSITORY, SHA], **GIT_KWARGS
    )
    git_mocks["run"].assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            f"--branch={SHA}",
            REPOSITORY,
            STAGE,
        ],
        **GIT_KWARGS,
    )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize("first_failure", ["original", "first-mirror"])
def test_lookup_timeout_still_tries_healthy_mirrors(
    git_mocks: dict[str, Mock], first_failure: str
) -> None:
    first = "https://mirror.example/first"
    healthy = "https://mirror.example/healthy"
    if first_failure == "original":
        mirrors = [MirrorSpec(REPOSITORY, healthy)]
        effects = [OSError("timeout"), f"{SHA}\trefs/heads/main\n"]
        urls = [REPOSITORY, healthy]
    else:
        mirrors = [MirrorSpec(REPOSITORY, first), MirrorSpec(REPOSITORY, healthy)]
        effects = ["", "", OSError("timeout"), f"{SHA}\trefs/heads/main\n"]
        urls = [REPOSITORY, REPOSITORY, first, healthy]
    git_mocks["lookup"].side_effect = effects
    scm = SourceCodeManager("cache", Mock(), mirrors=mirrors)
    result = scm.get_code(f"{REPOSITORY}/tree/main", skip_canonical_lookup=True)
    assert result is not None
    expected = [
        call(
            [
                "git",
                "ls-remote",
                "--",
                url,
                *([] if i == 1 and first_failure == "first-mirror" else ["main"]),
            ],
            **GIT_KWARGS,
        )
        for i, url in enumerate(urls)
    ]
    assert git_mocks["lookup"].call_args_list == expected
    git_mocks["run"].assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=main",
            healthy,
            STAGE,
        ],
        **GIT_KWARGS,
    )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize("ref_type", [RefType.BRANCH, RefType.TAG])
def test_longer_mapped_ref_wins_over_shorter_advertised_mirror_ref(
    git_mocks: dict[str, Mock], ref_type: RefType
) -> None:
    mirror = "https://mirror.example/repo"
    mirror_spec = MirrorSpec(
        REPOSITORY, mirror, {(ref_type, "release/v2"): (ref_type, "stable")}
    )

    def lookup(args: list[str], **kwargs: object) -> str:
        if args[3] == REPOSITORY:
            return ""
        if args[4:] in (["refs/heads/stable"], ["refs/tags/stable"]):
            kind = "heads" if ref_type == RefType.BRANCH else "tags"
            return f"{SHA}\trefs/{kind}/stable\n"
        return f"{SHA}\trefs/heads/release\n"

    git_mocks["lookup"].side_effect = lookup
    scm = SourceCodeManager("cache", Mock(), mirrors=[mirror_spec])
    result = scm.get_code(
        f"{REPOSITORY}/tree/release/v2/pkg", skip_canonical_lookup=True
    )
    assert result is not None
    assert result.branch == "release/v2"
    assert result.local_full_path == result.local_root_path + "/pkg"
    git_mocks["lookup"].assert_has_calls(
        [
            call(
                [
                    "git",
                    "ls-remote",
                    "--",
                    REPOSITORY,
                    "release/v2/pkg",
                    "release/v2",
                    "release",
                ],
                **GIT_KWARGS,
            ),
            call(["git", "ls-remote", "--", REPOSITORY], **GIT_KWARGS),
            call(
                [
                    "git",
                    "ls-remote",
                    "--",
                    mirror,
                    "release/v2/pkg",
                    "release/v2",
                    "release",
                ],
                **GIT_KWARGS,
            ),
            call(
                [
                    "git",
                    "ls-remote",
                    "--",
                    mirror,
                    (
                        "refs/heads/stable"
                        if ref_type == RefType.BRANCH
                        else "refs/tags/stable"
                    ),
                ],
                **GIT_KWARGS,
            ),
        ]
    )
    if ref_type == RefType.BRANCH:
        git_mocks["run"].assert_called_once_with(
            [
                "git",
                "clone",
                "-c",
                "advice.detachedHead=False",
                "--depth",
                "1",
                "--branch=stable",
                mirror,
                STAGE,
            ],
            **GIT_KWARGS,
        )
    else:
        git_mocks["run"].assert_has_calls(
            [
                call(["git", "init", "--quiet"], cwd=STAGE, **GIT_KWARGS),
                call(
                    ["git", "config", "remote.origin.url", mirror],
                    cwd=STAGE,
                    **GIT_KWARGS,
                ),
                call(
                    [
                        "git",
                        "fetch",
                        "--depth",
                        "1",
                        "origin",
                        "refs/tags/stable:refs/tags/stable",
                    ],
                    cwd=STAGE,
                    **GIT_KWARGS,
                ),
                call(
                    [
                        "git",
                        "-c",
                        "advice.detachedHead=False",
                        "checkout",
                        "FETCH_HEAD",
                    ],
                    cwd=STAGE,
                    **GIT_KWARGS,
                ),
            ]
        )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize("source_type", [RefType.BRANCH, RefType.TAG])
@pytest.mark.parametrize("original_failure", ["unresolved", "timeout"])
def test_explicit_mapping_wins_over_conflicting_mirror_ref_type(
    git_mocks: dict[str, Mock], source_type: RefType, original_failure: str
) -> None:
    mirror = "https://mirror.example/repo"
    mirror_spec = MirrorSpec(
        REPOSITORY, mirror, {(source_type, "main"): (RefType.BRANCH, "review")}
    )
    conflicting_type = "tags" if source_type == RefType.BRANCH else "heads"

    def lookup(args: list[str], **kwargs: object) -> str:
        if args[3] == REPOSITORY:
            if original_failure == "timeout":
                raise OSError("original repository unavailable")
            return ""
        if args[4:] == ["refs/heads/review"]:
            return f"{SHA}\trefs/heads/review\n"
        return f"{SHA}\trefs/{conflicting_type}/main\n"

    git_mocks["lookup"].side_effect = lookup
    scm = SourceCodeManager("cache", Mock(), mirrors=[mirror_spec])
    result = scm.get_code(f"{REPOSITORY}/tree/main/pkg", skip_canonical_lookup=True)
    assert result is not None
    assert result.branch == "main"
    assert result.local_full_path == result.local_root_path + "/pkg"
    expected_lookups = [
        call(["git", "ls-remote", "--", REPOSITORY, "main/pkg", "main"], **GIT_KWARGS)
    ]
    if original_failure == "unresolved":
        expected_lookups.append(
            call(["git", "ls-remote", "--", REPOSITORY], **GIT_KWARGS)
        )
    expected_lookups.extend(
        [
            call(["git", "ls-remote", "--", mirror, "main/pkg", "main"], **GIT_KWARGS),
            call(["git", "ls-remote", "--", mirror, "refs/heads/review"], **GIT_KWARGS),
        ]
    )
    git_mocks["lookup"].assert_has_calls(expected_lookups)
    git_mocks["run"].assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=review",
            mirror,
            STAGE,
        ],
        **GIT_KWARGS,
    )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize("source_type", [RefType.BRANCH, RefType.TAG])
@pytest.mark.parametrize("target_failure", ["missing", "timeout"])
def test_failed_explicit_mapping_never_uses_conflicting_mirror_ref(
    git_mocks: dict[str, Mock], source_type: RefType, target_failure: str
) -> None:
    mirror = "https://mirror.example/repo"
    spec = MirrorSpec(
        REPOSITORY, mirror, {(source_type, "main"): (RefType.BRANCH, "review")}
    )
    conflicting_type = "tags" if source_type == RefType.BRANCH else "heads"

    def lookup(args: list[str], **kwargs: object) -> str:
        if args[3] == REPOSITORY:
            return ""
        if args[4:] == ["refs/heads/review"]:
            if target_failure == "timeout":
                raise OSError("mapped target unavailable")
            return ""
        return f"{SHA}\trefs/{conflicting_type}/main\n"

    git_mocks["lookup"].side_effect = lookup
    scm = SourceCodeManager("cache", Mock(), mirrors=[spec])
    assert scm.get_code(f"{REPOSITORY}/tree/main", skip_canonical_lookup=True) is None
    expected = [
        call(["git", "ls-remote", "--", REPOSITORY, "main"], **GIT_KWARGS),
        call(["git", "ls-remote", "--", REPOSITORY], **GIT_KWARGS),
        call(["git", "ls-remote", "--", mirror, "main"], **GIT_KWARGS),
        call(["git", "ls-remote", "--", mirror, "refs/heads/review"], **GIT_KWARGS),
    ]
    git_mocks["lookup"].assert_has_calls(expected)
    git_mocks["run"].assert_not_called()
    git_mocks["mkdir"].assert_not_called()
    git_mocks["cache_dirs"].assert_not_called()


def test_failed_mapping_still_allows_a_healthy_later_mirror(
    git_mocks: dict[str, Mock],
) -> None:
    first = "https://mirror.example/first"
    healthy = "https://mirror.example/healthy"
    mapping = {(RefType.BRANCH, "main"): (RefType.BRANCH, "review")}

    def lookup(args: list[str], **kwargs: object) -> str:
        if args[3] == REPOSITORY:
            return ""
        if args[4:] == ["refs/heads/review"]:
            return f"{SHA}\trefs/heads/review\n" if args[3] == healthy else ""
        return f"{SHA}\trefs/tags/main\n"

    git_mocks["lookup"].side_effect = lookup
    scm = SourceCodeManager(
        "cache",
        Mock(),
        mirrors=[
            MirrorSpec(REPOSITORY, first, mapping),
            MirrorSpec(REPOSITORY, healthy, mapping),
        ],
    )
    result = scm.get_code(f"{REPOSITORY}/tree/main", skip_canonical_lookup=True)
    assert result is not None
    git_mocks["lookup"].assert_has_calls(
        [
            call(["git", "ls-remote", "--", REPOSITORY, "main"], **GIT_KWARGS),
            call(["git", "ls-remote", "--", REPOSITORY], **GIT_KWARGS),
            call(["git", "ls-remote", "--", first, "main"], **GIT_KWARGS),
            call(["git", "ls-remote", "--", first, "refs/heads/review"], **GIT_KWARGS),
            call(["git", "ls-remote", "--", healthy, "main"], **GIT_KWARGS),
            call(
                ["git", "ls-remote", "--", healthy, "refs/heads/review"], **GIT_KWARGS
            ),
        ]
    )
    git_mocks["run"].assert_called_once_with(
        [
            "git",
            "clone",
            "-c",
            "advice.detachedHead=False",
            "--depth",
            "1",
            "--branch=review",
            healthy,
            STAGE,
        ],
        **GIT_KWARGS,
    )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize("target_type", [RefType.BRANCH, RefType.TAG])
@pytest.mark.parametrize("healthy_has_both_types", [False, True])
def test_mapped_target_namespace_selects_a_healthy_later_mirror(
    git_mocks: dict[str, Mock], target_type: RefType, healthy_has_both_types: bool
) -> None:
    first = "https://mirror.example/wrong-type"
    healthy = "https://mirror.example/healthy"
    mapping = {(RefType.BRANCH, "main"): (target_type, "stable")}
    required = "heads" if target_type == RefType.BRANCH else "tags"
    opposite = "tags" if target_type == RefType.BRANCH else "heads"

    def lookup(args: list[str], **kwargs: object) -> str:
        if args[3] == REPOSITORY or args[4:] == ["main"]:
            return ""
        if args[3] == first:
            return f"{SHA}\trefs/{opposite}/stable\n"
        result = f"{SHA}\trefs/{required}/stable\n"
        if healthy_has_both_types:
            result += f"{'f' * 40}\trefs/{opposite}/stable\n"
        return result

    git_mocks["lookup"].side_effect = lookup
    scm = SourceCodeManager(
        "cache",
        Mock(),
        mirrors=[
            MirrorSpec(REPOSITORY, first, mapping),
            MirrorSpec(REPOSITORY, healthy, mapping),
        ],
    )
    result = scm.get_code(f"{REPOSITORY}/tree/main", skip_canonical_lookup=True)
    assert result is not None
    git_mocks["lookup"].assert_any_call(
        ["git", "ls-remote", "--", first, f"refs/{required}/stable"], **GIT_KWARGS
    )
    git_mocks["lookup"].assert_any_call(
        ["git", "ls-remote", "--", healthy, f"refs/{required}/stable"], **GIT_KWARGS
    )
    if target_type == RefType.BRANCH:
        git_mocks["run"].assert_called_once_with(
            [
                "git",
                "clone",
                "-c",
                "advice.detachedHead=False",
                "--depth",
                "1",
                "--branch=stable",
                healthy,
                STAGE,
            ],
            **GIT_KWARGS,
        )
    else:
        git_mocks["run"].assert_has_calls(
            [
                call(
                    ["git", "config", "remote.origin.url", healthy],
                    cwd=STAGE,
                    **GIT_KWARGS,
                ),
                call(
                    [
                        "git",
                        "fetch",
                        "--depth",
                        "1",
                        "origin",
                        "refs/tags/stable:refs/tags/stable",
                    ],
                    cwd=STAGE,
                    **GIT_KWARGS,
                ),
            ]
        )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize("second_type", [RefType.COMMIT, RefType.TAG, RefType.BRANCH])
def test_provisional_sha_fetch_failure_tries_later_mirrors(
    git_mocks: dict[str, Mock], second_type: RefType
) -> None:
    first = "https://mirror.example/missing-commit"
    healthy = "https://mirror.example/healthy"
    mapping: dict[tuple[RefType, str], tuple[RefType, str]] | None = (
        None
        if second_type == RefType.COMMIT
        else {(RefType.COMMIT, SHA): (second_type, "stable")}
    )
    mirrors = [MirrorSpec(REPOSITORY, first), MirrorSpec(REPOSITORY, healthy, mapping)]
    active = [""]

    def lookup(args: list[str], **kwargs: object) -> str:
        if args[:2] == ["git", "rev-parse"]:
            return "f" * 40
        if args[3] == REPOSITORY:
            raise OSError("original lookup timed out")
        return ""

    def execute(args: list[str], **kwargs: object) -> int:
        if args[:3] == ["git", "config", "remote.origin.url"]:
            active[0] = args[3]
        return 1 if args[:2] == ["git", "fetch"] and active[0] == first else 0

    git_mocks["lookup"].side_effect = lookup
    git_mocks["run"].side_effect = execute
    scm = SourceCodeManager("cache", Mock(), mirrors=mirrors)
    result = scm.get_code(f"{REPOSITORY}/tree/{SHA}", skip_canonical_lookup=True)
    assert result is not None
    assert result.branch == SHA
    root = result.local_root_path
    refspec = (
        SHA
        if second_type == RefType.COMMIT
        else (
            "refs/tags/stable:refs/tags/stable"
            if second_type == RefType.TAG
            else "refs/heads/stable"
        )
    )
    git_mocks["run"].assert_has_calls(
        [
            call(
                ["git", "config", "remote.origin.url", first], cwd=STAGE, **GIT_KWARGS
            ),
            call(
                ["git", "fetch", "--force", "--depth", "1", "origin", SHA],
                cwd=STAGE,
                **GIT_KWARGS,
            ),
            call(["git", "init", "--quiet"], cwd=STAGE, **GIT_KWARGS),
            call(
                ["git", "config", "remote.origin.url", healthy], cwd=STAGE, **GIT_KWARGS
            ),
            call(
                ["git", "fetch", "--force", "--depth", "1", "origin", refspec],
                cwd=STAGE,
                **GIT_KWARGS,
            ),
        ]
    )
    git_mocks["mkdir"].assert_called_once_with(STAGE)
    git_mocks["cache_dirs"].assert_called_once_with("cache")


@pytest.mark.parametrize("first_mapped", [False, True])
@pytest.mark.parametrize("target_type", [RefType.BRANCH, RefType.TAG])
@pytest.mark.parametrize(
    "case",
    [
        "valid",
        "invalid-json",
        "not-list",
        "wrong-length",
        "not-string",
        "wrong-source",
        "wrong-url",
        "wrong-type",
        "wrong-target",
        "wrong-head",
        "unmapped",
        "unreadable",
        "empty-head",
        "invalid-head",
    ],
)
def test_cached_sha_mapping_requires_matching_provenance(
    git_mocks: dict[str, Mock], target_type: RefType, case: str, first_mapped: bool
) -> None:
    first = "https://mirror.example/missing"
    healthy = "https://mirror.example/healthy"
    head = (
        ""
        if case == "empty-head"
        else "not-a-sha" if case == "invalid-head" else "f" * 40
    )
    target = "stable"
    mapping = {(RefType.COMMIT, SHA): (target_type, target)}
    git_mocks["cache_dirs"].return_value = ["20261127_120000Z"]
    git_mocks["cached"].return_value = True
    git_mocks["is_file"].return_value = True
    git_mocks["run"].return_value = 1
    metadata: object = [SHA, healthy, target_type.value, target, head]
    replacements: dict[str, object] = {
        "not-list": {},
        "wrong-length": [],
        "not-string": [SHA, healthy, target_type.value, target, None],
        "wrong-source": ["a" * 40, healthy, target_type.value, target, head],
        "wrong-url": [
            SHA,
            "https://mirror.example/removed",
            target_type.value,
            target,
            head,
        ],
        "wrong-type": [SHA, healthy, "other", target, head],
        "wrong-target": [SHA, healthy, target_type.value, "changed", head],
        "wrong-head": [SHA, healthy, target_type.value, target, "b" * 40],
        "unmapped": [SHA, first, RefType.COMMIT.value, SHA, head],
    }
    metadata = replacements.get(case, metadata)

    def lookup(args: list[str], **kwargs: object) -> str:
        if args[:2] == ["git", "ls-remote"]:
            if args[3] == REPOSITORY:
                raise OSError("original lookup timed out")
            return f"{'f' * 40}\t{args[4]}\n" if args[4].startswith("refs/") else ""
        if args[:2] == ["git", "rev-parse"]:
            return head
        assert args == ["git", "config", "--local", "--get", "ddla.resolved-ref"]
        if case == "unreadable":
            raise OSError("missing local provenance")
        return "{" if case == "invalid-json" else json.dumps(metadata)

    git_mocks["lookup"].side_effect = lookup
    scm = SourceCodeManager(
        "cache",
        Mock(),
        mirrors=(
            [MirrorSpec(REPOSITORY, healthy, mapping)]
            if first_mapped
            else [
                MirrorSpec(REPOSITORY, first),
                MirrorSpec(REPOSITORY, healthy, mapping),
            ]
        ),
    )
    result = scm.get_code(REPOSITORY + "/tree/" + SHA, skip_canonical_lookup=True)
    git_mocks["lookup"].assert_any_call(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=GENERATION,
        **GIT_KWARGS,
    )
    if case in ("empty-head", "invalid-head"):
        assert not any(
            args.args[0][:2] == ["git", "config"]
            for args in git_mocks["lookup"].call_args_list
        )
    else:
        git_mocks["lookup"].assert_any_call(
            ["git", "config", "--local", "--get", "ddla.resolved-ref"],
            cwd=GENERATION,
            **GIT_KWARGS,
        )
    if case == "valid":
        assert result is not None
        assert result.local_root_path == GENERATION
        git_mocks["run"].assert_not_called()
        git_mocks["mkdir"].assert_not_called()
    else:
        assert result is None
        assert git_mocks["run"].call_args_list == [
            call(["git", "init", "--quiet"], cwd=STAGE, **GIT_KWARGS)
        ] * (1 if first_mapped else 2)
        git_mocks["remove"].assert_called_once_with(STAGE)
    git_mocks["rename"].assert_not_called()


@pytest.mark.parametrize("failure", ["head-error", "invalid-head", "write-error"])
def test_failed_sha_mapping_provenance_is_not_published(
    git_mocks: dict[str, Mock], failure: str
) -> None:
    healthy = "https://mirror.example/healthy"
    mapping = {(RefType.COMMIT, SHA): (RefType.BRANCH, "stable")}

    def lookup(args: list[str], **kwargs: object) -> str:
        if args[:2] == ["git", "rev-parse"]:
            if failure == "head-error":
                raise OSError("unreadable HEAD")
            return "not-a-sha" if failure == "invalid-head" else "f" * 40
        return ""

    def execute(args: list[str], **kwargs: object) -> int:
        return 1 if args[:4] == ["git", "config", "--local", "ddla.resolved-ref"] else 0

    git_mocks["lookup"].side_effect = lookup
    git_mocks["run"].side_effect = execute
    scm = SourceCodeManager(
        "cache", Mock(), mirrors=[MirrorSpec(REPOSITORY, healthy, mapping)]
    )
    assert scm.get_code(REPOSITORY + "/tree/" + SHA, skip_canonical_lookup=True) is None
    git_mocks["lookup"].assert_any_call(
        ["git", "rev-parse", "--verify", "HEAD"],
        cwd=STAGE,
        **GIT_KWARGS,
    )
    if failure == "write-error":
        git_mocks["run"].assert_any_call(
            [
                "git",
                "config",
                "--local",
                "ddla.resolved-ref",
                json.dumps(
                    [
                        SHA,
                        healthy,
                        RefType.BRANCH.value,
                        "stable",
                        "f" * 40,
                    ]
                ),
            ],
            cwd=STAGE,
            **GIT_KWARGS,
        )
    git_mocks["remove"].assert_called_once_with(STAGE)
    git_mocks["rename"].assert_not_called()
    git_mocks["replace"].assert_not_called()


@pytest.mark.parametrize("target_type", [RefType.BRANCH, RefType.TAG])
@pytest.mark.parametrize("failure", ["missing", "timeout"])
def test_reachable_source_does_not_bypass_a_missing_mapped_destination(
    git_mocks: dict[str, Mock], target_type: RefType, failure: str
) -> None:
    mirror = "https://mirror.example/missing-target"
    namespace = "heads" if target_type == RefType.BRANCH else "tags"
    git_mocks["lookup"].side_effect = [
        f"{SHA}\trefs/tags/v1\n",
        OSError("target lookup timed out") if failure == "timeout" else "",
    ]
    scm = SourceCodeManager(
        "cache",
        Mock(),
        mirrors=[
            MirrorSpec(
                REPOSITORY,
                mirror,
                {(RefType.TAG, "v1"): (target_type, "stable")},
            )
        ],
    )
    assert scm.get_code(REPOSITORY + "/tree/v1", skip_canonical_lookup=True) is None
    assert git_mocks["lookup"].call_args_list == [
        call(["git", "ls-remote", "--", REPOSITORY, "v1"], **GIT_KWARGS),
        call(
            ["git", "ls-remote", "--", mirror, f"refs/{namespace}/stable"], **GIT_KWARGS
        ),
    ]
    git_mocks["run"].assert_not_called()
    git_mocks["mkdir"].assert_not_called()
    git_mocks["cache_dirs"].assert_not_called()
