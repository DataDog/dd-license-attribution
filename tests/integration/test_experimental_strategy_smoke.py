# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

"""Smoke tests for --experimental-strategy CLI flag.

These tests run the full CLI against real external targets and validate that:
- The command exits successfully
- The output is non-trivially non-empty (at least a minimum number of packages)
- Experimental does not silently drop packages the classic strategy found

Minimum line counts are intentionally loose — they guard against a broken
pipeline returning zero results, not against dependency set changes as packages
evolve over time.

subprocess is used instead of CliRunner so that stderr (log lines) is kept
separate from stdout (CSV output) and does not corrupt CSV parsing.
"""

import csv
import io
import os
import subprocess
import sys

import pytest


def _github_token() -> str:
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        pytest.skip("GITHUB_TOKEN not set — skipping experimental strategy smoke test")
    return token


def _run(args: list[str], token: str) -> tuple[int, str]:
    env = os.environ.copy()
    env["GITHUB_TOKEN"] = token
    result = subprocess.run(
        [sys.executable, "-m", "dd_license_attribution.cli.main_cli"] + args,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout


def _parse_csv(output: str) -> list[dict[str, str]]:
    return list(csv.DictReader(io.StringIO(output)))


def test_experimental_strategy_github_repo_succeeds_and_returns_packages() -> None:
    token = _github_token()

    classic_rc, classic_out = _run(
        ["generate-sbom", "https://github.com/DataDog/apigentools"], token
    )
    experimental_rc, experimental_out = _run(
        [
            "generate-sbom",
            "--experimental-strategy",
            "https://github.com/DataDog/apigentools",
        ],
        token,
    )

    assert classic_rc == 0, f"Classic exited {classic_rc}"
    assert experimental_rc == 0, f"Experimental exited {experimental_rc}"

    classic_rows = _parse_csv(classic_out)
    experimental_rows = _parse_csv(experimental_out)

    assert (
        len(classic_rows) >= 5
    ), f"Classic returned too few packages: {len(classic_rows)}"
    assert (
        len(experimental_rows) >= 5
    ), f"Experimental returned too few packages: {len(experimental_rows)}"

    classic_names = {r["component"] for r in classic_rows}
    experimental_names = {r["component"] for r in experimental_rows}
    missing = classic_names - experimental_names
    assert not missing, f"Experimental is missing packages found by classic: {missing}"


def test_experimental_strategy_ecosystem_python_succeeds_and_returns_packages() -> None:
    token = _github_token()

    classic_rc, classic_out = _run(
        ["generate-sbom", "--ecosystem", "python", "apigentools"], token
    )
    experimental_rc, experimental_out = _run(
        [
            "generate-sbom",
            "--experimental-strategy",
            "--ecosystem",
            "python",
            "apigentools",
        ],
        token,
    )

    assert classic_rc == 0, f"Classic exited {classic_rc}"
    assert experimental_rc == 0, f"Experimental exited {experimental_rc}"

    classic_rows = _parse_csv(classic_out)
    experimental_rows = _parse_csv(experimental_out)

    assert (
        len(classic_rows) >= 3
    ), f"Classic returned too few packages: {len(classic_rows)}"
    assert (
        len(experimental_rows) >= 3
    ), f"Experimental returned too few packages: {len(experimental_rows)}"

    classic_names = {r["component"] for r in classic_rows}
    experimental_names = {r["component"] for r in experimental_rows}
    missing = classic_names - experimental_names
    assert not missing, f"Experimental is missing packages found by classic: {missing}"
