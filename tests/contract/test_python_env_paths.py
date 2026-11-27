# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from pathlib import Path
from unittest.mock import call, patch

from dd_license_attribution.adaptors.os import run_command
from dd_license_attribution.artifact_management.python_env_manager import (
    PythonEnvManager,
)


def test_long_generated_checkout_can_create_and_reuse_a_real_virtualenv(
    tmp_path: Path,
) -> None:
    cache = tmp_path / ("a" * 170)
    cache.mkdir()
    manager = PythonEnvManager(str(cache))
    project = cache / manager.timestamped_dir / "owner-repo" / (".checkout-" + "b" * 32)
    project.mkdir(parents=True)
    (project / "pyproject.toml").write_text(
        '[project]\nname = "contract"\nversion = "0.0.0"\n'
    )

    def execute(args: list[str]) -> int:
        if args[:3] == ["python", "-m", "venv"]:
            return run_command(args)
        assert args[1:] == ["-m", "pip", "install", "."]
        return 0

    module = "dd_license_attribution.artifact_management.python_env_manager."
    with (
        patch(module + "run_command", side_effect=execute) as command,
        patch(module + "change_directory"),
    ):
        environment = manager.get_environment(str(project))
        assert environment is not None
        assert manager.get_environment(str(project)) == environment
        command.assert_has_calls(
            [
                call(["python", "-m", "venv", environment]),
                call([environment + "/bin/python", "-m", "pip", "install", "."]),
                call([environment + "/bin/python", "-m", "pip", "install", "."]),
            ]
        )
    assert (Path(environment) / "pyvenv.cfg").is_file()
    assert len(Path(environment).name.encode("utf-8")) <= 255
