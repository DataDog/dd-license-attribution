# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import subprocess
import tarfile
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
import pytest_mock
import requests

from dd_license_attribution.adaptors.os import (
    absolute_path,
    extract_tar_members,
    get_env_var,
    is_absolute_path,
    normalize_path,
    run_command,
    run_command_with_check,
    stream_url,
)


def _mock_response(chunks: list[bytes], headers: dict[str, str] | None = None) -> Mock:
    response = Mock()
    response.headers = headers or {}
    response.iter_content.return_value = iter(chunks)
    return response


def _assert_stream_request(mock_get: Mock, url: str, headers: dict[str, str]) -> None:
    mock_get.assert_called_once_with(
        url,
        allow_redirects=True,
        headers=headers,
        stream=True,
        timeout=30,
    )


def test_stream_url_yields_headers_and_chunks_then_closes(
    mocker: pytest_mock.MockFixture,
) -> None:
    response = _mock_response(
        [b"crate", b" archive"],
        headers={"Content-Length": "13"},
    )
    mock_get = mocker.patch(
        "dd_license_attribution.adaptors.os.requests.get",
        return_value=response,
    )

    with stream_url(
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
        1024,
    ) as (headers, chunks):
        result = b"".join(chunks)

    assert headers == {"Content-Length": "13"}
    assert result == b"crate archive"
    _assert_stream_request(
        mock_get,
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
    )
    response.raise_for_status.assert_called_once_with()
    response.iter_content.assert_called_once_with(chunk_size=1024)
    response.close.assert_called_once_with()


def test_stream_url_closes_response_when_body_iteration_fails(
    mocker: pytest_mock.MockFixture,
) -> None:
    def failing_chunks() -> Iterator[bytes]:
        raise requests.ConnectionError("connection lost")
        yield b"unreachable"

    response = _mock_response([])
    response.iter_content.return_value = failing_chunks()
    mock_get = mocker.patch(
        "dd_license_attribution.adaptors.os.requests.get",
        return_value=response,
    )

    with pytest.raises(OSError, match="Failed to download"):
        with stream_url(
            "https://example.test/crate/download",
            {"User-Agent": "test-agent"},
            1024,
        ) as (_, chunks):
            b"".join(chunks)

    _assert_stream_request(
        mock_get,
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
    )
    response.raise_for_status.assert_called_once_with()
    response.iter_content.assert_called_once_with(chunk_size=1024)
    response.close.assert_called_once_with()


def test_stream_url_wraps_request_errors(mocker: pytest_mock.MockFixture) -> None:
    mock_get = mocker.patch(
        "dd_license_attribution.adaptors.os.requests.get",
        side_effect=requests.Timeout("timed out"),
    )

    with pytest.raises(OSError, match="Failed to download"):
        with stream_url(
            "https://example.test/crate/download",
            {"User-Agent": "test-agent"},
            1024,
        ):
            pass

    _assert_stream_request(
        mock_get,
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
    )


def test_get_env_var_returns_environment_value(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_environ_get = mocker.patch(
        "dd_license_attribution.adaptors.os.os.environ.get",
        return_value="true",
    )

    result = get_env_var("CI")

    assert result == "true"
    mock_environ_get.assert_called_once_with("CI")


def test_extract_tar_members_delegates_to_extractall() -> None:
    archive = Mock(spec=tarfile.TarFile)
    members = [tarfile.TarInfo("crate")]

    extract_tar_members(archive, members, "/destination")

    archive.extractall.assert_called_once_with(
        "/destination",
        members=members,
        filter="data",
    )


def test_absolute_path_returns_os_absolute_path(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_abspath = mocker.patch(
        "dd_license_attribution.adaptors.os.os.path.abspath",
        return_value="/project/file.txt",
    )

    result = absolute_path("file.txt")

    assert result == "/project/file.txt"
    mock_abspath.assert_called_once_with("file.txt")


def test_is_absolute_path_returns_os_result(mocker: pytest_mock.MockFixture) -> None:
    mock_isabs = mocker.patch(
        "dd_license_attribution.adaptors.os.os.path.isabs",
        return_value=True,
    )

    result = is_absolute_path("/project/file.txt")

    assert result is True
    mock_isabs.assert_called_once_with("/project/file.txt")


def test_normalize_path_collapses_relative_segments() -> None:
    assert normalize_path("/project/patches/helper/../helper/.") == (
        "/project/patches/helper"
    )


def test_run_command_returns_timeout_exit_code(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_run = mocker.patch(
        "dd_license_attribution.adaptors.os.subprocess.run",
        side_effect=subprocess.TimeoutExpired(["slow"], timeout=1),
    )

    result = run_command(["slow"], timeout=1)

    assert result == 124
    mock_run.assert_called_once_with(
        ["slow"],
        stdout=subprocess.DEVNULL,
        cwd=None,
        env=None,
        timeout=1,
    )


def test_run_command_with_check_returns_timeout_details(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_run = mocker.patch(
        "dd_license_attribution.adaptors.os.subprocess.run",
        side_effect=subprocess.TimeoutExpired(["slow"], timeout=1),
    )

    exit_code, output, error_output = run_command_with_check(["slow"], timeout=1)

    assert exit_code == 124
    assert output == ""
    assert error_output == "Command timed out after 1 seconds: slow"
    mock_run.assert_called_once_with(
        ["slow"],
        capture_output=True,
        text=True,
        cwd=None,
        env=None,
        timeout=1,
    )
