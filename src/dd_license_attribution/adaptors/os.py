# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

"""Here we collect a set of OS wrappers and adaptors to be easily replaced during testing and debugging."""

import io
import os
import subprocess
import tarfile
from collections.abc import Iterator

import requests

DDLA_USER_AGENT = (
    "dd-license-attribution (https://github.com/DataDog/dd-license-attribution)"
)
DOWNLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def _merge_env(extra: dict[str, str] | None) -> dict[str, str] | None:
    if extra is None:
        return None
    merged = os.environ.copy()
    merged.update(extra)
    return merged


def list_dir(path: str) -> list[str]:
    return os.listdir(path)


def run_command(
    args: list[str], cwd: str | None = None, env: dict[str, str] | None = None
) -> int:
    result = subprocess.run(
        args, stdout=subprocess.DEVNULL, cwd=cwd, env=_merge_env(env)
    )
    return result.returncode


def path_exists(file_path: str) -> bool:
    return os.path.exists(file_path)


def create_dirs(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def walk_directory(path: str) -> Iterator[tuple[str, list[str], list[str]]]:
    return os.walk(path)


def output_from_command(
    args: list[str], cwd: str | None = None, env: dict[str, str] | None = None
) -> str:
    result = subprocess.run(
        args, capture_output=True, text=True, cwd=cwd, env=_merge_env(env)
    )
    return result.stdout


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


def download_url(
    url: str,
    user_agent: str = DDLA_USER_AGENT,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> bytes:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be greater than zero")

    try:
        response = requests.get(
            url,
            allow_redirects=True,
            headers={"User-Agent": user_agent},
            stream=True,
            timeout=30,
        )
        response.raise_for_status()
        content_length = response.headers.get("Content-Length")
        if content_length is not None:
            try:
                expected_bytes = int(content_length)
            except ValueError:
                expected_bytes = 0
            if expected_bytes > max_bytes:
                raise OSError(
                    f"Download from {url} exceeds maximum size of {max_bytes} bytes"
                )

        chunks: list[bytes] = []
        downloaded_bytes = 0
        for chunk in response.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE_BYTES):
            if not chunk:
                continue
            downloaded_bytes += len(chunk)
            if downloaded_bytes > max_bytes:
                raise OSError(
                    f"Download from {url} exceeds maximum size of {max_bytes} bytes"
                )
            chunks.append(chunk)
    except requests.RequestException as e:
        raise OSError(f"Failed to download {url}: {e}") from e
    finally:
        if "response" in locals():
            response.close()
    return b"".join(chunks)


def _is_safe_tar_member(member: tarfile.TarInfo, destination: str) -> bool:
    if not (member.isfile() or member.isdir()):
        return False

    if member.issym() or member.islnk():
        return False

    if os.path.isabs(member.name) or ".." in member.name.split("/"):
        return False

    destination_abs = os.path.abspath(destination)
    member_target = os.path.abspath(os.path.join(destination_abs, member.name))
    return member_target == destination_abs or member_target.startswith(
        f"{destination_abs}{os.sep}"
    )


def extract_tar_gz(archive_content: bytes, destination: str) -> list[str]:
    with tarfile.open(fileobj=io.BytesIO(archive_content), mode="r:gz") as archive:
        members = archive.getmembers()
        unsafe_members = [
            member.name
            for member in members
            if not _is_safe_tar_member(member, destination)
        ]
        if unsafe_members:
            raise ValueError(f"Unsafe archive path: {unsafe_members[0]}")

        archive.extractall(destination, members=members)
        return [member.name for member in members]


def is_dir(path: str) -> bool:
    return os.path.isdir(path)


def run_command_with_check(
    args: list[str], cwd: str | None = None, env: dict[str, str] | None = None
) -> tuple[int, str, str]:
    """Run a command and return (exit_code, stdout, stderr).

    Args:
        args: Command as list of arguments
        cwd: Working directory (if None, uses current directory)
        env: Extra environment variables to merge with current environment

    Returns:
        Tuple of (exit_code, stdout, stderr)
    """
    result = subprocess.run(
        args, capture_output=True, text=True, cwd=cwd, env=_merge_env(env)
    )
    return result.returncode, result.stdout, result.stderr


def format_command_output(output: str, error_output: str) -> str:
    parts: list[str] = []
    if output.strip():
        parts.append(f"stdout:\n{output.strip()}")
    if error_output.strip():
        parts.append(f"stderr:\n{error_output.strip()}")
    return "\n".join(parts)


def path_join(path: str, *paths: str) -> str:
    return os.path.join(path, *paths)
