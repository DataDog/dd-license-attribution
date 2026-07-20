# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import pytest

from dd_license_attribution.config.action_mirror import (
    ActionMirrorContext,
    build_action_mirror,
    build_action_mirror_entries,
)


class TestBuildActionMirror:
    def test_builds_public_default_branch_mirror(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(
                repository="DataDog/example",
                self_repository="DataDog/example",
            )
        )

        assert mirror == {
            "original_url": "https://github.com/DataDog/example",
            "mirror_url": "https://github.com/DataDog/example",
        }

    def test_builds_authenticated_mirror(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(repository="DataDog/private", token="secret")
        )

        assert mirror == {
            "original_url": "https://github.com/DataDog/private",
            "mirror_url": "https://git:secret@github.com/DataDog/private",
        }

    def test_maps_pull_request_to_fork_head(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(
                repository="DataDog/example",
                self_repository="DataDog/example",
                event="pull_request",
                head_ref="feature",
                pr_head_repo="contributor/example",
            )
        )

        assert mirror == {
            "original_url": "https://github.com/DataDog/example",
            "mirror_url": "https://github.com/contributor/example",
            "ref_mapping": {"branch:main": "branch:feature"},
        }

    def test_does_not_map_incomplete_pull_request_context(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(
                repository="DataDog/example",
                self_repository="DataDog/example",
                event="pull_request",
                head_ref="feature",
            )
        )

        assert "ref_mapping" not in mirror

    def test_does_not_map_pull_request_target_head(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(
                repository="DataDog/example",
                self_repository="DataDog/example",
                event="pull_request_target",
                head_ref="untrusted-feature",
                pr_head_repo="contributor/example",
                ref_name="main",
            )
        )

        assert mirror == {
            "original_url": "https://github.com/DataDog/example",
            "mirror_url": "https://github.com/DataDog/example",
        }

    def test_maps_merge_group_ref(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(
                repository="DataDog/example",
                self_repository="DataDog/example",
                event="merge_group",
                merge_group_ref="refs/heads/gh-readonly-queue/main/pr-123",
            )
        )

        assert mirror["ref_mapping"] == {
            "branch:main": "branch:gh-readonly-queue/main/pr-123"
        }

    def test_maps_non_default_push_ref(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(
                repository="DataDog/example",
                self_repository="DataDog/example",
                event="push",
                ref_name="release",
            )
        )

        assert mirror["ref_mapping"] == {"branch:main": "branch:release"}

    def test_uses_declared_default_branch(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(
                repository="DataDog/example",
                self_repository="DataDog/example",
                default_branch="develop",
                event="push",
                ref_name="feature",
            )
        )

        assert mirror["ref_mapping"] == {"branch:develop": "branch:feature"}

    def test_falls_back_to_main_for_empty_default_branch(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(
                repository="DataDog/example",
                self_repository="DataDog/example",
                default_branch="",
                event="push",
                ref_name="feature",
            )
        )

        assert mirror["ref_mapping"] == {"branch:main": "branch:feature"}

    def test_does_not_map_another_repository(self) -> None:
        mirror = build_action_mirror(
            ActionMirrorContext(
                repository="DataDog/dependency",
                self_repository="DataDog/example",
                event="pull_request",
                head_ref="feature",
                pr_head_repo="contributor/example",
                ref_name="123/merge",
            )
        )

        assert mirror == {
            "original_url": "https://github.com/DataDog/dependency",
            "mirror_url": "https://github.com/DataDog/dependency",
        }


class TestBuildActionMirrorEntries:
    def test_appends_generated_mirror(self) -> None:
        entries = build_action_mirror_entries(
            ActionMirrorContext(repository="DataDog/example")
        )

        assert entries == [
            {
                "original_url": "https://github.com/DataDog/example",
                "mirror_url": "https://github.com/DataDog/example",
            }
        ]

    def test_preserves_user_entry_precedence(self) -> None:
        user_entry = {
            "original_url": "https://github.com/DataDog/example",
            "mirror_url": "https://github.com/mirror/example",
        }

        entries = build_action_mirror_entries(
            ActionMirrorContext(repository="DataDog/example"), [user_entry]
        )

        assert entries[0] == user_entry
        assert entries[1] == {
            "original_url": "https://github.com/DataDog/example",
            "mirror_url": "https://github.com/DataDog/example",
        }

    def test_rejects_non_array_user_configuration(self) -> None:
        with pytest.raises(
            ValueError, match="user mirror configuration must be a JSON array"
        ):
            build_action_mirror_entries(
                ActionMirrorContext(repository="DataDog/example"), {}
            )
