# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import hashlib
from datetime import datetime
from unittest.mock import call

import pytest
from pytest_mock import MockFixture

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.python_env_manager import (
    MARKER_ENVIRONMENT_SNIPPET,
    PythonEnvManager,
)

LOCK_CONTENT = (
    'lock-version = "1.0"\n[[packages]]\nname = "requests"\nversion = "2.32.5"\n'
)
LOCK_MARKER = f"v3:{hashlib.sha256(LOCK_CONTENT.encode('utf-8')).hexdigest()}"
LOCK_DEPS = '[["requests", "2.32.5"]]'
# Marker format written by older sync code (no version prefix): must not
# be accepted as a match by the current sync.
OLD_LOCK_MARKER = hashlib.sha256(LOCK_CONTENT.encode("utf-8")).hexdigest()


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
    "py_file,buildable",
    [
        ("requirements.txt", False),
        ("setup.py", True),
        ("setup.cfg", False),
        ("pyproject.toml", True),
        ("Pipfile", False),
        ("Pipfile.lock", False),
    ],
)
def test_python_env_is_created_if_python_project_detected_and_not_cached(
    mocker: MockFixture, py_file: str, buildable: bool
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
    expected_calls = [
        mocker.call(
            [
                "python",
                "-m",
                "venv",
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv",
            ]
        )
    ]
    if buildable:
        # Only projects with a build manifest (pyproject.toml/setup.py) can
        # be installed with `pip install .`
        expected_calls.append(
            mocker.call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    ".",
                ]
            )
        )
    run_command_mock.assert_has_calls(expected_calls)


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
        side_effect=[["setup.py", "test.py", "pylock.toml"], ["20220101_000000Z"]],
    )
    python_env_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        return_value=True,
    )
    # The virtualenv is already synced to the lockfile (marker matches its
    # sha256): the cache check and the marker check both pass.
    python_env_open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        side_effect=[LOCK_CONTENT, LOCK_MARKER],
    )
    python_env_write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
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
    python_env_path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
        ]
    )
    python_env_open_file_mock.assert_has_calls(
        [
            call("pylock.toml"),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
        ]
    )
    python_env_write_file_mock.assert_not_called()
    chdir_mock.assert_called_once_with(resource_path)
    # Environment already synced: no uninstall/install commands are run
    run_command_mock.assert_not_called()


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
        side_effect=[["setup.py", "test.py", "pylock.toml"], ["20220101_000000Z"]],
    )
    # Lock present, but a fresh virtualenv has no sync marker. The cache
    # check for the old virtualenv comes first in the path_exists sequence.
    python_env_path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[True, False],
    )
    python_env_open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=LOCK_CONTENT,
    )
    python_env_write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    python_env_output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "",
            '[{"name": "requests", "version": "2.32.5"}, {"name": "pip", "version": "26.2.1"}]',
        ],
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
    python_env_path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            call(
                "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
        ]
    )
    python_env_open_file_mock.assert_called_once_with("pylock.toml")
    # Nothing to prune in the fresh environment (pip freeze is empty)
    python_env_output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )
    python_env_write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                LOCK_DEPS,
            ),
            call(
                "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                LOCK_MARKER,
            ),
        ]
    )
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    run_command_mock.assert_has_calls(
        [
            mocker.call(
                [
                    "python",
                    "-m",
                    "venv",
                    "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv",
                ]
            ),
            mocker.call(
                [
                    "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            mocker.call(
                [
                    "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )


def test_get_dependencies_gets_full_list(mocker: MockFixture) -> None:
    """An unsynced environment enumerates whatever pip list reports, unfiltered.

    pip appears in the mock output to pin that the unpinned path never
    name-filters it: the bootstrap-copy exclusion is the lockfile
    enumeration's job, not the pip-list path's.
    """
    output_from_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        return_value='[{ "name": "pytest", "version":"8.3.4"}, {"name":"pip", "version":"26.2.1"}, {"name":"pytest-cov", "version":"6.0.0"}]',
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        return_value=False,
    )

    venv_path = "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
    dependencies = PythonEnvManager.get_dependencies(venv_path)
    assert dependencies == [
        ("pytest", "8.3.4"),
        ("pip", "26.2.1"),
        ("pytest-cov", "6.0.0"),
    ]

    output_from_command_mock.assert_called_once_with(
        [
            "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
            "list",
            "--format=json",
        ]
    )
    path_exists_mock.assert_called_once_with(
        "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
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
        [
            "python",
            "-m",
            "venv",
            "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv",
        ]
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
                [
                    "python",
                    "-m",
                    "venv",
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv",
                ]
            ),
            mocker.call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    ".",
                ]
            ),
        ]
    )


def test_python_env_prunes_stale_packages_before_lockfile_install(
    mocker: MockFixture,
) -> None:
    """A cached env with stale packages from an unpinned install is pruned before the lock install."""
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T10:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], ["20220101_000000Z"]],
    )
    # Lock present, cached env found, no sync marker yet: the cache check
    # comes first in the path_exists sequence.
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[True, False],
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=LOCK_CONTENT,
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    # The cached env holds a stale unpinned package, a direct reference
    # left by a previous `pip install .` of the scanned project itself, and
    # the setuptools that some Python versions seed into fresh venvs (listed
    # only because of pip freeze --all). pip itself is listed but must not
    # be removed from its own environment.
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "stale-package==1.0\nscanned-project @ file:///tmp/project\n"
            "pip==26.2.1\nsetuptools==65.5.0",
            '[{"name": "requests", "version": "2.32.5"}, {"name": "pip", "version": "26.2.1"}]',
        ],
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
    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
        ]
    )
    chdir_mock.assert_called_once_with(resource_path)
    open_file_mock.assert_called_once_with("pylock.toml")
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )
    run_command_mock.assert_has_calls(
        [
            # The stale package, the direct reference and the seeded
            # setuptools are pruned first - pip itself is kept
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "uninstall",
                    "-y",
                    "stale-package",
                    "scanned-project",
                    "setuptools",
                ]
            ),
            # ...then a PEP 751 capable pip is ensured before the lock install
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
    write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                LOCK_DEPS,
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                LOCK_MARKER,
            ),
        ]
    )


def test_python_env_falls_back_to_unpinned_install_when_lockfile_install_fails(
    mocker: MockFixture,
) -> None:
    """When the pylock.toml install fails (e.g. pip without PEP 751 support), fall back with a warning."""
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T00:00:00+00:00")],
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
        side_effect=[["test.py", "pyproject.toml", "pylock.toml"], []],
    )
    # Lock present, fresh env (no cache dir listing), no sync marker: the
    # marker check fails, and the failed lock install re-checks the deps
    # sidecar for invalidation (absent).
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[False, False],
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=LOCK_CONTENT,
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "",
            '[{"name": "requests", "version": "2.32.5"}, {"name": "pip", "version": "26.2.1"}]',
        ],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    # venv creation succeeds, the pip upgrade succeeds, the lockfile
    # install fails, the unpinned install succeeds
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        side_effect=[0, 0, 1, 0],
    )
    logger_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.logger"
    )

    python_env_manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"

    env_path = python_env_manager.get_environment(resource_path)

    assert env_path is not None
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
            ),
        ]
    )
    open_file_mock.assert_called_once_with("pylock.toml")
    output_mock.assert_called_once_with(
        [
            "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
            "-m",
            "pip",
            "freeze",
            "--all",
        ]
    )
    run_command_mock.assert_has_calls(
        [
            # A PEP 751 capable pip is ensured before the lock install
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
            # The failed lockfile install falls back to an unpinned install
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    ".",
                ]
            ),
        ]
    )
    logger_mock.warning.assert_called_once_with(
        "Failed to install dependencies from pylock.toml (requires a "
        "pip with PEP 751 lockfile support and wheels matching this "
        "platform); falling back to an unpinned install, so "
        "dependency enumeration may not be reproducible"
    )
    # No marker is written when the lockfile could not be installed
    write_file_mock.assert_not_called()


def test_python_env_resyncs_when_marker_file_is_unreadable(
    mocker: MockFixture,
) -> None:
    """An unreadable sync marker is treated as unsynced: the sync proceeds."""
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T10:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], ["20220101_000000Z"]],
    )
    # Lock present, cached env found, marker and deps files exist but the
    # marker is unreadable
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[True, True, True],
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        side_effect=[LOCK_CONTENT, OSError("corrupted marker")],
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "",
            '[{"name": "requests", "version": "2.32.5"}, {"name": "pip", "version": "26.2.1"}]',
        ],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )
    logger_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.logger"
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
    chdir_mock.assert_called_once_with(resource_path)
    # The unreadable marker logs a debug message and the sync proceeds:
    # lockfile install runs and a fresh marker is written
    logger_mock.debug.assert_called_once()
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
    write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                LOCK_DEPS,
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                LOCK_MARKER,
            ),
        ]
    )
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )
    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
            ),
        ]
    )


def test_python_env_recreates_virtualenv_when_prune_fails(
    mocker: MockFixture,
) -> None:
    """When the prune of stale packages fails, the virtualenv is recreated before the lock install."""
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T10:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], ["20220101_000000Z"]],
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[True, False],
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=LOCK_CONTENT,
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "stale-package==1.0",
            '[{"name": "requests", "version": "2.32.5"}, {"name": "pip", "version": "26.2.1"}]',
        ],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    # The uninstall of stale packages fails, the venv recreation, the pip
    # upgrade and the lockfile install succeed
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        side_effect=[1, 0, 0, 0],
    )
    logger_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.logger"
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
    chdir_mock.assert_called_once_with(resource_path)
    open_file_mock.assert_called_once_with("pylock.toml")
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )
    run_command_mock.assert_has_calls(
        [
            # The prune of the stale package fails...
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "uninstall",
                    "-y",
                    "stale-package",
                ]
            ),
            # ...so the virtualenv is recreated clean...
            call(
                [
                    "python",
                    "-m",
                    "venv",
                    "--clear",
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv",
                ]
            ),
            # ...the recreated (bundled) pip is upgraded to a PEP 751
            # capable version...
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            # ...and the lockfile install starts from the clean environment
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
    # The recreated environment holds exactly the pinned closure, so the
    # marker is written
    write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                LOCK_DEPS,
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                LOCK_MARKER,
            ),
        ]
    )
    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
        ]
    )
    logger_mock.warning.assert_called_once_with(
        "Failed to prune existing packages from %s; recreating the "
        "virtualenv so the next install starts from a clean environment",
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv",
    )


def test_python_env_lock_only_project_degrades_gracefully_when_lock_install_fails(
    mocker: MockFixture,
) -> None:
    """A lock-only project (no build manifest) never runs `pip install .` - it degrades with a warning."""
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T00:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], []],
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[False, False],
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=LOCK_CONTENT,
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "",
            '[{"name": "requests", "version": "2.32.5"}, {"name": "pip", "version": "26.2.1"}]',
        ],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    # venv creation and pip upgrade succeed, the lockfile install fails
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        side_effect=[0, 0, 1],
    )
    logger_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.logger"
    )

    python_env_manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"

    # The environment is returned (no PyEnvRuntimeError): a lock-only project
    # has no build backend for `pip install .`
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
    open_file_mock.assert_called_once_with("pylock.toml")
    output_mock.assert_called_once_with(
        [
            "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
            "-m",
            "pip",
            "freeze",
            "--all",
        ]
    )
    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
            ),
        ]
    )
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "python",
                    "-m",
                    "venv",
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
    # No unpinned fallback for a lock-only project: a warning explains the
    # degraded enumeration, and no marker is written
    logger_mock.warning.assert_has_calls(
        [
            call(
                "Failed to install dependencies from pylock.toml (requires a "
                "pip with PEP 751 lockfile support and wheels matching this "
                "platform); falling back to an unpinned install, so "
                "dependency enumeration may not be reproducible"
            ),
            mocker.call(
                "Could not install the pinned dependencies from pylock.toml "
                "for %s and the project has no build manifest "
                "(pyproject.toml/setup.py) for an unpinned install; "
                "dependency enumeration may be incomplete",
                resource_path,
            ),
        ]
    )
    write_file_mock.assert_not_called()


def test_python_env_resyncs_env_marked_by_older_sync_format(
    mocker: MockFixture,
) -> None:
    """A marker from a different sync-semantics generation is not accepted: the sync re-runs.

    This pins the mechanism that makes bumping LOCK_SYNC_MARKER_VERSION safe:
    a marker whose content does not carry the current version prefix never
    matches, so environments synced by a previous generation of the sync
    logic are re-synced once under the current semantics.
    """
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T10:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], ["20220101_000000Z"]],
    )
    # Cache check passes; the marker exists but holds the old (unversioned)
    # format and its deps sidecar is missing, so it must not be accepted as
    # a match: the environment is re-synced under the current semantics.
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[True, True, False],
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        side_effect=[LOCK_CONTENT, OLD_LOCK_MARKER],
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    # The old sync left setuptools seeded in the environment (3.11-style
    # venv); the current prune removes it.
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "setuptools==65.5.0",
            '[{"name": "requests", "version": "2.32.5"}, {"name": "pip", "version": "26.2.1"}]',
        ],
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
    chdir_mock.assert_called_once_with(resource_path)
    # The missing deps sidecar short-circuits the marker acceptance before
    # the marker is even read: only the lockfile is opened
    open_file_mock.assert_called_once_with("pylock.toml")
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )
    run_command_mock.assert_has_calls(
        [
            # The stale setuptools left by the older sync is pruned
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "uninstall",
                    "-y",
                    "setuptools",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
    # The new versioned marker is written
    write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                LOCK_DEPS,
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                LOCK_MARKER,
            ),
        ]
    )
    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
            ),
        ]
    )


def test_get_dependencies_enumerates_from_the_lockfile_for_synced_envs(
    mocker: MockFixture,
) -> None:
    """A synced environment enumerates the deps file written from the lockfile - no pip list call.

    The venv's bootstrap pip is not in the lockfile, so it does not leak into
    the SBOM; a pip the project genuinely declares IS in the lockfile and
    stays in the enumeration.
    """
    output_from_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command"
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        return_value=True,
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value='[["requests", "2.32.5"], ["pip", "25.3"]]',
    )
    venv_path = "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv"

    dependencies = PythonEnvManager.get_dependencies(venv_path)

    # The declared pip is kept; the bootstrap pip (not in the lockfile) is
    # absent because the enumeration comes from the lockfile deps file
    assert dependencies == [("requests", "2.32.5"), ("pip", "25.3")]
    path_exists_mock.assert_called_once_with(
        "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
    )
    open_file_mock.assert_called_once_with(
        "cache_dir/20220101_100000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
    )
    output_from_command_mock.assert_not_called()


def test_parse_locked_versions_returns_the_version_map() -> None:
    """The pylock.toml parser collects normalized names mapped to pinned versions."""
    lock_content = (
        'lock-version = "1.0"\n'
        "[[packages]]\n"
        'name = "requests"\n'
        'version = "2.32.5"\n'
        "[[packages]]\n"
        'name = "typing_extensions"\n'
        'version = "4.1.0"\n'
    )
    versions = PythonEnvManager._parse_locked_versions(lock_content)
    assert versions == {"requests": "2.32.5", "typing-extensions": "4.1.0"}


def test_synced_environment_writes_the_deps_enumeration(mocker: MockFixture) -> None:
    """After a successful lock sync, the deps file drives the enumeration."""
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T00:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], []],
    )
    # Fresh env: no marker; then get_dependencies finds the deps file
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[False, True],
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        side_effect=[LOCK_CONTENT, LOCK_DEPS],
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "",
            '[{"name": "requests", "version": "2.32.5"}, {"name": "pip", "version": "26.2.1"}]',
        ],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )

    manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"

    env_path = manager.get_environment(resource_path)
    assert env_path is not None

    dependencies = PythonEnvManager.get_dependencies(env_path)
    assert dependencies == [("requests", "2.32.5")]
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    open_file_mock.assert_has_calls(
        [
            call("pylock.toml"),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
            ),
        ]
    )
    write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                LOCK_DEPS,
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                LOCK_MARKER,
            ),
        ]
    )
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
            ),
        ]
    )
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])


def test_failed_resync_invalidates_the_stale_deps_sidecar(mocker: MockFixture) -> None:
    """A failed re-sync removes the stale deps sidecar so the enumeration falls back to pip list.

    Without the invalidation, a previously-synced environment whose lock
    install fails would keep enumerating the OLD lockfile's packages while
    the environment actually holds an unpinned install.
    """
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T10:00:00+00:00")],
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
        side_effect=[
            ["test.py", "pyproject.toml", "pylock.toml"],
            ["20220101_000000Z"],
        ],
    )
    # Cached env; the marker and a stale deps sidecar both exist, but the
    # marker holds the PREVIOUS lockfile's hash (the lockfile changed), so
    # the acceptance fails and the sync re-runs.
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[True, True, True, True, False],
    )
    stale_marker = (
        f"v3:{hashlib.sha256(b'old-lock-content'.decode().encode()).hexdigest()}"
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        side_effect=[LOCK_CONTENT, stale_marker, '[["stale-pkg", "1.0"]]'],
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    remove_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.remove_file"
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=["", '[{"name": "fresh-pkg", "version": "2.0.0"}]'],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    # pip upgrade succeeds, the changed lockfile install fails, the unpinned
    # install succeeds
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        side_effect=[0, 1, 0],
    )
    logger_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.logger"
    )

    manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"

    env_path = manager.get_environment(resource_path)
    assert env_path is not None

    # The enumeration fell back to pip list (the stale sidecar was removed),
    # NOT the old lockfile's packages
    dependencies = PythonEnvManager.get_dependencies(env_path)
    assert dependencies == [("fresh-pkg", "2.0.0")]
    remove_file_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
    )
    # No marker or deps file is written by the failed sync
    write_file_mock.assert_not_called()
    logger_mock.warning.assert_has_calls(
        [
            mocker.call(
                "Failed to install dependencies from pylock.toml (requires a "
                "pip with PEP 751 lockfile support and wheels matching this "
                "platform); falling back to an unpinned install, so "
                "dependency enumeration may not be reproducible"
            )
        ]
    )
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    # Cached env: only the install step changes directory
    chdir_mock.assert_called_once_with(resource_path)
    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
            ),
        ]
    )
    open_file_mock.assert_has_calls(
        [
            call("pylock.toml"),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
        ]
    )
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    ".",
                ]
            ),
        ]
    )
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )


def test_sidecar_matches_lock_names_across_separator_styles(
    mocker: MockFixture,
) -> None:
    """PEP 503 normalization: typing-extensions (lock) matches typing_extensions (pip list).

    pip list reports the installed-distribution name with underscores while
    the lockfile pins the canonical hyphenated name; without normalization
    the package would vanish from the sidecar and from the SBOM.
    """
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T00:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], []],
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[False],
    )
    lock_content = (
        'lock-version = "1.0"\n'
        "[[packages]]\n"
        'name = "typing-extensions"\n'
        'version = "4.1.0"\n'
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=lock_content,
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "",
            '[{"name": "typing_extensions", "version": "4.1.0"}, {"name": "pip", "version": "26.2.1"}]',
        ],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )

    manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"
    env_path = manager.get_environment(resource_path)
    assert env_path is not None
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])

    # The underscored installed name matches the hyphenated lock name; the
    # bootstrap pip does not
    write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                '[["typing_extensions", "4.1.0"]]',
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                f"v3:{hashlib.sha256(lock_content.encode('utf-8')).hexdigest()}",
            ),
        ]
    )
    open_file_mock.assert_called_once_with("pylock.toml")
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    path_exists_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
    )


def test_malformed_lockfile_prunes_previously_synced_env(mocker: MockFixture) -> None:
    """A previously synced env is pruned when the lockfile becomes malformed TOML.

    Without the prune, the unpinned fallback enumeration (pip list) would
    report the stale closure of the OLD lockfile.
    """
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T10:00:00+00:00")],
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
        side_effect=[
            ["test.py", "pyproject.toml", "pylock.toml"],
            ["20220101_000000Z"],
        ],
    )
    # Cached env; the marker/deps sidecar exist but the lockfile no longer
    # parses (and the marker hash no longer matches, so the sync re-runs).
    # The 4th call is the invalidation re-checking the deps sidecar.
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[True, True, True, True],
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value="] not valid toml [",
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    remove_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.remove_file"
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        return_value="stale-pkg==1.0",
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )
    logger_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.logger"
    )

    manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"

    env_path = manager.get_environment(resource_path)
    assert env_path is not None

    # The stale closure is pruned, the sidecar invalidated, and the unpinned
    # fallback installs from the project manifest
    output_mock.assert_called_once_with(
        [
            "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
            "-m",
            "pip",
            "freeze",
            "--all",
        ]
    )
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "uninstall",
                    "-y",
                    "stale-pkg",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    ".",
                ]
            ),
        ]
    )
    remove_file_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
    )
    write_file_mock.assert_not_called()
    logger_mock.warning.assert_has_calls(
        [
            mocker.call(
                "Failed to parse pylock.toml; falling back to an unpinned "
                "install, so dependency enumeration may not be reproducible"
            )
        ]
    )
    # The lockfile is read, then the stale marker is read (its content does
    # not match the new lockfile hash, so the sync re-runs)
    open_file_mock.assert_has_calls(
        [
            call("pylock.toml"),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
        ]
    )
    chdir_mock.assert_called_once_with(resource_path)
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    path_exists_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps"
            ),
        ]
    )


def test_uncleanable_environment_raises(mocker: MockFixture) -> None:
    """When the prune fails AND the venv recreation fails, the sync raises instead of enumerating stale packages."""
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T00:00:00+00:00")],
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
        side_effect=[["test.py", "pyproject.toml", "pylock.toml"], []],
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[False],
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=LOCK_CONTENT,
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        return_value="stale-pkg==1.0",
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    # The uninstall fails and the venv recreation also fails
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        side_effect=[0, 1, 1],
    )
    logger_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.logger"
    )

    manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"

    with pytest.raises(Exception) as e:
        manager.get_environment(resource_path)
    assert (
        str(e.value)
        == "Failed to clean or recreate the Python virtualenv at cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv"
    )
    output_mock.assert_called_once_with(
        [
            "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
            "-m",
            "pip",
            "freeze",
            "--all",
        ]
    )
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "uninstall",
                    "-y",
                    "stale-pkg",
                ]
            ),
            call(
                [
                    "python",
                    "-m",
                    "venv",
                    "--clear",
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv",
                ]
            ),
        ]
    )
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    logger_mock.warning.assert_has_calls(
        [
            mocker.call(
                "Failed to prune existing packages from %s; recreating the "
                "virtualenv so the next install starts from a clean environment",
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv",
            )
        ]
    )
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    path_exists_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
    )
    open_file_mock.assert_called_once_with("pylock.toml")


def test_marker_gated_pip_entry_stays_excluded_from_the_sidecar(
    mocker: MockFixture,
) -> None:
    """A marker-gated pip entry does not leak the toolchain pip as a dependency.

    The lockfile pins pip==25.3 gated to an environment that does not apply
    here: pip does not install it, the venv keeps its (upgraded) toolchain
    pip, and the version comparison keeps it out of the sidecar.
    """
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T00:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], []],
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[False],
    )
    lock_content = (
        'lock-version = "1.0"\n'
        "[[packages]]\n"
        'name = "pip"\n'
        'version = "25.3"\n'
        "marker = \"python_version < '3.11'\"\n"
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=lock_content,
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "",
            '{"implementation_name": "cpython", "implementation_version": "3.14.7", "os_name": "posix", "platform_machine": "x86_64", "platform_release": "6.8.0", "platform_system": "Linux", "platform_version": "#1", "python_full_version": "3.14.7", "platform_python_implementation": "CPython", "python_version": "3.14", "sys_platform": "linux"}',
            '[{"name": "pip", "version": "26.2.1"}]',
        ],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )

    manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"
    env_path = manager.get_environment(resource_path)
    assert env_path is not None

    # The toolchain pip (26.2.1) does not match the gated pin (25.3): the
    # sidecar is empty of pip
    write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                "[]",
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                f"v3:{hashlib.sha256(lock_content.encode('utf-8')).hexdigest()}",
            ),
        ]
    )
    open_file_mock.assert_called_once_with("pylock.toml")
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    path_exists_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
    )
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-c",
                    MARKER_ENVIRONMENT_SNIPPET,
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )


def test_marker_gated_pip_with_matching_version_stays_excluded(
    mocker: MockFixture,
) -> None:
    """A marker-gated pip entry excluded by its marker stays out even when its pinned version equals the toolchain pip's.

    This is the version-coincidence corner: the gate is what excludes the
    entry, not a version mismatch.
    """
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T00:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], []],
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[False],
    )
    # pip==26.2.1, but gated to an environment that does not apply here
    lock_content = (
        'lock-version = "1.0"\n'
        "[[packages]]\n"
        'name = "pip"\n'
        'version = "26.2.1"\n'
        "marker = \"python_version < '3.11'\"\n"
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=lock_content,
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    # The toolchain pip happens to be exactly the gated pin's version
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "",
            '{"implementation_name": "cpython", "implementation_version": "3.14.7", "os_name": "posix", "platform_machine": "x86_64", "platform_release": "6.8.0", "platform_system": "Linux", "platform_version": "#1", "python_full_version": "3.14.7", "platform_python_implementation": "CPython", "python_version": "3.14", "sys_platform": "linux"}',
            '[{"name": "pip", "version": "26.2.1"}]',
        ],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )

    manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"
    env_path = manager.get_environment(resource_path)
    assert env_path is not None

    write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                "[]",
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                f"v3:{hashlib.sha256(lock_content.encode('utf-8')).hexdigest()}",
            ),
        ]
    )
    open_file_mock.assert_called_once_with("pylock.toml")
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    path_exists_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
    )
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-c",
                    MARKER_ENVIRONMENT_SNIPPET,
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )


def test_declared_pip_is_kept_in_the_sidecar(mocker: MockFixture) -> None:
    """A pip entry whose marker applies here pins the toolchain pip and is kept."""
    get_datetime_now_mock = mocker.patch(
        "dd_license_attribution.artifact_management.artifact_manager.get_datetime_now",
        side_effect=[datetime.fromisoformat("2022-01-01T00:00:00+00:00")],
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
        side_effect=[["test.py", "pylock.toml"], []],
    )
    path_exists_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.path_exists",
        side_effect=[False],
    )
    lock_content = (
        'lock-version = "1.0"\n'
        "[[packages]]\n"
        'name = "pip"\n'
        'version = "25.3"\n'
        "[[packages]]\n"
        'name = "requests"\n'
        'version = "2.32.5"\n'
    )
    open_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.open_file",
        return_value=lock_content,
    )
    write_file_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.write_file"
    )
    # The lock install placed the declared pip version
    output_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.output_from_command",
        side_effect=[
            "",
            '[{"name": "requests", "version": "2.32.5"}, {"name": "pip", "version": "25.3"}]',
        ],
    )
    chdir_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.change_directory"
    )
    run_command_mock = mocker.patch(
        "dd_license_attribution.artifact_management.python_env_manager.run_command",
        return_value=0,
    )

    manager = PythonEnvManager("cache_dir", 86400)
    resource_path = "cache_dir/20210901_000000Z/python_project"
    env_path = manager.get_environment(resource_path)
    assert env_path is not None

    write_file_mock.assert_has_calls(
        [
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-deps",
                '[["requests", "2.32.5"], ["pip", "25.3"]]',
            ),
            call(
                "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced",
                f"v3:{hashlib.sha256(lock_content.encode('utf-8')).hexdigest()}",
            ),
        ]
    )
    open_file_mock.assert_called_once_with("pylock.toml")
    chdir_mock.assert_has_calls([call(resource_path), call(resource_path)])
    get_datetime_now_mock.assert_called_once()
    artifact_path_exists_mock.assert_called_once_with("cache_dir")
    artifact_list_dir_mock.assert_called_once_with("cache_dir")
    python_env_list_dir_mock.assert_has_calls([call(resource_path), call("cache_dir")])
    path_exists_mock.assert_called_once_with(
        "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/.ddla-pylock-synced"
    )
    output_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "freeze",
                    "--all",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/pip",
                    "list",
                    "--format=json",
                ]
            ),
        ]
    )
    run_command_mock.assert_has_calls(
        [
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--upgrade",
                    "pip>=26.1",
                ]
            ),
            call(
                [
                    "cache_dir/20220101_000000Z/cache_dir_20210901_000000Z_python_project_virtualenv/bin/python",
                    "-m",
                    "pip",
                    "install",
                    "--no-deps",
                    "-r",
                    "pylock.toml",
                ]
            ),
        ]
    )
