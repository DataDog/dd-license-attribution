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

    with pytest.raises(
        OSError,
        match=r"^Download from https://example\.test/crate/download exceeds maximum size of 20 bytes$",
    ):
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

    with pytest.raises(
        OSError,
        match=r"^Download from https://example\.test/crate/download exceeds maximum size of 10 bytes$",
    ):
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


def test_download_bounded_validates_redirects_before_following(
    mocker: pytest_mock.MockFixture,
) -> None:
    chunks, consumed = _tracked_chunks([b"ok"])
    events: list[str] = []
    responses = iter(
        [
            (301, {"Location": "/pkg/?go-get=1"}, iter([])),
            (200, {}, chunks),
        ]
    )

    @contextlib.contextmanager
    def fake_stream_once(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        status_code, resp_headers, resp_chunks = next(responses)
        try:
            yield status_code, resp_headers, resp_chunks
        finally:
            events.append(f"close:{url}")

    def validator(target: str) -> None:
        events.append(f"validate:{target}")

    mock_stream_once = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url_once",
        side_effect=fake_stream_once,
    )
    mock_validator = Mock(side_effect=validator)

    result = download_bounded(
        "https://vanity.example/pkg?go-get=1",
        max_bytes=1024,
        redirect_validator=mock_validator,
    )

    assert result == b"ok"
    # First response closes before validator inspects the resolved redirect URL
    assert events == [
        "close:https://vanity.example/pkg?go-get=1",
        "validate:https://vanity.example/pkg/?go-get=1",
        "close:https://vanity.example/pkg/?go-get=1",
    ]
    mock_validator.assert_called_once_with("https://vanity.example/pkg/?go-get=1")
    assert mock_stream_once.call_args_list == [
        mocker.call(
            "https://vanity.example/pkg?go-get=1",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
        mocker.call(
            "https://vanity.example/pkg/?go-get=1",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
    ]
    consumed.assert_called_once_with(b"ok")


def test_download_bounded_aborts_on_rejected_redirect_without_requesting_target(
    mocker: pytest_mock.MockFixture,
) -> None:
    @contextlib.contextmanager
    def fake_stream_once(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        yield 302, {"Location": "http://127.0.0.1:8123/admin/reload"}, iter([])

    mock_stream_once = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url_once",
        side_effect=fake_stream_once,
    )
    validator = Mock(side_effect=ValueError("disallowed redirect"))

    with pytest.raises(ValueError, match="disallowed redirect"):
        download_bounded(
            "https://evil.example/pkg?go-get=1",
            max_bytes=1024,
            redirect_validator=validator,
        )

    validator.assert_called_once_with("http://127.0.0.1:8123/admin/reload")
    mock_stream_once.assert_called_once_with(
        "https://evil.example/pkg?go-get=1",
        {"User-Agent": DDLA_USER_AGENT},
        DOWNLOAD_CHUNK_SIZE_BYTES,
    )


def test_download_bounded_allows_max_validated_redirects(
    mocker: pytest_mock.MockFixture,
) -> None:
    chunks, consumed = _tracked_chunks([b"final"])
    responses: Iterator[tuple[int, dict[str, str], Iterator[bytes]]] = iter(
        [
            (302, {"Location": f"https://vanity.example/hop{i}"}, iter([]))
            for i in range(1, MAX_VALIDATED_REDIRECTS + 1)
        ]
        + [(200, {}, chunks)]
    )

    @contextlib.contextmanager
    def fake_stream_once(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        yield next(responses)

    mock_stream_once = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url_once",
        side_effect=fake_stream_once,
    )
    validator = Mock()

    result = download_bounded(
        "https://vanity.example/start",
        user_agent="custom-agent",
        max_bytes=1024,
        redirect_validator=validator,
    )

    assert result == b"final"
    expected_targets = [
        f"https://vanity.example/hop{i}" for i in range(1, MAX_VALIDATED_REDIRECTS + 1)
    ]
    assert validator.call_args_list == [mocker.call(t) for t in expected_targets]
    assert mock_stream_once.call_args_list == [
        mocker.call(
            target,
            {"User-Agent": "custom-agent"},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        )
        for target in ["https://vanity.example/start", *expected_targets]
    ]
    consumed.assert_called_once_with(b"final")


def test_download_bounded_rejects_excessive_validated_redirects(
    mocker: pytest_mock.MockFixture,
) -> None:
    responses: Iterator[tuple[int, dict[str, str], Iterator[bytes]]] = iter(
        [
            (302, {"Location": f"https://loop.example/hop{i}"}, iter([]))
            for i in range(1, MAX_VALIDATED_REDIRECTS + 1)
        ]
        + [(302, {"Location": "http://127.0.0.1/never-validated"}, iter([]))]
    )

    @contextlib.contextmanager
    def fake_stream_once(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        yield next(responses)

    mock_stream_once = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url_once",
        side_effect=fake_stream_once,
    )
    validator = Mock()

    with pytest.raises(
        OSError,
        match=r"^Too many redirects while downloading https://loop\.example/start$",
    ):
        download_bounded(
            "https://loop.example/start",
            max_bytes=1024,
            redirect_validator=validator,
        )

    expected_targets = [
        f"https://loop.example/hop{i}" for i in range(1, MAX_VALIDATED_REDIRECTS + 1)
    ]
    assert validator.call_args_list == [mocker.call(t) for t in expected_targets]
    assert mock_stream_once.call_args_list == [
        mocker.call(
            target,
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        )
        for target in ["https://loop.example/start", *expected_targets]
    ]


@pytest.mark.parametrize(
    ("status_code", "resp_headers"),
    [
        (299, {"Location": "https://other.example/ignored"}),
        (302, {}),
        (302, {"Location": ""}),
        (400, {"Location": "https://other.example/ignored"}),
    ],
)
def test_download_bounded_does_not_follow_non_redirect_or_missing_location(
    mocker: pytest_mock.MockFixture,
    status_code: int,
    resp_headers: dict[str, str],
) -> None:
    chunks, consumed = _tracked_chunks([b"body"])

    @contextlib.contextmanager
    def fake_stream_once(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        yield status_code, resp_headers, chunks

    mock_stream_once = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url_once",
        side_effect=fake_stream_once,
    )
    validator = Mock()

    assert (
        download_bounded(
            "https://vanity.example/pkg?go-get=1",
            max_bytes=1024,
            redirect_validator=validator,
        )
        == b"body"
    )
    validator.assert_not_called()
    mock_stream_once.assert_called_once_with(
        "https://vanity.example/pkg?go-get=1",
        {"User-Agent": DDLA_USER_AGENT},
        DOWNLOAD_CHUNK_SIZE_BYTES,
    )
    consumed.assert_called_once_with(b"body")


def test_download_bounded_follows_status_300_and_399_redirects(
    mocker: pytest_mock.MockFixture,
) -> None:
    chunks, consumed = _tracked_chunks([b"done"])
    responses = iter(
        [
            (300, {"Location": "https://vanity.example/hop1"}, iter([])),
            (399, {"Location": "https://vanity.example/hop2"}, iter([])),
            (200, {}, chunks),
        ]
    )

    @contextlib.contextmanager
    def fake_stream_once(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        yield next(responses)

    mock_stream_once = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url_once",
        side_effect=fake_stream_once,
    )
    validator = Mock()

    assert (
        download_bounded(
            "https://vanity.example/start",
            max_bytes=1024,
            redirect_validator=validator,
        )
        == b"done"
    )
    assert validator.call_args_list == [
        mocker.call("https://vanity.example/hop1"),
        mocker.call("https://vanity.example/hop2"),
    ]
    assert mock_stream_once.call_args_list == [
        mocker.call(
            "https://vanity.example/start",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
        mocker.call(
            "https://vanity.example/hop1",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
        mocker.call(
            "https://vanity.example/hop2",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
    ]
    consumed.assert_called_once_with(b"done")


@pytest.mark.parametrize("location_header", ["location", "LOCATION"])
def test_download_bounded_matches_location_header_case_insensitively(
    mocker: pytest_mock.MockFixture,
    location_header: str,
) -> None:
    chunks, consumed = _tracked_chunks([b"ok"])
    responses = iter(
        [
            (301, {location_header: "/target"}, iter([])),
            (200, {}, chunks),
        ]
    )

    @contextlib.contextmanager
    def fake_stream_once(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        yield next(responses)

    mock_stream_once = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url_once",
        side_effect=fake_stream_once,
    )
    validator = Mock()

    assert (
        download_bounded(
            "https://vanity.example/start",
            max_bytes=1024,
            redirect_validator=validator,
        )
        == b"ok"
    )
    validator.assert_called_once_with("https://vanity.example/target")
    assert mock_stream_once.call_args_list == [
        mocker.call(
            "https://vanity.example/start",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
        mocker.call(
            "https://vanity.example/target",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
    ]
    consumed.assert_called_once_with(b"ok")


@pytest.mark.parametrize("content_length_header", ["content-length", "CONTENT-LENGTH"])
def test_download_bounded_enforces_content_length_on_redirected_response(
    mocker: pytest_mock.MockFixture,
    content_length_header: str,
) -> None:
    chunks, consumed = _tracked_chunks([b"too-big"])
    responses = iter(
        [
            (301, {"Location": "https://cdn.example/final"}, iter([])),
            (200, {content_length_header: "11"}, chunks),
        ]
    )

    @contextlib.contextmanager
    def fake_stream_once(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        yield next(responses)

    mock_stream_once = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url_once",
        side_effect=fake_stream_once,
    )
    validator = Mock()

    with pytest.raises(
        OSError,
        match=r"^Download from https://cdn\.example/final exceeds maximum size of 10 bytes$",
    ):
        download_bounded(
            "https://vanity.example/start",
            max_bytes=10,
            redirect_validator=validator,
        )

    validator.assert_called_once_with("https://cdn.example/final")
    assert mock_stream_once.call_args_list == [
        mocker.call(
            "https://vanity.example/start",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
        mocker.call(
            "https://cdn.example/final",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
    ]
    consumed.assert_not_called()


def test_download_bounded_enforces_stream_limit_on_redirected_response(
    mocker: pytest_mock.MockFixture,
) -> None:
    chunks, consumed = _tracked_chunks([b"12345", b"678901"])
    responses = iter(
        [
            (302, {"Location": "https://cdn.example/stream"}, iter([])),
            (200, {}, chunks),
        ]
    )

    @contextlib.contextmanager
    def fake_stream_once(
        url: str,
        headers: dict[str, str],
        chunk_size: int,
    ) -> Iterator[tuple[int, dict[str, str], Iterator[bytes]]]:
        yield next(responses)

    mock_stream_once = mocker.patch(
        "dd_license_attribution.utils.bounded_download.stream_url_once",
        side_effect=fake_stream_once,
    )
    validator = Mock()

    with pytest.raises(
        OSError,
        match=r"^Download from https://cdn\.example/stream exceeds maximum size of 10 bytes$",
    ):
        download_bounded(
            "https://vanity.example/start",
            max_bytes=10,
            redirect_validator=validator,
        )

    validator.assert_called_once_with("https://cdn.example/stream")
    assert mock_stream_once.call_args_list == [
        mocker.call(
            "https://vanity.example/start",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
        mocker.call(
            "https://cdn.example/stream",
            {"User-Agent": DDLA_USER_AGENT},
            DOWNLOAD_CHUNK_SIZE_BYTES,
        ),
    ]
    assert consumed.call_args_list == [mocker.call(b"12345"), mocker.call(b"678901")]
