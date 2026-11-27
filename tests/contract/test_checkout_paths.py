# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from pathlib import Path
from unittest.mock import Mock, call, patch

from dd_license_attribution.artifact_management.source_code_manager import (
    SourceCodeManager,
)


def test_checkout_containment_resolves_parent_segments_and_symlinks(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    cache.mkdir()
    scm = SourceCodeManager(str(cache), Mock())
    checkout = cache / "repo"
    checkout.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    (cache / "escape").symlink_to(outside, target_is_directory=True)
    (checkout / "escape").symlink_to(outside, target_is_directory=True)
    assert scm._is_within_cache_dir(str(checkout))
    assert not scm._is_within_cache_dir(str(cache))
    assert not scm._is_within_cache_dir(str(cache / ".." / "outside"))
    assert not scm._is_within_cache_dir(str(cache / "escape"))
    assert not scm._is_within_cache_dir(str(tmp_path / "cache-other"))
    assert scm._is_within_checkout_root(str(checkout), str(checkout / "src"))
    assert not scm._is_within_checkout_root(
        str(checkout), str(checkout / ".." / "sibling")
    )
    assert not scm._is_within_checkout_root(str(checkout), str(checkout / "escape"))


def test_nested_ref_publication_ignores_concurrent_checkout_symlinks(
    tmp_path: Path,
) -> None:
    cache = tmp_path / "cache"
    outside = tmp_path / "outside-cache"
    cache.mkdir()
    outside.mkdir()
    scm = SourceCodeManager(str(cache), Mock())
    repository_cache = cache / scm.timestamped_dir / "owner-repo"

    def clone_and_publish_competing_checkout(args: list[str], **kwargs: object) -> int:
        staging = Path(args[-1])
        (staging / ".git").mkdir()
        (staging / "marker").write_text("requested checkout")
        competing = repository_cache / ".competing-checkout"
        competing.mkdir()
        (competing / ".git").mkdir()
        (competing / "link").symlink_to(outside, target_is_directory=True)
        competing.rename(repository_cache / "release")
        return 0

    module = "dd_license_attribution.artifact_management.source_code_manager."
    with (
        patch(
            module + "output_from_command",
            return_value="ref: refs/heads/release/link/subref\tHEAD\n",
        ) as lookup,
        patch(
            module + "run_command", side_effect=clone_and_publish_competing_checkout
        ) as clone,
    ):
        result = scm.get_code(
            "https://github.com/owner/repo", skip_canonical_lookup=True
        )
        assert result is not None
        assert (
            scm.get_code("https://github.com/owner/repo", skip_canonical_lookup=True)
            == result
        )
        lookup.assert_has_calls(
            [
                call(
                    [
                        "git",
                        "ls-remote",
                        "--symref",
                        "--",
                        "https://github.com/owner/repo",
                        "HEAD",
                    ],
                    env={"GIT_TERMINAL_PROMPT": "0"},
                    timeout=30,
                ),
                call(
                    [
                        "git",
                        "ls-remote",
                        "--symref",
                        "--",
                        "https://github.com/owner/repo",
                        "HEAD",
                    ],
                    env={"GIT_TERMINAL_PROMPT": "0"},
                    timeout=30,
                ),
            ]
        )
        clone.assert_called_once()
    assert result is not None
    assert Path(result.local_root_path).resolve().is_relative_to(cache.resolve())
    assert not (outside / "subref").exists()
    assert (Path(result.local_root_path) / "marker").read_text() == "requested checkout"
