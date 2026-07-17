# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

import json
import logging
from unittest.mock import Mock, call

import pytest
import pytest_mock
from pytest import LogCaptureFixture

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.rust_package_resolver import (
    CRATES_IO_USER_AGENT,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.rust_collection_strategy import (
    mark_rust_metadata,
)
from dd_license_attribution.metadata_collector.strategies.rust_crates_io_collection_strategy import (
    CRATES_IO_API_BASE_URL,
    RustCratesIoMetadataCollectionStrategy,
)


def _metadata(
    name: str,
    version: str | None,
    origin: str | None = None,
    license: list[str] | None = None,
    copyright: list[str] | None = None,
) -> Metadata:
    return Metadata(
        name=name,
        version=version,
        origin=origin if origin is not None else name,
        local_src_path=None,
        license=license or [],
        copyright=copyright or [],
    )


def _crate_response(
    name: str,
    version: str,
    license_expression: str | None = "MIT OR Apache-2.0",
    repository: str | None = None,
    default_version: str | None = None,
) -> bytes:
    return json.dumps(
        {
            "crate": {
                "name": name,
                "default_version": default_version or version,
                "repository": repository,
            },
            "versions": [
                {
                    "num": version,
                    "license": license_expression,
                    "repository": repository,
                }
            ],
        }
    ).encode()


def _source_code_manager() -> Mock:
    source_code_manager = Mock()
    source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/project",
        branch="main",
        local_root_path="/cache/org-project",
        local_full_path="/cache/org-project",
    )
    return source_code_manager


def test_enriches_locked_and_path_dependency_metadata_without_overwriting(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _source_code_manager()
    mock_path_join = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_normalize_path = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.normalize_path",
        side_effect=lambda path: path.replace("/./", "/").removesuffix("/."),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=lambda path: path
        in {
            "/project/Cargo.lock",
            "/project/Cargo.toml",
            "/project/patches/helper/Cargo.toml",
        },
    )
    cargo_lock = """
version = 4

[[package]]
name = "regex"
version = "1.13.0"
source = "registry+https://github.com/rust-lang/crates.io-index"

[[package]]
name = "git-only"
version = "1.0.0"
source = "git+https://github.com/org/git-only"

[[package]]
version = "1.0.0"
"""
    root_manifest = """
[package]
name = "project"
version = "1.0.0"

[dependencies]
renamed = { package = "actual-crate", version = "2.0.0" }
simple = "1.0.0"
helper = { path = "patches/helper", version = "1.0.0" }
unversioned = { git = "https://github.com/org/unversioned" }
git-versioned = { git = "https://github.com/org/git-versioned", version = "1.0.0" }
alternate-registry = { version = "1.0.0", registry = "private" }
explicit-crates-io = { version = "=5.0.0", registry = "crates-io" }

[workspace.dependencies]
workspace-crate = "3.0.0"

[target]
invalid = "not-a-table"

[target.'cfg(unix)'.build-dependencies]
target-crate = "4.0.0"
"""
    helper_manifest = """
[package]
name = "helper"
version = "1.0.0"

[dev-dependencies]
tracing-subscriber = "=0.3.20"
helper = { path = "." }
"""

    def open_file(path: str) -> str:
        return {
            "/project/Cargo.lock": cargo_lock,
            "/project/Cargo.toml": root_manifest,
            "/project/patches/helper/Cargo.toml": helper_manifest,
        }[path]

    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        side_effect=open_file,
    )

    def download(url: str, user_agent: str) -> bytes:
        if url.endswith("/download"):
            return b"crate archive"
        if url.endswith("/regex"):
            return _crate_response(
                "regex",
                "1.13.0",
                repository="https://github.com/rust-lang/regex",
            )
        if url.endswith("/tracing-subscriber"):
            return _crate_response(
                "tracing-subscriber",
                "0.3.20",
                license_expression="MIT",
                repository="https://github.com/tokio-rs/tracing",
            )
        if url.endswith("/explicit-crates-io"):
            return _crate_response(
                "explicit-crates-io",
                "5.0.0",
                license_expression="Apache-2.0",
                repository="https://github.com/org/explicit-crates-io",
            )
        raise AssertionError(f"Unexpected URL: {url}")

    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url",
        side_effect=download,
    )
    mock_read_archive = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.read_tar_gz_text_file",
        side_effect=[
            '[package]\nname = "regex"\nauthors = ["The Rust Developers"]\n',
            '[package]\nname = "tracing-subscriber"\nauthors = ["Tokio Contributors", 1, ""]\n',
        ],
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "project",
        source_code_manager,
        local_project_path="/project",
    )
    complete = _metadata(
        "simple",
        "1.0.0",
        origin="https://example.com/simple",
        license=["BSD-3-Clause"],
        copyright=["Existing Author"],
    )
    unrelated = _metadata("npm-only", "1.0.0")

    result = strategy.augment_metadata(
        [
            _metadata("regex", ">= 1.12.3,< 2.0.0"),
            _metadata("tracing-subscriber", ">= 0.3.20,< 0.4.0"),
            _metadata(
                "explicit-crates-io",
                ">= 5.0.0,< 6.0.0",
                copyright=["Existing Explicit Author"],
            ),
            _metadata("helper", "1.0.0"),
            _metadata("git-versioned", "1.0.0"),
            _metadata("alternate-registry", "1.0.0"),
            complete,
            unrelated,
        ]
    )

    assert result == [
        _metadata(
            "regex",
            ">= 1.12.3,< 2.0.0",
            origin="https://github.com/rust-lang/regex",
            license=["MIT OR Apache-2.0"],
            copyright=["The Rust Developers"],
        ),
        _metadata(
            "tracing-subscriber",
            ">= 0.3.20,< 0.4.0",
            origin="https://github.com/tokio-rs/tracing",
            license=["MIT"],
            copyright=["Tokio Contributors"],
        ),
        _metadata(
            "explicit-crates-io",
            ">= 5.0.0,< 6.0.0",
            origin="https://github.com/org/explicit-crates-io",
            license=["Apache-2.0"],
            copyright=["Existing Explicit Author"],
        ),
        _metadata("helper", "1.0.0"),
        _metadata("git-versioned", "1.0.0"),
        _metadata("alternate-registry", "1.0.0"),
        complete,
        unrelated,
    ]
    source_code_manager.get_code.assert_not_called()
    mock_path_exists.assert_has_calls(
        [
            call("/project/Cargo.lock"),
            call("/project/Cargo.toml"),
            call("/project/patches/helper/Cargo.toml"),
        ]
    )
    assert mock_path_exists.call_count == 3
    mock_open_file.assert_has_calls(
        [
            call("/project/Cargo.lock"),
            call("/project/Cargo.toml"),
            call("/project/patches/helper/Cargo.toml"),
        ]
    )
    assert mock_open_file.call_count == 3
    mock_download.assert_has_calls(
        [
            call(
                f"{CRATES_IO_API_BASE_URL}/regex",
                user_agent=CRATES_IO_USER_AGENT,
            ),
            call(
                f"{CRATES_IO_API_BASE_URL}/regex/1.13.0/download",
                user_agent=CRATES_IO_USER_AGENT,
            ),
            call(
                f"{CRATES_IO_API_BASE_URL}/tracing-subscriber",
                user_agent=CRATES_IO_USER_AGENT,
            ),
            call(
                f"{CRATES_IO_API_BASE_URL}/tracing-subscriber/0.3.20/download",
                user_agent=CRATES_IO_USER_AGENT,
            ),
            call(
                f"{CRATES_IO_API_BASE_URL}/explicit-crates-io",
                user_agent=CRATES_IO_USER_AGENT,
            ),
        ]
    )
    assert mock_download.call_count == 5
    mock_read_archive.assert_has_calls(
        [call(b"crate archive", "/Cargo.toml"), call(b"crate archive", "/Cargo.toml")]
    )
    assert mock_read_archive.call_count == 2
    assert mock_path_join.call_count == 5
    assert mock_normalize_path.call_count == 3


def test_complete_metadata_still_receives_locked_version_and_repository_origin(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _source_code_manager()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=[True, False],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value=(
            '[[package]]\nname = "serde"\nversion = "1.0.0"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
        ),
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url",
        return_value=_crate_response(
            "serde",
            "1.0.0",
            repository="https://github.com/serde-rs/serde",
        ),
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "serde",
        source_code_manager,
        local_project_path="/project",
    )

    result = strategy.augment_metadata(
        [
            _metadata(
                "serde",
                None,
                license=["MIT OR Apache-2.0"],
                copyright=["Serde Developers"],
            )
        ]
    )

    assert result == [
        _metadata(
            "serde",
            "1.0.0",
            origin="https://github.com/serde-rs/serde",
            license=["MIT OR Apache-2.0"],
            copyright=["Serde Developers"],
        )
    ]
    source_code_manager.get_code.assert_not_called()
    mock_path_exists.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/project/Cargo.lock")
    mock_download.assert_called_once_with(
        f"{CRATES_IO_API_BASE_URL}/serde",
        user_agent=CRATES_IO_USER_AGENT,
    )


def test_direct_root_package_is_enriched_from_manifest_version(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _source_code_manager()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=[False, True],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value='[package]\nname = "serde"\nversion = "1.0.0"\n',
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url",
        side_effect=[
            _crate_response(
                "serde",
                "1.0.0",
                repository="https://github.com/serde-rs/serde",
            ),
            b"crate archive",
        ],
    )
    mock_read_archive = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.read_tar_gz_text_file",
        return_value='[package]\nname = "serde"\nauthors = ["Serde Developers"]\n',
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "serde",
        source_code_manager,
        local_project_path="/project",
    )

    result = strategy.augment_metadata([_metadata("serde", "1.0.0")])

    assert result == [
        _metadata(
            "serde",
            "1.0.0",
            origin="https://github.com/serde-rs/serde",
            license=["MIT OR Apache-2.0"],
            copyright=["Serde Developers"],
        )
    ]
    source_code_manager.get_code.assert_not_called()
    mock_path_exists.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/project/Cargo.toml")
    mock_download.assert_has_calls(
        [
            call(
                f"{CRATES_IO_API_BASE_URL}/serde",
                user_agent=CRATES_IO_USER_AGENT,
            ),
            call(
                f"{CRATES_IO_API_BASE_URL}/serde/1.0.0/download",
                user_agent=CRATES_IO_USER_AGENT,
            ),
        ]
    )
    assert mock_download.call_count == 2
    mock_read_archive.assert_called_once_with(b"crate archive", "/Cargo.toml")


def test_repository_mode_ignores_manifest_ranges_without_lockfile(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _source_code_manager()
    mock_walk = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.walk_directory",
        return_value=[
            ("/cache/org-project", [".git", "target", "crate"], []),
            ("/cache/org-project/crate", ["nested"], ["Cargo.toml"]),
            ("/cache/org-project/crate/nested", [], ["Cargo.toml"]),
        ],
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=lambda path: path.endswith("Cargo.toml"),
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value='[dependencies]\nzip = ">= 0.6.6"\n',
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url"
    )
    mock_read_archive = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.read_tar_gz_text_file",
        return_value='[package]\nname = "zip"\nauthors = ["The zip Authors"]\n',
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "https://github.com/org/project",
        source_code_manager,
    )

    result = strategy.augment_metadata([_metadata("zip", None)])

    assert result == [_metadata("zip", None)]
    source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/project"
    )
    mock_walk.assert_called_once_with("/cache/org-project")
    mock_path_exists.assert_has_calls(
        [
            call("/cache/org-project/crate/Cargo.lock"),
            call("/cache/org-project/crate/Cargo.toml"),
            call("/cache/org-project/crate/nested/Cargo.lock"),
            call("/cache/org-project/crate/nested/Cargo.toml"),
        ]
    )
    assert mock_path_exists.call_count == 4
    mock_open_file.assert_has_calls(
        [
            call("/cache/org-project/crate/Cargo.toml"),
            call("/cache/org-project/crate/nested/Cargo.toml"),
        ]
    )
    assert mock_open_file.call_count == 2
    mock_download.assert_not_called()
    mock_read_archive.assert_not_called()


def test_repository_mode_does_not_enrich_unmarked_same_name_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _source_code_manager()
    mock_walk = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.walk_directory",
        return_value=[("/cache/org-project", [], ["Cargo.toml"])],
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=lambda path: path.endswith("Cargo.lock"),
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value=(
            '[[package]]\nname = "serde"\nversion = "1.0.228"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
        ),
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url"
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "https://github.com/org/project",
        source_code_manager,
    )
    metadata = [
        _metadata(
            "serde",
            None,
            origin="https://pypi.org/project/serde",
        )
    ]

    result = strategy.augment_metadata(metadata)

    assert result == metadata
    source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/project"
    )
    mock_walk.assert_called_once_with("/cache/org-project")
    mock_path_exists.assert_has_calls(
        [
            call("/cache/org-project/Cargo.lock"),
            call("/cache/org-project/Cargo.toml"),
        ]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/cache/org-project/Cargo.lock")
    mock_download.assert_not_called()


def test_repository_mode_enriches_marked_rust_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _source_code_manager()
    mock_walk = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.walk_directory",
        return_value=[("/cache/org-project", [], ["Cargo.toml"])],
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=lambda path: path.endswith("Cargo.lock"),
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value=(
            '[[package]]\nname = "serde"\nversion = "1.0.228"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
        ),
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url",
        side_effect=[
            _crate_response(
                "serde",
                "1.0.228",
                repository="https://github.com/serde-rs/serde",
            ),
            b"crate archive",
        ],
    )
    mock_read_archive = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.read_tar_gz_text_file",
        return_value='[package]\nname = "serde"\nauthors = ["Serde Developers"]\n',
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "https://github.com/org/project",
        source_code_manager,
    )

    result = strategy.augment_metadata([mark_rust_metadata(_metadata("serde", None))])

    assert result == [
        _metadata(
            "serde",
            "1.0.228",
            origin="https://github.com/serde-rs/serde",
            license=["MIT OR Apache-2.0"],
            copyright=["Serde Developers"],
        )
    ]
    source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/project"
    )
    mock_walk.assert_called_once_with("/cache/org-project")
    mock_path_exists.assert_has_calls(
        [
            call("/cache/org-project/Cargo.lock"),
            call("/cache/org-project/Cargo.toml"),
        ]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/cache/org-project/Cargo.lock")
    mock_download.assert_has_calls(
        [
            call(
                f"{CRATES_IO_API_BASE_URL}/serde",
                user_agent=CRATES_IO_USER_AGENT,
            ),
            call(
                f"{CRATES_IO_API_BASE_URL}/serde/1.0.228/download",
                user_agent=CRATES_IO_USER_AGENT,
            ),
        ]
    )
    assert mock_download.call_count == 2
    mock_read_archive.assert_called_once_with(b"crate archive", "/Cargo.toml")


def test_unavailable_repository_returns_metadata_unchanged() -> None:
    source_code_manager = _source_code_manager()
    source_code_manager.get_code.return_value = None
    strategy = RustCratesIoMetadataCollectionStrategy(
        "https://github.com/org/project",
        source_code_manager,
    )
    metadata = [_metadata("regex", "1.12.3")]

    result = strategy.augment_metadata(metadata)

    assert result == metadata
    source_code_manager.get_code.assert_called_once_with(
        "https://github.com/org/project"
    )


def test_locked_crate_is_used_when_manifest_is_missing(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _source_code_manager()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=[True, False],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value=(
            'package = ["invalid", '
            '{ name = "regex", version = "1.0.0", '
            'source = "registry+https://github.com/rust-lang/crates.io-index" }]\n'
        ),
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url",
        return_value=json.dumps(
            {
                "crate": {"default_version": "1.0.0", "repository": 1},
                "versions": [
                    {
                        "num": "1.0.0",
                        "license": 1,
                        "repository": 1,
                    }
                ],
            }
        ).encode(),
    )
    mock_read_archive = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.read_tar_gz_text_file"
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "regex",
        source_code_manager,
        local_project_path="/project",
    )
    metadata = _metadata(
        "regex",
        None,
        copyright=["Existing Author"],
    )

    result = strategy.augment_metadata([metadata])

    assert result == [metadata]
    mock_path_exists.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/project/Cargo.lock")
    mock_download.assert_called_once_with(
        f"{CRATES_IO_API_BASE_URL}/regex",
        user_agent=CRATES_IO_USER_AGENT,
    )
    mock_read_archive.assert_not_called()


@pytest.mark.parametrize(
    "metadata_version",
    [None, ">= 1.13.0,< 2.0.0"],
)
def test_unparseable_manifest_version_is_ignored(
    mocker: pytest_mock.MockFixture,
    metadata_version: str | None,
) -> None:
    source_code_manager = _source_code_manager()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=[False, True],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value='[dependencies]\nregex = "not-semver"\n',
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url",
        side_effect=[
            _crate_response(
                "regex",
                "1.13.0",
                repository="https://github.com/rust-lang/regex",
            ),
            b"crate archive",
        ],
    )
    mock_read_archive = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.read_tar_gz_text_file",
        return_value='[package]\nname = "regex"\nauthors = ["The Rust Developers"]\n',
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "regex",
        source_code_manager,
        local_project_path="/project",
    )

    result = strategy.augment_metadata([_metadata("regex", metadata_version)])

    assert result == [_metadata("regex", metadata_version)]
    mock_path_exists.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/project/Cargo.toml")
    mock_download.assert_not_called()
    mock_read_archive.assert_not_called()


def test_ambiguous_locked_versions_do_not_set_version_or_enrich(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _source_code_manager()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=[True, False],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value=(
            '[[package]]\nname = "syn"\nversion = "1.0.109"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
            "\n"
            '[[package]]\nname = "syn"\nversion = "2.0.104"\n'
            'source = "registry+https://github.com/rust-lang/crates.io-index"\n'
        ),
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url"
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "project",
        source_code_manager,
        local_project_path="/project",
    )

    result = strategy.augment_metadata([_metadata("syn", None)])

    assert result == [_metadata("syn", None)]
    mock_path_exists.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/project/Cargo.lock")
    mock_download.assert_not_called()


@pytest.mark.parametrize(
    "manifest_requirement",
    ["2", "^1", "1.0.203", ">= 0.6.6", "=not-semver"],
)
def test_manifest_requirement_without_exact_version_is_not_enriched(
    mocker: pytest_mock.MockFixture,
    manifest_requirement: str,
) -> None:
    source_code_manager = _source_code_manager()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=[False, True],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value=f'[dependencies]\nclap = "{manifest_requirement}"\n',
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url"
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "project",
        source_code_manager,
        local_project_path="/project",
    )

    result = strategy.augment_metadata([_metadata("clap", None)])

    assert result == [_metadata("clap", None)]
    mock_path_exists.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/project/Cargo.toml")
    mock_download.assert_not_called()


@pytest.mark.parametrize(
    ("metadata_response", "expected_log"),
    [
        (OSError("network unavailable"), "Could not retrieve crates.io metadata"),
        (b"not-json", "Could not retrieve crates.io metadata"),
        (json.dumps([]).encode(), None),
        (json.dumps({"crate": {}, "versions": "invalid"}).encode(), None),
        (
            json.dumps(
                {
                    "crate": {"default_version": "2.0.0"},
                    "versions": [{"num": "3.0.0"}],
                }
            ).encode(),
            None,
        ),
    ],
)
def test_invalid_crates_io_metadata_is_ignored(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
    metadata_response: bytes | OSError,
    expected_log: str | None,
) -> None:
    source_code_manager = _source_code_manager()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=[False, True],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value='[dependencies]\nregex = "=1.0.0"\n',
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url",
    )
    if isinstance(metadata_response, OSError):
        mock_download.side_effect = metadata_response
    else:
        mock_download.return_value = metadata_response
    mock_read_archive = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.read_tar_gz_text_file"
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "regex",
        source_code_manager,
        local_project_path="/project",
    )
    metadata = [_metadata("regex", "1.0.0")]

    with caplog.at_level(logging.WARNING):
        result = strategy.augment_metadata(metadata)

    assert result == metadata
    if expected_log is not None:
        assert expected_log in caplog.text
    mock_path_exists.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/project/Cargo.toml")
    mock_download.assert_called_once_with(
        f"{CRATES_IO_API_BASE_URL}/regex",
        user_agent=CRATES_IO_USER_AGENT,
    )
    mock_read_archive.assert_not_called()


@pytest.mark.parametrize(
    ("archive_result", "expected_copyright", "expected_log"),
    [
        (OSError("download failed"), [], "Could not retrieve crates.io authors"),
        (None, [], None),
        ("invalid toml =", [], "Could not retrieve crates.io authors"),
        ("[workspace]\nmembers = []\n", [], None),
        ('[package]\nname = "regex"\nauthors = "invalid"\n', [], None),
    ],
)
def test_author_metadata_failures_preserve_other_crate_metadata(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
    archive_result: str | OSError | None,
    expected_copyright: list[str],
    expected_log: str | None,
) -> None:
    source_code_manager = _source_code_manager()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        side_effect=[False, True],
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        return_value='[dependencies]\nregex = "=1.0.0"\n',
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url",
        side_effect=[
            _crate_response(
                "regex",
                "1.0.0",
                repository="https://github.com/rust-lang/regex",
            ),
            (
                OSError("download failed")
                if isinstance(archive_result, OSError)
                else b"crate archive"
            ),
        ],
    )
    mock_read_archive = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.read_tar_gz_text_file",
        return_value=archive_result if isinstance(archive_result, str) else None,
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "regex",
        source_code_manager,
        local_project_path="/project",
    )

    with caplog.at_level(logging.WARNING):
        result = strategy.augment_metadata([_metadata("regex", "1.0.0")])

    assert result == [
        _metadata(
            "regex",
            "1.0.0",
            origin="https://github.com/rust-lang/regex",
            license=["MIT OR Apache-2.0"],
            copyright=expected_copyright,
        )
    ]
    if expected_log is not None:
        assert expected_log in caplog.text
    mock_path_exists.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_called_once_with("/project/Cargo.toml")
    assert mock_download.call_count == 2
    if isinstance(archive_result, OSError):
        mock_read_archive.assert_not_called()
    else:
        mock_read_archive.assert_called_once_with(b"crate archive", "/Cargo.toml")


@pytest.mark.parametrize(
    ("filename", "content", "expected_log"),
    [
        ("Cargo.lock", "not valid =", "Failed to parse Cargo.lock"),
        ("Cargo.toml", "not valid =", "Failed to parse Cargo.toml"),
    ],
)
def test_invalid_cargo_file_is_ignored(
    mocker: pytest_mock.MockFixture,
    caplog: LogCaptureFixture,
    filename: str,
    content: str,
    expected_log: str,
) -> None:
    source_code_manager = _source_code_manager()
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_join",
        side_effect=lambda *parts: "/".join(parts),
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.path_exists",
        return_value=True,
    )

    def open_file(path: str) -> str:
        if path.endswith(filename):
            return content
        return "version = 4\n"

    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.open_file",
        side_effect=open_file,
    )
    mock_download = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies."
        "rust_crates_io_collection_strategy.download_url"
    )
    strategy = RustCratesIoMetadataCollectionStrategy(
        "project",
        source_code_manager,
        local_project_path="/project",
    )

    with caplog.at_level(logging.WARNING):
        result = strategy.augment_metadata([_metadata("regex", "1.0.0")])

    assert result == [_metadata("regex", "1.0.0")]
    assert expected_log in caplog.text
    mock_path_exists.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_path_exists.call_count == 2
    mock_open_file.assert_has_calls(
        [call("/project/Cargo.lock"), call("/project/Cargo.toml")]
    )
    assert mock_open_file.call_count == 2
    mock_download.assert_not_called()
