# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from dataclasses import dataclass


@dataclass(frozen=True)
class ActionMirrorContext:
    """GitHub event context used to build the composite action's mirror."""

    repository: str
    self_repository: str = ""
    default_branch: str = "main"
    token: str = ""
    event: str = ""
    head_ref: str = ""
    pr_head_repo: str = ""
    merge_group_ref: str = ""
    ref_name: str = ""


def build_action_mirror(context: ActionMirrorContext) -> dict[str, object]:
    """Build the action-generated mirror entry for a repository scan."""
    default_branch = context.default_branch or "main"
    target_repo = context.repository
    target_ref = ""

    if context.repository == context.self_repository:
        # Only pull_request maps to the head repository. In particular,
        # pull_request_target must never select untrusted head code while its
        # privileged token is available to dependency-analysis subprocesses.
        if (
            context.event == "pull_request"
            and context.pr_head_repo
            and context.head_ref
        ):
            target_repo = context.pr_head_repo
            target_ref = context.head_ref
        elif context.event == "merge_group" and context.merge_group_ref:
            target_ref = context.merge_group_ref.removeprefix("refs/heads/")
        elif context.ref_name and context.ref_name != default_branch:
            target_ref = context.ref_name

    if context.token:
        mirror_url = f"https://git:{context.token}@github.com/{target_repo}"
    else:
        mirror_url = f"https://github.com/{target_repo}"

    mirror: dict[str, object] = {
        "original_url": f"https://github.com/{context.repository}",
        "mirror_url": mirror_url,
    }
    if target_ref:
        mirror["ref_mapping"] = {f"branch:{default_branch}": f"branch:{target_ref}"}
    return mirror


def build_action_mirror_entries(
    context: ActionMirrorContext, user_entries: object | None = None
) -> list[object]:
    """Place caller-supplied mirrors before the action-generated fallback."""
    if user_entries is None:
        entries: list[object] = []
    elif isinstance(user_entries, list):
        entries = list(user_entries)
    else:
        raise ValueError("user mirror configuration must be a JSON array")

    entries.append(build_action_mirror(context))
    return entries
