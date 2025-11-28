# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from giturlparse import parse


def test_tree_url_1() -> None:
    tree_url = "https://github.com/DataDog/ospo-tools/tree/main/src"
    parsed = parse(tree_url)
    assert parsed.valid
    assert parsed.protocol == "https"
    assert parsed.host == "github.com"
    assert parsed.owner == "DataDog"
    assert parsed.repo == "ospo-tools"
    # The values below may seem incorrect, but it is current behavior at the time of writing
    assert parsed.branch == "main/src"
    assert parsed.path_raw == "/tree/main/src"
    assert parsed.path == ""
    assert parsed.github


def test_tree_url_2() -> None:
    tree_url = "https://github.com/DataDog/ospo-tools/tree/main"
    parsed = parse(tree_url)
    assert parsed.valid
    assert parsed.protocol == "https"
    assert parsed.host == "github.com"
    assert parsed.owner == "DataDog"
    assert parsed.repo == "ospo-tools"
    # The values below may seem incorrect, but it is current behavior at the time of writing
    assert parsed.branch == "main"
    assert parsed.path_raw == "/tree/main"
    assert parsed.path == ""
    assert parsed.github


def test_blob_url_1() -> None:
    blob_url = "https://github.com/DataDog/ospo-tools/blob/main/src/dd_license_attribution/cli/__init__.py"
    parsed = parse(blob_url)
    assert parsed.valid
    assert parsed.protocol == "https"
    assert parsed.host == "github.com"
    assert parsed.owner == "DataDog"
    assert parsed.repo == "ospo-tools"
    # The values below may seem incorrect, but it is current behavior at the time of writing
    assert parsed.branch == ""
    assert parsed.path_raw == "/blob/main/src/dd_license_attribution/cli/__init__.py"
    assert parsed.path == "main/src/dd_license_attribution/cli/__init__.py"
    assert parsed.github


def test_releases_tag_url_1() -> None:
    releases_tag_url = "https://github.com/DataDog/ospo-tools/tree/v0.1.0-beta"
    parsed = parse(releases_tag_url)
    assert parsed.valid
    assert parsed.protocol == "https"
    assert parsed.host == "github.com"
    assert parsed.owner == "DataDog"
    assert parsed.repo == "ospo-tools"
    # The values below may seem incorrect, but it is current behavior at the time of writing
    assert parsed.branch == "v0.1.0-beta"
    assert parsed.path_raw == "/tree/v0.1.0-beta"
    assert parsed.path == ""
    assert parsed.github


def test_repo_url_1() -> None:
    repo_url = "https://github.com/DataDog/ospo-tools"
    parsed = parse(repo_url)
    assert parsed.valid
    assert parsed.protocol == "https"
    assert parsed.host == "github.com"
    assert parsed.owner == "DataDog"
    assert parsed.repo == "ospo-tools"
    assert parsed.branch == ""
    assert parsed.path_raw == ""
    assert parsed.path == ""
    assert parsed.github
