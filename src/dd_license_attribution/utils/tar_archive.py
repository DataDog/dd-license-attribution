# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import contextlib
import gzip
import io
import tarfile
from collections.abc import Iterator

from dd_license_attribution.adaptors.os import (
    PATH_SEPARATOR,
    absolute_path,
    is_absolute_path,
    path_join,
)

MAX_EXTRACTED_ARCHIVE_BYTES = 100 * 1024 * 1024
MAX_ARCHIVE_MEMBERS = 10_000
_TAR_BLOCK_SIZE = 512
_MAX_DELEGATED_READ_BYTES = 1024 * 1024


class _BoundedGzipReader(io.RawIOBase):
    """Caps how far tarfile may advance into the decompressed gzip stream."""

    def __init__(
        self,
        raw: gzip.GzipFile,
        max_bytes: int,
        max_content_bytes: int,
    ) -> None:
        self._raw = raw
        self._max_bytes = max_bytes
        self._max_content_bytes = max_content_bytes

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._raw.tell()

    def read(self, size: int = -1) -> bytes:
        delegated_size = self._bounded_read_size(size)
        content = self._raw.read(delegated_size)
        self._check_budget()
        return content

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        current_position = self._raw.tell()
        target_position = self._target_position(offset, whence, current_position)
        if target_position < current_position:
            position = self._raw.seek(target_position, io.SEEK_SET)
            self._check_budget()
            return position

        bytes_to_skip = target_position - current_position
        while bytes_to_skip > 0:
            chunk = self.read(min(bytes_to_skip, _MAX_DELEGATED_READ_BYTES))
            if not chunk:
                break
            bytes_to_skip -= len(chunk)
        position = self._raw.tell()
        self._check_budget()
        return position

    def _bounded_read_size(self, requested_size: int) -> int:
        remaining_bytes = self._max_bytes - self._raw.tell()
        if remaining_bytes < 0:
            self._check_budget()
        if requested_size < 0 or requested_size > remaining_bytes:
            return remaining_bytes + 1
        return requested_size

    def _target_position(
        self,
        offset: int,
        whence: int,
        current_position: int,
    ) -> int:
        if whence == io.SEEK_SET:
            return offset
        if whence == io.SEEK_CUR:
            return current_position + offset
        if whence == io.SEEK_END:
            raise ValueError("Seeking from end is not supported for gzip tar archives")
        raise ValueError(f"Invalid seek mode: {whence}")

    def _check_budget(self) -> None:
        if self._raw.tell() > self._max_bytes:
            raise ValueError(
                "Archive exceeds maximum extracted size "
                f"of {self._max_content_bytes} bytes"
            )


def _decompression_budget(max_content_bytes: int, max_members: int) -> int:
    """Content allowance plus tar header and padding overhead."""
    return max_content_bytes + (max_members + 2) * 2 * _TAR_BLOCK_SIZE


@contextlib.contextmanager
def _open_bounded_tar_gz(
    archive_content: bytes,
    budget: int,
    max_content_bytes: int,
) -> Iterator[tarfile.TarFile]:
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(archive_content)) as gzip_stream:
            reader = _BoundedGzipReader(gzip_stream, budget, max_content_bytes)
            with tarfile.open(fileobj=reader, mode="r:") as archive:
                yield archive
    except (tarfile.TarError, gzip.BadGzipFile, EOFError) as e:
        raise ValueError(f"Malformed gzip tar archive: {e}") from e


def _is_safe_tar_member(member: tarfile.TarInfo, destination: str) -> bool:
    if not (member.isfile() or member.isdir()):
        return False

    member_name = member.name.replace("\\", "/")
    if is_absolute_path(member_name) or ".." in member_name.split("/"):
        return False

    destination_abs = absolute_path(destination)
    member_target = absolute_path(path_join(destination_abs, member_name))
    return member_target == destination_abs or member_target.startswith(
        f"{destination_abs}{PATH_SEPARATOR}"
    )


def _iter_validated_members(
    archive: tarfile.TarFile,
    destination: str,
    max_extracted_bytes: int,
    max_members: int,
) -> Iterator[tarfile.TarInfo]:
    member_count = 0
    extracted_bytes = 0
    for member in archive:
        member_count += 1
        if member_count > max_members:
            raise ValueError(f"Archive contains more than {max_members} members")
        if not _is_safe_tar_member(member, destination):
            raise ValueError(f"Unsafe archive path: {member.name}")
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
        yield member


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

    budget = _decompression_budget(max_extracted_bytes, max_members)
    with _open_bounded_tar_gz(archive_content, budget, max_extracted_bytes) as archive:
        member_names = [
            member.name
            for member in _iter_validated_members(
                archive,
                destination,
                max_extracted_bytes,
                max_members,
            )
        ]

    with _open_bounded_tar_gz(archive_content, budget, max_extracted_bytes) as archive:
        for member in _iter_validated_members(
            archive,
            destination,
            max_extracted_bytes,
            max_members,
        ):
            archive.extract(member, destination, filter="data")

    return member_names


def read_tar_gz_text_file(
    archive_content: bytes,
    member_suffix: str,
    max_bytes: int = MAX_EXTRACTED_ARCHIVE_BYTES,
    max_members: int = MAX_ARCHIVE_MEMBERS,
) -> str | None:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be greater than zero")
    if max_members <= 0:
        raise ValueError("max_members must be greater than zero")

    budget = _decompression_budget(max_bytes, max_members)
    with _open_bounded_tar_gz(archive_content, budget, max_bytes) as archive:
        member_count = 0
        for member in archive:
            member_count += 1
            if member_count > max_members:
                raise ValueError(f"Archive contains more than {max_members} members")
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
    return None
