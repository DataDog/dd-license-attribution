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
    MAX_VALIDATED_REDIRECTS,
    _exceeds_content_length,
    download_bounded,
    fetch_bounded_validated,
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
    assert MAX_VALIDATED_REDIRECTS == 5


def _public_only(ip: str) -> bool:
    return ip == "93.184.216.34"


def _fake_pinned_responses(
    mocker: pytest_mock.MockFixture,
    responses: list[tuple[int, dict[str, str], list[bytes]]],
) -> tuple[Mock, list[Mock]]:
    """Patch the pinned transport with canned (status, headers, chunks) responses; track body reads."""
    consumed_mocks: list[Mock] = []
    remaining = list(responses)

    @contextlib.contextmanager
    def fake_stream(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
        ip_validator: object,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        status, response_headers, chunks = remaining.pop(0)
        tracked, consumed = _tracked_chunks(chunks)
        consumed_mocks.append(consumed)
        yield status, response_headers, tracked

    mock_stream = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_pinned_https_once",
        side_effect=fake_stream,
    )
    return mock_stream, consumed_mocks


def test_fetch_bounded_validated_follows_validated_redirects_without_reading_their_bodies(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_stream, consumed = _fake_pinned_responses(
        mocker,
        [
            (301, {"Location": "/moved?go-get=1"}, [b"redirect-body"]),
            (302, {"Location": "https://other.example/final"}, [b"more"]),
            (200, {"Content-Length": "4"}, [b"do", b"", b"ne"]),
        ],
    )
    validator = Mock()

    status, body = fetch_bounded_validated(
        "https://vanity.example/pkg?go-get=1",
        max_bytes=4,
        url_validator=validator,
        ip_validator=_public_only,
        user_agent="test-agent",
    )

    assert (status, body) == (200, b"done")
    assert [c.args[0] for c in validator.call_args_list] == [
        "https://vanity.example/pkg?go-get=1",
        "https://vanity.example/moved?go-get=1",
        "https://other.example/final",
    ]
    assert [c.args for c in mock_stream.call_args_list] == [
        (
            "https://vanity.example/pkg?go-get=1",
            {"User-Agent": "test-agent"},
            5,
            _public_only,
        ),
        (
            "https://vanity.example/moved?go-get=1",
            {"User-Agent": "test-agent"},
            5,
            _public_only,
        ),
        (
            "https://other.example/final",
            {"User-Agent": "test-agent"},
            5,
            _public_only,
        ),
    ]
    consumed[0].assert_not_called()
    consumed[1].assert_not_called()
    assert consumed[2].call_count == 3


def test_fetch_bounded_validated_returns_error_status_bodies_and_redirects_without_location(
    mocker: pytest_mock.MockFixture,
) -> None:
    _fake_pinned_responses(
        mocker,
        [
            (404, {}, [b"<meta go-import>"]),
            (304, {}, [b""]),
            (400, {"Location": "/ignored"}, [b"bad-request"]),
            (300, {"Location": "/chosen"}, [b"ignored"]),
            (200, {}, [b"x"]),
        ],
    )

    assert fetch_bounded_validated(
        "https://vanity.example/a",
        max_bytes=64,
        url_validator=Mock(),
        ip_validator=_public_only,
    ) == (404, b"<meta go-import>")
    assert fetch_bounded_validated(
        "https://vanity.example/b",
        max_bytes=64,
        url_validator=Mock(),
        ip_validator=_public_only,
    ) == (304, b"")
    assert fetch_bounded_validated(
        "https://vanity.example/c",
        max_bytes=64,
        url_validator=Mock(),
        ip_validator=_public_only,
    ) == (400, b"bad-request")
    assert fetch_bounded_validated(
        "https://vanity.example/d",
        max_bytes=1,
        url_validator=Mock(),
        ip_validator=_public_only,
    ) == (200, b"x")


def test_fetch_bounded_validated_stops_before_connecting_to_rejected_redirect(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_stream, _ = _fake_pinned_responses(
        mocker,
        [(302, {"Location": "https://127.1/admin"}, [b""])],
    )

    def validator(url: str) -> None:
        if "127.1" in url:
            raise ValueError("Numeric or non-public host")

    with pytest.raises(ValueError, match="Numeric or non-public host"):
        fetch_bounded_validated(
            "https://vanity.example/pkg",
            max_bytes=64,
            url_validator=validator,
            ip_validator=_public_only,
        )
    assert mock_stream.call_count == 1


def test_fetch_bounded_validated_rejects_initial_url_without_connecting(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_stream, _ = _fake_pinned_responses(mocker, [])

    with pytest.raises(ValueError, match="bad"):
        fetch_bounded_validated(
            "https://127.1/pkg",
            max_bytes=64,
            url_validator=Mock(side_effect=ValueError("bad")),
            ip_validator=_public_only,
        )
    mock_stream.assert_not_called()


def test_fetch_bounded_validated_limits_redirect_hops(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_stream, _ = _fake_pinned_responses(
        mocker,
        [(302, {"Location": f"/hop{i}"}, [b""]) for i in range(7)],
    )

    with pytest.raises(
        OSError, match="Too many redirects while downloading https://loop.example/start"
    ):
        fetch_bounded_validated(
            "https://loop.example/start",
            max_bytes=64,
            url_validator=Mock(),
            ip_validator=_public_only,
        )
    assert mock_stream.call_count == MAX_VALIDATED_REDIRECTS + 1


def test_fetch_bounded_validated_enforces_size_cap(
    mocker: pytest_mock.MockFixture,
) -> None:
    _fake_pinned_responses(
        mocker,
        [
            (200, {"Content-Length": "65"}, [b"x"]),
            (200, {}, [b"x" * 40, b"x" * 25]),
        ],
    )

    for _ in range(2):
        with pytest.raises(
            OSError,
            match=(
                r"^Download from https://vanity\.example/big "
                r"exceeds maximum size of 64 bytes$"
            ),
        ):
            fetch_bounded_validated(
                "https://vanity.example/big",
                max_bytes=64,
                url_validator=Mock(),
                ip_validator=_public_only,
            )


def test_fetch_bounded_validated_rejects_invalid_size_limit() -> None:
    with pytest.raises(ValueError) as exc_info:
        fetch_bounded_validated(
            "https://vanity.example/pkg",
            max_bytes=0,
            url_validator=Mock(),
            ip_validator=_public_only,
        )
    assert str(exc_info.value) == "max_bytes must be greater than zero"


def test_fetch_bounded_validated_caps_chunk_size_at_download_chunk_size(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_stream, _ = _fake_pinned_responses(mocker, [(200, {}, [b"ok"])])

    status, body = fetch_bounded_validated(
        "https://vanity.example/large",
        max_bytes=DOWNLOAD_CHUNK_SIZE_BYTES * 2,
        url_validator=Mock(),
        ip_validator=_public_only,
    )

    assert (status, body) == (200, b"ok")
    mock_stream.assert_called_once_with(
        "https://vanity.example/large",
        {"User-Agent": DDLA_USER_AGENT},
        DOWNLOAD_CHUNK_SIZE_BYTES,
        _public_only,
    )
