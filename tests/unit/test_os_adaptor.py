# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import io
import tarfile
from unittest.mock import Mock

import pytest
import pytest_mock
import requests

from dd_license_attribution.adaptors.os import (
    DOWNLOAD_CHUNK_SIZE_BYTES,
    download_url,
    extract_tar_gz,
    normalize_path,
    read_tar_gz_text_file,
)


def _mock_response(chunks: list[bytes], headers: dict[str, str] | None = None) -> Mock:
    response = Mock()
    response.headers = headers or {}
    response.iter_content.return_value = chunks
    return response


def _assert_download_request(mock_get: Mock, url: str, user_agent: str) -> None:
    mock_get.assert_called_once_with(
        url,
        allow_redirects=True,
        headers={"User-Agent": user_agent},
        stream=True,
        timeout=30,
    )


def _tar_gz_with_member(member: tarfile.TarInfo) -> bytes:
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        archive.addfile(member)
    return archive_bytes.getvalue()


def _tar_gz_with_files(files: dict[str, bytes]) -> bytes:
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return archive_bytes.getvalue()


def test_download_url_streams_response_and_closes(
    mocker: pytest_mock.MockFixture,
) -> None:
    response = _mock_response([b"crate", b"", b" archive"])
    mock_get = mocker.patch(
        "dd_license_attribution.adaptors.os.requests.get",
        return_value=response,
    )

    result = download_url(
        "https://example.test/crate/download",
        user_agent="test-agent",
        max_bytes=20,
    )

    assert result == b"crate archive"
    _assert_download_request(
        mock_get,
        "https://example.test/crate/download",
        "test-agent",
    )
    response.raise_for_status.assert_called_once_with()
    response.iter_content.assert_called_once_with(chunk_size=DOWNLOAD_CHUNK_SIZE_BYTES)
    response.close.assert_called_once_with()


def test_download_url_rejects_content_length_over_limit(
    mocker: pytest_mock.MockFixture,
) -> None:
    response = _mock_response([], headers={"Content-Length": "21"})
    mock_get = mocker.patch(
        "dd_license_attribution.adaptors.os.requests.get",
        return_value=response,
    )

    with pytest.raises(OSError, match="exceeds maximum size"):
        download_url(
            "https://example.test/crate/download",
            user_agent="test-agent",
            max_bytes=20,
        )

    _assert_download_request(
        mock_get,
        "https://example.test/crate/download",
        "test-agent",
    )
    response.raise_for_status.assert_called_once_with()
    response.iter_content.assert_not_called()
    response.close.assert_called_once_with()


def test_download_url_rejects_stream_over_limit(
    mocker: pytest_mock.MockFixture,
) -> None:
    response = _mock_response([b"crate", b" archive"])
    mock_get = mocker.patch(
        "dd_license_attribution.adaptors.os.requests.get",
        return_value=response,
    )

    with pytest.raises(OSError, match="exceeds maximum size"):
        download_url(
            "https://example.test/crate/download",
            user_agent="test-agent",
            max_bytes=10,
        )

    _assert_download_request(
        mock_get,
        "https://example.test/crate/download",
        "test-agent",
    )
    response.raise_for_status.assert_called_once_with()
    response.iter_content.assert_called_once_with(chunk_size=DOWNLOAD_CHUNK_SIZE_BYTES)
    response.close.assert_called_once_with()


def test_download_url_wraps_request_errors(mocker: pytest_mock.MockFixture) -> None:
    mock_get = mocker.patch(
        "dd_license_attribution.adaptors.os.requests.get",
        side_effect=requests.Timeout("timed out"),
    )

    with pytest.raises(OSError, match="Failed to download"):
        download_url(
            "https://example.test/crate/download",
            user_agent="test-agent",
        )

    _assert_download_request(
        mock_get,
        "https://example.test/crate/download",
        "test-agent",
    )


@pytest.mark.parametrize(
    "member_type",
    [
        tarfile.FIFOTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
    ],
)
def test_extract_tar_gz_rejects_special_members(member_type: bytes) -> None:
    member = tarfile.TarInfo("crate/special")
    member.type = member_type
    archive_content = _tar_gz_with_member(member)

    with pytest.raises(ValueError, match="Unsafe archive path: crate/special"):
        extract_tar_gz(archive_content, "/destination")


def test_extract_tar_gz_rejects_file_over_extracted_size_limit() -> None:
    archive_content = _tar_gz_with_files({"crate/large.txt": b"x" * 21})

    with pytest.raises(
        ValueError,
        match=(
            "Archive member crate/large.txt exceeds maximum extracted size "
            "of 20 bytes"
        ),
    ):
        extract_tar_gz(
            archive_content,
            "/destination",
            max_extracted_bytes=20,
        )


def test_extract_tar_gz_rejects_total_extracted_size_over_limit() -> None:
    archive_content = _tar_gz_with_files(
        {
            "crate/one.txt": b"x" * 10,
            "crate/two.txt": b"y" * 11,
        }
    )

    with pytest.raises(
        ValueError,
        match="Archive exceeds maximum extracted size of 20 bytes",
    ):
        extract_tar_gz(
            archive_content,
            "/destination",
            max_extracted_bytes=20,
        )


def test_read_tar_gz_text_file_reads_matching_member() -> None:
    archive_content = _tar_gz_with_files(
        {
            "crate/README.md": b"readme",
            "crate/Cargo.toml": b'[package]\nname = "crate"\n',
        }
    )

    result = read_tar_gz_text_file(archive_content, "/Cargo.toml")

    assert result == '[package]\nname = "crate"\n'


def test_read_tar_gz_text_file_returns_none_without_matching_member() -> None:
    archive_content = _tar_gz_with_files({"crate/README.md": b"readme"})

    result = read_tar_gz_text_file(archive_content, "/Cargo.toml")

    assert result is None


def test_read_tar_gz_text_file_rejects_oversized_member() -> None:
    archive_content = _tar_gz_with_files({"crate/Cargo.toml": b"x" * 21})

    with pytest.raises(ValueError, match="exceeds maximum size of 20 bytes"):
        read_tar_gz_text_file(
            archive_content,
            "/Cargo.toml",
            max_bytes=20,
        )


def test_read_tar_gz_text_file_rejects_invalid_size_limit() -> None:
    with pytest.raises(ValueError, match="max_bytes must be greater than zero"):
        read_tar_gz_text_file(b"archive", "/Cargo.toml", max_bytes=0)


def test_normalize_path_collapses_relative_segments() -> None:
    assert normalize_path("/project/patches/helper/../helper/.") == (
        "/project/patches/helper"
    )
