# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from dd_license_attribution.adaptors.os import stream_url

DDLA_USER_AGENT = (
    "dd-license-attribution (https://github.com/DataDog/dd-license-attribution)"
)
DOWNLOAD_CHUNK_SIZE_BYTES = 1024 * 1024
MAX_DOWNLOAD_BYTES = 100 * 1024 * 1024


def _exceeds_content_length(content_length: str | None, max_bytes: int) -> bool:
    if content_length is None:
        return False
    try:
        expected_bytes = int(content_length)
    except ValueError:
        return False
    return expected_bytes > max_bytes


def download_bounded(
    url: str,
    user_agent: str = DDLA_USER_AGENT,
    max_bytes: int = MAX_DOWNLOAD_BYTES,
) -> bytes:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be greater than zero")

    with stream_url(
        url,
        {"User-Agent": user_agent},
        DOWNLOAD_CHUNK_SIZE_BYTES,
    ) as (headers, chunks):
        if _exceeds_content_length(headers.get("Content-Length"), max_bytes):
            raise OSError(
                f"Download from {url} exceeds maximum size of {max_bytes} bytes"
            )

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
