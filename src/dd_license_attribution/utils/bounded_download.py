# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from collections.abc import Callable, Iterator, Mapping
from urllib.parse import urljoin

from dd_license_attribution.adaptors.os import stream_url, stream_url_once

DDLA_USER_AGENT = (
    "dd-license-attribution (https://github.com/DataDog/dd-license-attribution)"
)
DOWNLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024
MAX_VALIDATED_REDIRECTS = 5


def _get_header(headers: Mapping[str, str], lowercase_name: str) -> str | None:
    for key, value in headers.items():
        if key.lower() == lowercase_name:
            return value
    return None


def _exceeds_content_length(content_length: str | None, max_bytes: int) -> bool:
    if content_length is None:
        return False
    try:
        expected_bytes = int(content_length)
    except ValueError:
        return False
    return expected_bytes > max_bytes


def _read_bounded_chunks(
    url: str,
    headers: Mapping[str, str],
    chunks: Iterator[bytes],
    max_bytes: int,
) -> bytes:
    if _exceeds_content_length(_get_header(headers, "content-length"), max_bytes):
        raise OSError(f"Download from {url} exceeds maximum size of {max_bytes} bytes")

    buffer: list[bytes] = []
    downloaded_bytes = 0
    for chunk in chunks:
        if not chunk:
            continue
        downloaded_bytes += len(chunk)
        if downloaded_bytes > max_bytes:
            raise OSError(
                f"Download from {url} exceeds maximum size of {max_bytes} bytes"
            )
        buffer.append(chunk)
    return b"".join(buffer)


def download_bounded(
    url: str,
    user_agent: str = DDLA_USER_AGENT,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
    redirect_validator: Callable[[str], None] | None = None,
) -> bytes:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be greater than zero")

    request_headers = {"User-Agent": user_agent}
    if redirect_validator is None:
        with stream_url(url, request_headers, DOWNLOAD_CHUNK_SIZE_BYTES) as (
            headers,
            chunks,
        ):
            return _read_bounded_chunks(url, headers, chunks, max_bytes)

    current_url = url
    for hop in range(MAX_VALIDATED_REDIRECTS + 1):
        with stream_url_once(
            current_url, request_headers, DOWNLOAD_CHUNK_SIZE_BYTES
        ) as (status_code, headers, chunks):
            location = _get_header(headers, "location")
            if not (300 <= status_code < 400 and location):
                return _read_bounded_chunks(current_url, headers, chunks, max_bytes)
        if hop < MAX_VALIDATED_REDIRECTS:
            next_url = urljoin(current_url, location)
            redirect_validator(next_url)
            current_url = next_url
    raise OSError(f"Too many redirects while downloading {url}")
