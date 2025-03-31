# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

"""Here we collect a set of OS wrappers and adaptors to be easily replaced during testing and debugging."""

from typing import Iterator
import os


def list_dir(path: str) -> list[str]:
    return os.listdir(path)


def run_command(command: str) -> int:
    return os.system(f"{command} >&2")


def path_exists(file_path: str) -> bool:
    return os.path.exists(file_path)


def create_dirs(path: str) -> None:
    os.makedirs(path, exist_ok=True)


def walk_directory(path: str) -> Iterator[tuple[str, list[str], list[str]]]:
    return os.walk(path)


def output_from_command(command: str) -> str:
    return os.popen(command).read()


def change_directory(dir_name: str) -> None:
    os.chdir(dir_name)


def get_current_working_directory() -> str:
    return os.getcwd()


def open_file(file_path: str) -> str:
    with open(file_path, "r") as file:
        return file.read()
