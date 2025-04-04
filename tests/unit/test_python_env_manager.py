# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from datetime import datetime
from unittest.mock import call

import pytest
from pytest_mock import MockFixture

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.python_env_manager import (
    PythonEnvManager,
)


def test_python_env_is_not_created_if_not_python_project_detected(
    mocker: MockFixture,
) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[
            datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
        ],
    )
    artifact_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=[],
    )
    python_env_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.list_dir",
        return_value=["test.go"],
    )
    python_env_manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/not_python_project"
    env_path = python_env_manager.get_environment(resource_path)
    assert env_path is None
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_called_once_with(resource_path)


@pytest.mark.parametrize(
    "py_file",
    [
        ("requirements.txt"),
        ("setup.py"),
        ("setup.cfg"),
        ("pyproject.toml"),
        ("Pipfile"),
        ("Pipfile.lock"),
    ],
)
def test_python_env_is_created_if_python_project_detected_and_not_cached(
    mocker: MockFixture, py_file: str
) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[
            datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
        ],
    )
    artifact_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=[],
    )
    python_env_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.list_dir",
        side_effect=[["test.py", py_file], []],
    )

    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )

    python_env_manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"

    env_path = python_env_manager.get_environment(resource_path)

    assert (
        env_path
        == "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
    )
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    run_command_mock.assert_has_calls(
        [
            mocker.call(
                "python -m venv cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            mocker.call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python -m pip install ."
            ),
        ]
    )


def test_python_env_is_returned_if_python_project_detected_and_cached(
    mocker: MockFixture,
) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[
            datetime.fromisoformat("2022-01-01T10:00:00+00:00"),
        ],
    )
    artifact_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=["20220101_000000Z"],
    )
    python_env_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.list_dir",
        side_effect=[["setup.py", "test.py"], ["20220101_000000Z"]],
    )
    python_env_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        return_value=True,
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )
    python_env_manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"
    env_path = python_env_manager.get_environment(resource_path)
    assert (
        env_path
        == "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
    )
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    python_env_path_exists_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
    )
    chdir_mock.assert_called_once_with(resource_path)
    run_command_mock.assert_has_calls(
        [
            mocker.call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python -m pip install ."
            ),
        ]
    )


def test_python_env_is_created_if_python_project_detected_and_force_update(
    mocker: MockFixture,
) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[
            datetime.fromisoformat("2022-01-01T10:00:00+00:00"),
        ],
    )
    artifact_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=["20220101_000000Z"],
    )
    python_env_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.list_dir",
        side_effect=[["setup.py", "test.py"], ["20220101_000000Z"]],
    )
    python_env_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        return_value=True,
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )

    python_env_manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"
    env_path = python_env_manager.get_environment(resource_path, force_update=True)
    assert (
        env_path
        == "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
    )
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    python_env_path_exists_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
    )
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    run_command_mock.assert_has_calls(
        [
            mocker.call(
                "python -m venv cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            mocker.call(
                "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python -m pip install ."
            ),
        ]
    )


def test_get_dependencies_gets_full_list(mocker: MockFixture) -> None:
    output_from_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        return_value='[{ "name": "pytest", "version":"8.3.4"}, {"name":"pytest-cov", "version":"6.0.0"}]',
    )

    venv_path = "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
    dependencies = PythonEnvManager.get_dependencies(venv_path)
    assert dependencies == [("pytest", "8.3.4"), ("pytest-cov", "6.0.0")]

    output_from_command_mock.assert_called_once_with(
        "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip list --format=json"
    )


def test_fail_to_create_pyenv_throws(mocker: MockFixture) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[
            datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
        ],
    )
    artifact_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=[],
    )
    python_env_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.list_dir",
        side_effect=[["setup.py", "requirements.txt"], []],
    )

    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command"
    )
    run_command_mock.side_effect = [1]

    python_env_manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"

    with pytest.raises(Exception) as e:
        python_env_manager.get_environment(resource_path)
    assert str(e.value) == "Failed to create Python virtualenv"
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    chdir_mock.assert_called_once_with(resource_path)
    run_command_mock.assert_called_once_with(
        "python -m venv cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
    )


def test_fail_to_install_dependencies_in_pyenv_throws(mocker: MockFixture) -> None:
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[
            datetime.fromisoformat("2022-01-01T00:00:00+00:00"),
        ],
    )
    artifact_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.path_exists",
        return_value=True,
    )
    artifact_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.list_dir",
        return_value=[],
    )
    python_env_list_dir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.list_dir",
        side_effect=[["setup.py", "requirements.txt"], []],
    )

    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command"
    )
    run_command_mock.side_effect = [0, 1]

    python_env_manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"

    with pytest.raises(Exception) as e:
        python_env_manager.get_environment(resource_path)
    assert (
        str(e.value)
        == "Failed to install dependencies when creating Python virtualenv cache"
    )
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    run_command_mock.assert_has_calls(
        [
            mocker.call(
                "python -m venv cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            mocker.call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python -m pip install ."
            ),
        ]
    )
