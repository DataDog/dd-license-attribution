# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from pathlib import Path
from unittest.mock import Mock

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
