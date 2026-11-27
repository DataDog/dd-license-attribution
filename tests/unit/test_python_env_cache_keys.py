# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from collections.abc import Iterator
from contextlib import ExitStack
from datetime import datetime
from unittest.mock import Mock, call, patch

import pytest

from dd_license_attribution.artifact_management.python_env_manager import (
    PythonEnvManager,
)

BASE = "/tmp/" + "a" * 170
MODULE = "dd_license_attribution.artifact_management."


@pytest.fixture
def environment_mocks() -> Iterator[dict[str, Mock]]:
    targets = {
        "exists": "artifact_manager.path_exists",
        "initial_dirs": "artifact_manager.list_dir",
        "now": "artifact_manager.get_datetime_now",
        "dirs": "python_env_manager.list_dir",
        "cached": "python_env_manager.path_exists",
        "chdir": "python_env_manager.change_directory",
        "run": "python_env_manager.run_command",
    }
    with ExitStack() as stack:
        mocks = {
            name: stack.enter_context(patch(MODULE + target))
            for name, target in targets.items()
        }
        mocks["exists"].return_value = True
        mocks["initial_dirs"].return_value = []
        mocks["now"].return_value = datetime.fromisoformat("2026-11-27T12:00:00+00:00")
        mocks["dirs"].side_effect = lambda path: (
            [] if path == BASE else ["pyproject.toml"]
        )
        mocks["cached"].return_value = False
        mocks["run"].return_value = 0
        yield mocks
        mocks["exists"].assert_called_once_with(BASE)
        mocks["initial_dirs"].assert_called_once_with(BASE)
        mocks["now"].assert_called_once_with()


def test_long_checkout_path_has_bounded_environment_components(
    environment_mocks: dict[str, Mock],
) -> None:
    project = BASE + "/20261127_120000Z/owner-repo/.checkout-" + "b" * 32

    def execute(args: list[str]) -> int:
        if args[:3] == ["python", "-m", "venv"]:
            assert all(len(part.encode("utf-8")) <= 255 for part in args[3].split("/"))
        return 0

    environment_mocks["run"].side_effect = execute
    manager = PythonEnvManager(BASE)
    result = manager.get_environment(project)
    assert result is not None
    assert "/.python-env-v2/" in result
    environment_mocks["run"].assert_has_calls(
        [
            call(["python", "-m", "venv", result]),
            call([result + "/bin/python", "-m", "pip", "install", "."]),
        ]
    )
    environment_mocks["chdir"].assert_has_calls([call(project), call(project)])


def test_previously_colliding_project_paths_have_distinct_environments(
    environment_mocks: dict[str, Mock],
) -> None:
    manager = PythonEnvManager(BASE)
    first = manager.get_environment("a/b")
    second = manager.get_environment("a_b")
    assert first is not None and second is not None and first != second
    environment_mocks["run"].assert_has_calls(
        [
            call(["python", "-m", "venv", first]),
            call([first + "/bin/python", "-m", "pip", "install", "."]),
            call(["python", "-m", "venv", second]),
            call([second + "/bin/python", "-m", "pip", "install", "."]),
        ]
    )


def test_namespaced_environment_cache_hit_skips_creation(
    environment_mocks: dict[str, Mock],
) -> None:
    environment_mocks["dirs"].side_effect = lambda path: (
        ["20261127_120000Z"] if path == BASE else ["pyproject.toml"]
    )
    environment_mocks["cached"].side_effect = (
        lambda path: "/.python-env-v2/" in path and path.endswith("_virtualenv")
    )
    manager = PythonEnvManager(BASE)
    result = manager.get_environment("project")
    assert result is not None
    environment_mocks["run"].assert_called_once_with(
        [result + "/bin/python", "-m", "pip", "install", "."]
    )
    environment_mocks["cached"].assert_any_call(result)
