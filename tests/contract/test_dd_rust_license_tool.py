# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import pytest

from dd_license_attribution.adaptors.os import get_env_var, run_command_with_check


def _run_dd_rust_license_tool(
    args: list[str], cwd: str | None = None
) -> tuple[int, str, str]:
    try:
        return run_command_with_check(["dd-rust-license-tool", *args], cwd=cwd)
    except OSError:
        if get_env_var("CI") == "true":
            raise
        pytest.skip("dd-rust-license-tool not installed")


def test_dd_rust_license_tool_version() -> None:
    exit_code, output, error_output = _run_dd_rust_license_tool(["--version"])

    assert exit_code == 0, error_output
    assert "dd-rust-license-tool" in output


def test_dd_rust_license_tool_dump_emits_expected_csv_header() -> None:
    fixture_path = "tests/fixtures/rust/sample_crate"

    exit_code, output, error_output = _run_dd_rust_license_tool(
        ["dump"],
        cwd=fixture_path,
    )

    assert exit_code == 0, error_output
    assert output.splitlines()[0] == "Component,Origin,License,Copyright"
    assert "serde" in output
    assert "anyhow" in output
    assert "itoa" not in output
    assert "cc" not in output
