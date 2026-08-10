# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import io
import tarfile
from pathlib import Path

from dd_license_attribution.utils.tar_archive import extract_tar_gz


def _tar_gz_with_files(files: dict[str, bytes]) -> bytes:
    archive_bytes = io.BytesIO()
    with tarfile.open(fileobj=archive_bytes, mode="w:gz") as archive:
        for name, content in files.items():
            member = tarfile.TarInfo(name)
            member.size = len(content)
            archive.addfile(member, io.BytesIO(content))
    return archive_bytes.getvalue()


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


def test_extract_tar_gz_extracts_members_to_destination(tmp_path: Path) -> None:
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
