# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

"""Here we collect a set of OS wrappers and adaptors to be easily replaced during testing and debugging."""

import contextlib
import os
import subprocess
import tarfile
from collections.abc import Iterable, Iterator, Mapping

import requests

PATH_SEPARATOR = os.sep


def _merge_env(extra: dict[str, str] | None) -> dict[str, str] | None:
    if extra is None:
        return None
    merged = os.environ.copy()
    merged.update(extra)
    return merged


def get_env_var(name: str) -> str | None:
    return os.environ.get(name)


def list_dir(path: str) -> list[str]:
    return os.listdir(path)


def run_command(
    args: list[str],
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> int:
    try:
        result = subprocess.run(
            args,
            stdout=subprocess.DEVNULL,
            cwd=cwd,
            env=_merge_env(env),
            timeout=timeout,
        )
        return result.returncode
    except subprocess.TimeoutExpired:
        return 124


def path_exists(file_path: str) -> bool:
    return os.path.exists(file_path)


def create_dirs(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def walk_directory(path: str) -> Iterator[tuple[str, list[str], list[str]]]:
    return os.walk(path)


def output_from_command(
    args: list[str],
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> str:
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=_merge_env(env),
            timeout=timeout,
        )
        return result.stdout
    except subprocess.TimeoutExpired as e:
        raise OSError(f"Command timed out after {timeout} seconds: {args[0]}") from e


def change_directory(dir_name: str) -> None:
    os.chdir(dir_name)


def get_current_working_directory() -> str:
    return os.getcwd()


def open_file(file_path: str) -> str:
    try:
        with open(file_path, "r", encoding="utf-8") as file:
            return file.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, "r", encoding="utf-16") as file:
                return file.read()
        except UnicodeDecodeError:
            with open(file_path, "r", encoding=None) as file:
                return file.read()


def write_file(file_path: str, content: str) -> None:
    with open(file_path, "w", encoding="utf-8") as file:
        file.write(content)


def extract_tar_members(
    archive: tarfile.TarFile,
    members: Iterable[tarfile.TarInfo],
    destination: str,
) -> None:
    archive.extractall(destination, members=members, filter="data")


def absolute_path(path: str) -> str:
    return os.path.abspath(path)


def is_absolute_path(path: str) -> bool:
    return os.path.isabs(path)


@contextlib.contextmanager
def stream_url(
    url: str,
    headers: dict[str, str],
    chunk_size: int,
    timeout: int = 30,
) -> Iterator[tuple[Mapping[str, str], Iterator[bytes]]]:
    response: requests.Response | None = None
    try:
        response = requests.get(
            url,
            allow_redirects=True,
            headers=headers,
            stream=True,
            timeout=timeout,
        )
        response.raise_for_status()
        yield response.headers, response.iter_content(chunk_size=chunk_size)
    except requests.RequestException as e:
        raise OSError(f"Failed to download {url}: {e}") from e
    finally:
        if response is not None:
            response.close()


def is_dir(path: str) -> bool:
    return os.path.isdir(path)


def run_command_with_check(
    args: list[str],
    cwd: str | None = None,
    env: dict[str, str] | None = None,
    timeout: int | None = None,
) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr).

    Args:
        args: Command as list of arguments
        cwd: Working directory (if None, uses current directory)
        env: Extra environment variables to merge with current environment

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=_merge_env(env),
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        output = e.stdout if isinstance(e.stdout, str) else ""
        error_output = e.stderr if isinstance(e.stderr, str) else ""
        timeout_message = f"Command timed out after {timeout} seconds: {args[0]}"
        if error_output:
            error_output = f"{error_output}\n{timeout_message}"
        else:
            error_output = timeout_message
        return 124, output, error_output


def format_command_output(output: str, error_output: str) -> str:
    parts: list[str] = []
    if output.strip():
        parts.append(f"stdout:\n{output.strip()}")
    if error_output.strip():
        parts.append(f"stderr:\n{error_output.strip()}")
    return "\n".join(parts)


def path_join(path: str, *paths: str) -> str:
    return os.path.join(path, *paths)


def normalize_path(path: str) -> str:
    return os.path.normpath(path)
