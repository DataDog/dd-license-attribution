# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import gzip
import io
import tarfile
from collections.abc import Iterator
from pathlib import Path

import pytest
import pytest_mock

from dd_license_attribution.utils.tar_archive import (
    MAX_ARCHIVE_MEMBERS,
    MAX_EXTRACTED_ARCHIVE_BYTES,
    _BoundedGzipReader,
    _decompression_budget,
    _is_safe_tar_member,
    extract_tar_gz,
    read_tar_gz_text_file,
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


def _tar_gz_with_file_and_trailing_garbage(files: dict[str, bytes]) -> bytes:
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    tar_with_garbage = archive_bytes.getvalue() + b"trailing garbage"
    return gzip.compress(tar_with_garbage)


def _tar_gz_with_read_only_directory() -> bytes:
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        directory = tarfile.TarInfo("crate")
        directory.type = tarfile.DIRTYPE
        directory.mode = 0o500
        archive.addfile(directory)

        member = tarfile.TarInfo("crate/Cargo.toml")
        content = b"[package]\n"
        member.size = len(content)
        archive.addfile(member, io.BytesIO(content))
    return archive_bytes.getvalue()


@pytest.mark.parametrize(
    "member_type",
    [
        tarfile.FIFOTYPE,
        tarfile.CHRTYPE,
        tarfile.BLKTYPE,
    ],
)
def test_extract_tar_gz_rejects_special_members(
    tmp_path: Path,
    member_type: bytes,
) -> None:
    member = tarfile.TarInfo("crate/special")
    member.type = member_type
    archive_content = _tar_gz_with_member(member)

    with pytest.raises(ValueError, match="Unsafe archive path: crate/special"):
        extract_tar_gz(archive_content, str(tmp_path))


@pytest.mark.parametrize(
    "member_name",
    [
        "../escape.txt",
        "crate/../../escape.txt",
        "/tmp/escape.txt",
        "crate\\..\\escape.txt",
    ],
)
def test_extract_tar_gz_rejects_unsafe_member_paths(
    tmp_path: Path,
    member_name: str,
) -> None:
    member = tarfile.TarInfo(member_name)
    member.size = 0
    archive_content = _tar_gz_with_member(member)

    with pytest.raises(ValueError, match="Unsafe archive path"):
        extract_tar_gz(archive_content, str(tmp_path))


@pytest.mark.parametrize("member_type", [tarfile.SYMTYPE, tarfile.LNKTYPE])
def test_extract_tar_gz_rejects_link_members(
    tmp_path: Path,
    member_type: bytes,
) -> None:
    member = tarfile.TarInfo("crate/link")
    member.type = member_type
    member.linkname = "../escape.txt"
    archive_content = _tar_gz_with_member(member)

    with pytest.raises(ValueError, match="Unsafe archive path: crate/link"):
        extract_tar_gz(archive_content, str(tmp_path))


def test_extract_tar_gz_rejects_too_many_members(tmp_path: Path) -> None:
    archive_content = _tar_gz_with_files(
        {
            "crate/one.txt": b"one",
            "crate/two.txt": b"two",
        }
    )

    with pytest.raises(ValueError, match="Archive contains more than 1 members"):
        extract_tar_gz(archive_content, str(tmp_path), max_members=1)


def test_extract_tar_gz_rejects_invalid_member_limit(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_members must be greater than zero"):
        extract_tar_gz(b"archive", str(tmp_path), max_members=0)


def test_extract_tar_gz_rejects_invalid_extracted_size_limit(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="max_extracted_bytes must be greater than zero",
    ):
        extract_tar_gz(b"archive", str(tmp_path), max_extracted_bytes=0)


def test_extract_tar_gz_rejects_file_over_extracted_size_limit(
    tmp_path: Path,
) -> None:
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
            str(tmp_path),
            max_extracted_bytes=20,
        )


def test_extract_tar_gz_rejects_total_extracted_size_over_limit(
    tmp_path: Path,
) -> None:
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
            str(tmp_path),
            max_extracted_bytes=20,
        )


def test_extract_tar_gz_accepts_exact_extracted_size_limit(tmp_path: Path) -> None:
    archive_content = _tar_gz_with_files(
        {
            "crate/one.txt": b"x" * 10,
            "crate/two.txt": b"y" * 10,
        }
    )

    result = extract_tar_gz(
        archive_content,
        str(tmp_path),
        max_extracted_bytes=20,
    )

    assert result == ["crate/one.txt", "crate/two.txt"]
    assert (tmp_path / "crate" / "one.txt").read_bytes() == b"x" * 10
    assert (tmp_path / "crate" / "two.txt").read_bytes() == b"y" * 10


def test_extract_tar_gz_rejects_malformed_archive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Malformed gzip tar archive"):
        extract_tar_gz(b"not a gzip tar archive", str(tmp_path))


def test_extract_tar_gz_rejects_truncated_gzip(tmp_path: Path) -> None:
    archive_content = _tar_gz_with_files({"crate/Cargo.toml": b"[package]\n"})

    with pytest.raises(ValueError, match="Malformed gzip tar archive"):
        extract_tar_gz(archive_content[: len(archive_content) // 2], str(tmp_path))


def test_extract_tar_gz_allows_tar_trailing_garbage_after_eof(tmp_path: Path) -> None:
    archive_content = _tar_gz_with_file_and_trailing_garbage(
        {"crate/Cargo.toml": b"[package]\n"}
    )

    result = extract_tar_gz(archive_content, str(tmp_path))

    assert result == ["crate/Cargo.toml"]
    assert (tmp_path / "crate" / "Cargo.toml").read_text() == "[package]\n"


def test_extract_tar_gz_writes_nothing_when_later_member_is_rejected(
    tmp_path: Path,
) -> None:
    archive_content = _tar_gz_with_files(
        {
            "crate/one.txt": b"one",
            "../escape.txt": b"escape",
        }
    )

    with pytest.raises(ValueError, match="Unsafe archive path"):
        extract_tar_gz(archive_content, str(tmp_path))

    assert list(tmp_path.iterdir()) == []


def test_extract_tar_gz_returns_members_in_archive_order_and_extracts_root(
    tmp_path: Path,
) -> None:
    archive_content = _tar_gz_with_files(
        {
            "demo-1.2.3/Cargo.toml": b"[package]\n",
            "demo-1.2.3/src/lib.rs": b"pub fn demo() {}\n",
        }
    )

    result = extract_tar_gz(archive_content, str(tmp_path))

    assert result == ["demo-1.2.3/Cargo.toml", "demo-1.2.3/src/lib.rs"]
    assert (tmp_path / "demo-1.2.3" / "Cargo.toml").read_bytes() == b"[package]\n"
    assert (
        tmp_path / "demo-1.2.3" / "src" / "lib.rs"
    ).read_bytes() == b"pub fn demo() {}\n"


def test_extract_tar_gz_uses_os_adaptor_for_extraction(
    tmp_path: Path,
    mocker: pytest_mock.MockFixture,
) -> None:
    archive_content = _tar_gz_with_files({"crate/Cargo.toml": b"[package]\n"})
    captured_member_names: list[str] = []
    captured_destination = ""
    captured_archive: tarfile.TarFile | None = None

    def fake_extract_tar_members(
        archive: tarfile.TarFile,
        members: Iterator[tarfile.TarInfo],
        destination: str,
    ) -> None:
        nonlocal captured_archive, captured_destination
        captured_archive = archive
        captured_destination = destination
        captured_member_names.extend(member.name for member in members)

    mock_extract_tar_members = mocker.patch(
        "dd_license_attribution.utils.tar_archive.extract_tar_members",
        side_effect=fake_extract_tar_members,
    )

    result = extract_tar_gz(archive_content, str(tmp_path))

    assert result == ["crate/Cargo.toml"]
    mock_extract_tar_members.assert_called_once()
    assert isinstance(captured_archive, tarfile.TarFile)
    assert captured_member_names == ["crate/Cargo.toml"]
    assert captured_destination == str(tmp_path)


def test_extract_tar_gz_defers_directory_permissions_until_children_are_extracted(
    tmp_path: Path,
) -> None:
    archive_content = _tar_gz_with_read_only_directory()
    directory_path = tmp_path / "crate"

    try:
        result = extract_tar_gz(archive_content, str(tmp_path))

        assert result == ["crate", "crate/Cargo.toml"]
        assert (directory_path / "Cargo.toml").read_bytes() == b"[package]\n"
    finally:
        if directory_path.exists():
            directory_path.chmod(0o700)


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


def test_read_tar_gz_text_file_accepts_exact_size_limit() -> None:
    archive_content = _tar_gz_with_files({"crate/Cargo.toml": b"x" * 20})

    result = read_tar_gz_text_file(
        archive_content,
        "/Cargo.toml",
        max_bytes=20,
    )

    assert result == "x" * 20


def test_read_tar_gz_text_file_rejects_invalid_size_limit() -> None:
    with pytest.raises(ValueError, match="max_bytes must be greater than zero"):
        read_tar_gz_text_file(b"archive", "/Cargo.toml", max_bytes=0)


def test_read_tar_gz_text_file_rejects_invalid_member_limit() -> None:
    with pytest.raises(ValueError, match="max_members must be greater than zero"):
        read_tar_gz_text_file(b"archive", "/Cargo.toml", max_members=0)


def test_read_tar_gz_text_file_rejects_too_many_members_before_match() -> None:
    archive_content = _tar_gz_with_files(
        {
            "crate/README.md": b"readme",
            "crate/Cargo.toml": b'[package]\nname = "crate"\n',
        }
    )

    with pytest.raises(ValueError, match="Archive contains more than 1 members"):
        read_tar_gz_text_file(archive_content, "/Cargo.toml", max_members=1)


def test_read_tar_gz_text_file_rejects_large_unmatched_member_before_match() -> None:
    archive_content = _tar_gz_with_files(
        {
            "crate/large.txt": b"x" * 10_000,
            "crate/Cargo.toml": b'[package]\nname = "crate"\n',
        }
    )

    with pytest.raises(
        ValueError,
        match="Archive exceeds maximum extracted size of 20 bytes",
    ):
        read_tar_gz_text_file(
            archive_content,
            "/Cargo.toml",
            max_bytes=20,
            max_members=2,
        )


def test_read_tar_gz_text_file_rejects_malformed_archive() -> None:
    with pytest.raises(ValueError, match="Malformed gzip tar archive"):
        read_tar_gz_text_file(b"not a gzip tar archive", "/Cargo.toml")


def test_bounded_reader_rejects_decompressed_stream_over_budget() -> None:
    compressed_content = gzip.compress(b"x" * 21)

    with gzip.GzipFile(fileobj=io.BytesIO(compressed_content)) as gzip_stream:
        reader = _BoundedGzipReader(gzip_stream, max_bytes=20, max_content_bytes=20)
        assert reader.readable()
        assert reader.seekable()
        with pytest.raises(
            ValueError,
            match="Archive exceeds maximum extracted size of 20 bytes",
        ):
            reader.read()


def test_bounded_reader_caps_large_requested_read_before_delegating() -> None:
    compressed_content = gzip.compress(b"x" * 10_000)

    with gzip.GzipFile(fileobj=io.BytesIO(compressed_content)) as gzip_stream:
        reader = _BoundedGzipReader(gzip_stream, max_bytes=20, max_content_bytes=20)
        with pytest.raises(
            ValueError,
            match="Archive exceeds maximum extracted size of 20 bytes",
        ):
            reader.read(10_000)

        assert gzip_stream.tell() == 21


def test_bounded_reader_rejects_when_already_over_budget() -> None:
    compressed_content = gzip.compress(b"x" * 10)

    with gzip.GzipFile(fileobj=io.BytesIO(compressed_content)) as gzip_stream:
        reader = _BoundedGzipReader(gzip_stream, max_bytes=1, max_content_bytes=1)
        with pytest.raises(
            ValueError,
            match="Archive exceeds maximum extracted size of 1 bytes",
        ):
            reader.read(2)
        with pytest.raises(
            ValueError,
            match="Archive exceeds maximum extracted size of 1 bytes",
        ):
            reader.read(1)


def test_bounded_reader_caps_forward_seek_before_delegating() -> None:
    compressed_content = gzip.compress(b"x" * 10_000)

    with gzip.GzipFile(fileobj=io.BytesIO(compressed_content)) as gzip_stream:
        reader = _BoundedGzipReader(gzip_stream, max_bytes=20, max_content_bytes=20)
        with pytest.raises(
            ValueError,
            match="Archive exceeds maximum extracted size of 20 bytes",
        ):
            reader.seek(10_000)

        assert gzip_stream.tell() == 21


def test_bounded_reader_supports_small_forward_and_backward_seeks() -> None:
    compressed_content = gzip.compress(b"0123456789")

    with gzip.GzipFile(fileobj=io.BytesIO(compressed_content)) as gzip_stream:
        reader = _BoundedGzipReader(gzip_stream, max_bytes=20, max_content_bytes=20)

        assert reader.read(5) == b"01234"
        assert reader.tell() == 5
        assert reader.seek(8, io.SEEK_CUR) == 10
        assert reader.tell() == 10
        assert reader.seek(2) == 2
        assert reader.tell() == 2


def test_bounded_reader_stops_forward_seek_at_eof() -> None:
    compressed_content = gzip.compress(b"abc")

    with gzip.GzipFile(fileobj=io.BytesIO(compressed_content)) as gzip_stream:
        reader = _BoundedGzipReader(gzip_stream, max_bytes=20, max_content_bytes=20)

        assert reader.seek(10) == 3


@pytest.mark.parametrize("whence", [io.SEEK_END, 99])
def test_bounded_reader_rejects_unsupported_seek_modes(whence: int) -> None:
    compressed_content = gzip.compress(b"abc")

    with gzip.GzipFile(fileobj=io.BytesIO(compressed_content)) as gzip_stream:
        reader = _BoundedGzipReader(gzip_stream, max_bytes=20, max_content_bytes=20)

        with pytest.raises(ValueError):
            reader.seek(1, whence)


def test_is_safe_tar_member_accepts_destination_member(tmp_path: Path) -> None:
    member = tarfile.TarInfo("")
    member.size = 0

    assert _is_safe_tar_member(member, str(tmp_path))


def test_is_safe_tar_member_rejects_unsafe_path(tmp_path: Path) -> None:
    member = tarfile.TarInfo("../escape.txt")
    member.size = 0

    assert not _is_safe_tar_member(member, str(tmp_path))


def test_decompression_budget_includes_tar_overhead() -> None:
    assert _decompression_budget(1000, 3) == 1000 + 5 * 1024


def test_archive_constants_are_pinned() -> None:
    assert MAX_EXTRACTED_ARCHIVE_BYTES == 100 * 1024 * 1024
    assert MAX_ARCHIVE_MEMBERS == 10_000
