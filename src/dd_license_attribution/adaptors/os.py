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
MAX_EXTRACTED_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000


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


def download_url(
    url: str,
    user_agent: str = DDLA_USER_AGENT,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> bytes:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be greater than zero")

    response: requests.Response | None = None
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
        if response is not None:
            response.close()
    return b"".join(chunks)


def _is_safe_tar_member(member: tarfile.TarInfo, destination: str) -> bool:
    if not (member.isfile() or member.isdir()):
        return False

    if member.issym() or member.islnk():
        return False

    member_name = member.name.replace("\\", "/")
    if os.path.isabs(member_name) or ".." in member_name.split("/"):
        return False

    destination_abs = os.path.abspath(destination)
    member_target = os.path.abspath(os.path.join(destination_abs, member_name))
    return member_target == destination_abs or member_target.startswith(
        f"{destination_abs}{os.sep}"
    )


def extract_tar_gz(
    archive_content: bytes,
    destination: str,
    max_extracted_bytes: int = MAX_EXTRACTED_ARCHIVE_BYTES,
    max_members: int = MAX_ARCHIVE_MEMBERS,
) -> list[str]:
    if max_extracted_bytes <= 0:
        raise ValueError("max_extracted_bytes must be greater than zero")
    if max_members <= 0:
        raise ValueError("max_members must be greater than zero")

    try:
        with tarfile.open(fileobj=io.BytesIO(archive_content), mode="r:gz") as archive:
            members = archive.getmembers()
            if len(members) > max_members:
                raise ValueError(
                    f"Archive contains more than {max_members} members"
                )
            unsafe_members = [
                member.name
                for member in members
                if not _is_safe_tar_member(member, destination)
            ]
            if unsafe_members:
                raise ValueError(f"Unsafe archive path: {unsafe_members[0]}")

            extracted_bytes = 0
            for member in members:
                if member.isfile() and member.size > max_extracted_bytes:
                    raise ValueError(
                        f"Archive member {member.name} exceeds maximum extracted "
                        f"size of {max_extracted_bytes} bytes"
                    )
                extracted_bytes += member.size
                if extracted_bytes > max_extracted_bytes:
                    raise ValueError(
                        "Archive exceeds maximum extracted size "
                        f"of {max_extracted_bytes} bytes"
                    )

            archive.extractall(destination, members=members, filter="data")
            return [member.name for member in members]
    except tarfile.TarError as e:
        raise ValueError(f"Malformed gzip tar archive: {e}") from e


def read_tar_gz_text_file(
    archive_content: bytes,
    member_suffix: str,
    max_bytes: int = MAX_EXTRACTED_ARCHIVE_BYTES,
) -> str | None:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be greater than zero")

    try:
        with tarfile.open(fileobj=io.BytesIO(archive_content), mode="r:gz") as archive:
            for member in archive.getmembers():
                if not member.isfile() or not member.name.endswith(member_suffix):
                    continue
                if member.size > max_bytes:
                    raise ValueError(
                        f"Archive member {member.name} exceeds maximum size "
                        f"of {max_bytes} bytes"
                    )
                extracted_file = archive.extractfile(member)
                if extracted_file is None:
                    return None
                return extracted_file.read().decode("utf-8")
    except tarfile.TarError as e:
        raise ValueError(f"Malformed gzip tar archive: {e}") from e
    return None


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
