# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import contextlib
from collections.abc import Iterator
from unittest.mock import Mock

import pytest
import pytest_mock

from dd_license_attribution.utils.bounded_download import (
    DDLA_USER_AGENT,
    DOWNLOAD_CHUNK_SIZE_BYTES,
    MAX_DOWNLOAD_BYTES,
    _exceeds_content_length,
    download_bounded,
)


def _tracked_chunks(chunks: list[bytes]) -> tuple[Iterator[bytes], Mock]:
    consumed = Mock()

    def iterator() -> Iterator[bytes]:
        for chunk in chunks:
            consumed(chunk)
            yield chunk

    return iterator(), consumed


def test_download_bounded_joins_non_empty_chunks(
    mocker: pytest_mock.MockFixture,
) -> None:
    chunks, consumed = _tracked_chunks([b"crate", b"", b" archive"])
    mock_stream_url = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url",
        return_value=contextlib.nullcontext(({}, chunks)),
    )

    result = download_bounded(
        "https://example.test/crate/download",
        user_agent="test-agent",
        max_bytes=20,
    )

    assert result == b"crate archive"
    mock_stream_url.assert_called_once_with(
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
        DOWNLOAD_CHUNK_SIZE_BYTES,
    )
    consumed.assert_any_call(b"crate")
    consumed.assert_any_call(b"")
    consumed.assert_any_call(b" archive")
    assert consumed.call_count == 3


def test_download_bounded_rejects_content_length_over_limit_without_reading_chunks(
    mocker: pytest_mock.MockFixture,
) -> None:
    chunks, consumed = _tracked_chunks([b"crate"])
    mock_stream_url = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url",
        return_value=contextlib.nullcontext(({"Content-Length": "21"}, chunks)),
    )

    with pytest.raises(OSError, match="exceeds maximum size"):
        download_bounded(
            "https://example.test/crate/download",
            user_agent="test-agent",
            max_bytes=20,
        )

    mock_stream_url.assert_called_once_with(
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
        DOWNLOAD_CHUNK_SIZE_BYTES,
    )
    consumed.assert_not_called()


@pytest.mark.parametrize("content_length", [None, "not-a-number"])
def test_download_bounded_ignores_absent_or_invalid_content_length(
    mocker: pytest_mock.MockFixture,
    content_length: str | None,
) -> None:
    chunks, consumed = _tracked_chunks([b"crate"])
    headers = {} if content_length is None else {"Content-Length": content_length}
    mock_stream_url = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url",
        return_value=contextlib.nullcontext((headers, chunks)),
    )

    result = download_bounded(
        "https://example.test/crate/download",
        user_agent="test-agent",
        max_bytes=20,
    )

    assert result == b"crate"
    mock_stream_url.assert_called_once_with(
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
        DOWNLOAD_CHUNK_SIZE_BYTES,
    )
    consumed.assert_called_once_with(b"crate")


def test_download_bounded_rejects_cumulative_stream_over_limit(
    mocker: pytest_mock.MockFixture,
) -> None:
    chunks, consumed = _tracked_chunks([b"crate", b" archive"])
    mock_stream_url = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url",
        return_value=contextlib.nullcontext(({}, chunks)),
    )

    with pytest.raises(OSError, match="exceeds maximum size"):
        download_bounded(
            "https://example.test/crate/download",
            user_agent="test-agent",
            max_bytes=10,
        )

    mock_stream_url.assert_called_once_with(
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
        DOWNLOAD_CHUNK_SIZE_BYTES,
    )
    consumed.assert_any_call(b"crate")
    consumed.assert_any_call(b" archive")
    assert consumed.call_count == 2


def test_download_bounded_accepts_single_byte_limit(
    mocker: pytest_mock.MockFixture,
) -> None:
    chunks, consumed = _tracked_chunks([b"x"])
    mock_stream_url = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url",
        return_value=contextlib.nullcontext(({}, chunks)),
    )

    result = download_bounded(
        "https://example.test/crate/download",
        user_agent="test-agent",
        max_bytes=1,
    )

    assert result == b"x"
    mock_stream_url.assert_called_once_with(
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
        DOWNLOAD_CHUNK_SIZE_BYTES,
    )
    consumed.assert_called_once_with(b"x")


def test_download_bounded_rejects_invalid_size_limit() -> None:
    with pytest.raises(ValueError) as exc_info:
        download_bounded("https://example.test/crate/download", max_bytes=0)
    assert str(exc_info.value) == "max_bytes must be greater than zero"


def test_download_bounded_propagates_stream_url_oserror(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_stream_url = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url",
        side_effect=OSError("network unavailable"),
    )

    with pytest.raises(OSError, match="network unavailable"):
        download_bounded(
            "https://example.test/crate/download",
            user_agent="test-agent",
        )

    mock_stream_url.assert_called_once_with(
        "https://example.test/crate/download",
        {"User-Agent": "test-agent"},
        DOWNLOAD_CHUNK_SIZE_BYTES,
    )


def test_exceeds_content_length_parsing() -> None:
    assert _exceeds_content_length("21", 20)
    assert not _exceeds_content_length("20", 20)
    assert not _exceeds_content_length("not-a-number", 20)
    assert not _exceeds_content_length(None, 20)


def test_download_constants_are_pinned() -> None:
    assert DDLA_USER_AGENT == (
        "dd-license-attribution (https://github.com/DataDog/dd-license-attribution)"
    )
    assert DOWNLOAD_CHUNK_SIZE_BYTES == 1024 * 1024
    assert MAX_DOWNLOAD_BYTES == 100 * 1024 * 1024
