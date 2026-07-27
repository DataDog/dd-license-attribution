# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from collections.abc import Iterator
from unittest.mock import Mock, call

import pytest
import pytest_mock

from dd_license_attribution.artifact_management.artifact_manager import (
    SourceCodeReference,
)
from dd_license_attribution.artifact_management.rust_package_resolver import (
    SYNTHETIC_PACKAGE_NAME,
)
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.project_scope import ProjectScope
from dd_license_attribution.metadata_collector.strategies.rust_collection_strategy import (
    RUST_LICENSE_TOOL_COMMAND,
    RUST_LICENSE_TOOL_COMMAND_TIMEOUT_SECONDS,
    RUST_LICENSE_TOOL_INSTALL_HINT,
    RustLicenseToolNotInstalledError,
    RustMetadataCollectionStrategy,
    _looks_like_missing_binary,
    ensure_rust_license_tool_installed,
    is_rust_metadata,
)


def _csv_output() -> str:
    return (
        "Component,Origin,License,Copyright\n"
        f"{SYNTHETIC_PACKAGE_NAME},,,\n"
        "serde,https://github.com/serde-rs/serde,MIT OR Apache-2.0,"
        "The serde developers\n"
        "anyhow,https://github.com/dtolnay/anyhow,MIT OR Apache-2.0,"
        "David Tolnay\n"
        "blank-origin,,,\n"
    )


def _dependency_only_csv_output() -> str:
    return (
        "Component,Origin,License,Copyright\n"
        "anyhow,https://github.com/dtolnay/anyhow,MIT OR Apache-2.0,"
        "David Tolnay\n"
    )


def _mock_source_code_manager() -> Mock:
    source_code_manager = Mock()
    source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/org/repo",
        None,
    )
    return source_code_manager


def _patch_common_io(
    mocker: pytest_mock.MockFixture,
    csv_content: str = "",
    cargo_toml: str = "",
) -> tuple[Mock, Mock, Mock, Mock]:
    def fake_path_join(*args: str) -> str:
        return "/".join(args)

    mock_path_join = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.path_exists",
        return_value=True,
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.open_file",
        return_value=cargo_toml,
    )
    mock_run_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.run_command_with_check",
        return_value=(0, csv_content, ""),
    )
    return mock_path_join, mock_path_exists, mock_open_file, mock_run_command


def _assert_dump_called_once(mock_run_command: Mock, cwd: str) -> None:
    mock_run_command.assert_called_once_with(
        [RUST_LICENSE_TOOL_COMMAND, "dump"],
        cwd=cwd,
        timeout=RUST_LICENSE_TOOL_COMMAND_TIMEOUT_SECONDS,
    )


def test_local_project_path_ingests_csv_and_filters_seed_entries(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            _csv_output(),
            '[package]\nname = "serde"\nversion = "1.0.0"\n',
        )
    )
    strategy = RustMetadataCollectionStrategy(
        "serde@1.0",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )
    initial_metadata = [
        Metadata(
            name="serde@1.0",
            origin="serde@1.0",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="existing",
            origin="existing-origin",
            local_src_path=None,
            license=["BSD-3-Clause"],
            version="1.0.0",
            copyright=["Existing"],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == [
        Metadata(
            name="existing",
            origin="existing-origin",
            local_src_path=None,
            license=["BSD-3-Clause"],
            version="1.0.0",
            copyright=["Existing"],
        ),
        Metadata(
            name="serde",
            origin="https://github.com/serde-rs/serde",
            local_src_path="/tmp/rust-resolve/serde",
            license=["MIT OR Apache-2.0"],
            version="1.0.0",
            copyright=["The serde developers"],
        ),
        Metadata(
            name="anyhow",
            origin="https://github.com/dtolnay/anyhow",
            local_src_path=None,
            license=["MIT OR Apache-2.0"],
            version=None,
            copyright=["David Tolnay"],
        ),
        Metadata(
            name="blank-origin",
            origin="",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]
    source_code_manager.get_canonical_urls.assert_not_called()
    source_code_manager.get_code.assert_not_called()
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_join.assert_called_once_with("/tmp/rust-resolve/serde", "Cargo.toml")
    mock_path_exists.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")
    mock_open_file.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")


def test_local_project_path_preserves_root_when_tool_omits_root_row(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            _dependency_only_csv_output(),
            '[package]\nname = "serde"\nversion = "1.0.0"\n',
        )
    )
    strategy = RustMetadataCollectionStrategy(
        "serde@1.0",
        source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/rust-resolve/serde",
    )

    result = strategy.augment_metadata(
        [
            Metadata(
                name="serde@1.0",
                origin="serde@1.0",
                local_src_path=None,
                license=[],
                version=None,
                copyright=[],
            )
        ]
    )

    assert result == [
        Metadata(
            name="serde",
            origin="serde",
            local_src_path="/tmp/rust-resolve/serde",
            license=[],
            version="1.0.0",
            copyright=[],
        )
    ]
    source_code_manager.get_canonical_urls.assert_not_called()
    source_code_manager.get_code.assert_not_called()
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_join.assert_called_once_with("/tmp/rust-resolve/serde", "Cargo.toml")
    mock_path_exists.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")
    mock_open_file.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")


def test_rust_metadata_replaces_fallback_origin_without_duplicating_dependency(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            "Component,Origin,License,Copyright\n"
            "base64,https://github.com/marshallpierce/rust-base64,"
            "MIT OR Apache-2.0,"
            "Alice Maz <alice@alicemaz.com>; Marshall Pierce <marshall@mpierce.org>\n",
        )
    )
    strategy = RustMetadataCollectionStrategy(
        "root-crate",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/root-crate",
    )
    initial_metadata = [
        Metadata(
            name="base64",
            origin="base64",
            local_src_path=None,
            license=[],
            version="0.22.1",
            copyright=[],
        )
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == [
        Metadata(
            name="base64",
            origin="https://github.com/marshallpierce/rust-base64",
            local_src_path=None,
            license=["MIT OR Apache-2.0"],
            version="0.22.1",
            copyright=[
                "Alice Maz <alice@alicemaz.com>; Marshall Pierce <marshall@mpierce.org>"
            ],
        )
    ]
    source_code_manager.get_canonical_urls.assert_not_called()
    source_code_manager.get_code.assert_not_called()
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/root-crate")
    mock_path_exists.assert_not_called()
    mock_open_file.assert_not_called()
    mock_path_join.assert_not_called()


def test_rust_metadata_keeps_same_name_non_rust_dependency_separate(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            "Component,Origin,License,Copyright\n"
            "regex,https://github.com/rust-lang/regex,MIT OR Apache-2.0,"
            "The Rust Developers\n",
        )
    )
    strategy = RustMetadataCollectionStrategy(
        "root-crate",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/root-crate",
    )
    non_rust_metadata = Metadata(
        name="regex",
        origin="https://pypi.org/project/regex",
        local_src_path=None,
        license=["Apache-2.0"],
        version="2024.11.6",
        copyright=["Python regex maintainers"],
    )

    result = strategy.augment_metadata([non_rust_metadata])

    assert result == [
        non_rust_metadata,
        Metadata(
            name="regex",
            origin="https://github.com/rust-lang/regex",
            local_src_path=None,
            license=["MIT OR Apache-2.0"],
            version=None,
            copyright=["The Rust Developers"],
        ),
    ]
    assert not is_rust_metadata(result[0])
    assert is_rust_metadata(result[1])
    source_code_manager.get_canonical_urls.assert_not_called()
    source_code_manager.get_code.assert_not_called()
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/root-crate")
    mock_path_exists.assert_not_called()
    mock_open_file.assert_not_called()
    mock_path_join.assert_not_called()


def test_local_project_path_only_root_project_filters_to_requested_crate_and_sets_version(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            _csv_output(),
            '[package]\nname = "serde"\nversion = "1.0.0"\n',
        )
    )
    strategy = RustMetadataCollectionStrategy(
        "serde@1.0",
        source_code_manager,
        ProjectScope.ONLY_ROOT_PROJECT,
        local_project_path="/tmp/rust-resolve/serde",
    )

    result = strategy.augment_metadata(
        [
            Metadata(
                name="serde@1.0",
                origin="serde@1.0",
                local_src_path=None,
                license=[],
                version=None,
                copyright=[],
            )
        ]
    )

    assert result == [
        Metadata(
            name="serde",
            origin="https://github.com/serde-rs/serde",
            local_src_path="/tmp/rust-resolve/serde",
            license=["MIT OR Apache-2.0"],
            version="1.0.0",
            copyright=["The serde developers"],
        )
    ]
    source_code_manager.get_code.assert_not_called()
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_join.assert_called_once_with("/tmp/rust-resolve/serde", "Cargo.toml")
    mock_path_exists.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")
    mock_open_file.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")


def test_local_project_path_only_transitive_filters_requested_crate(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            _csv_output(),
            '[package]\nname = "serde"\nversion = "1.0.0"\n',
        )
    )
    strategy = RustMetadataCollectionStrategy(
        "serde@1.0",
        source_code_manager,
        ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES,
        local_project_path="/tmp/rust-resolve/serde",
    )

    result = strategy.augment_metadata(
        [
            Metadata(
                name="serde@1.0",
                origin="serde@1.0",
                local_src_path=None,
                license=[],
                version=None,
                copyright=[],
            )
        ]
    )

    assert [metadata.name for metadata in result] == ["anyhow", "blank-origin"]
    assert not any(metadata.name == "serde" for metadata in result)
    source_code_manager.get_code.assert_not_called()
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_join.assert_called_once_with("/tmp/rust-resolve/serde", "Cargo.toml")
    mock_path_exists.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")
    mock_open_file.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")


def test_github_mode_walks_sibling_cargo_projects_and_filters_roots_for_transitive_scope(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/org/repo",
        branch="main",
        local_root_path="/cache/org_repo",
        local_full_path="/cache/org_repo",
    )
    mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.walk_directory",
        return_value=[
            ("/cache/org_repo", ["crate-a", "crate-b"], []),
            ("/cache/org_repo/crate-a", [], ["Cargo.toml"]),
            ("/cache/org_repo/crate-b", [], ["Cargo.toml"]),
        ],
    )

    def fake_open_file(path: str) -> str:
        if path == "/cache/org_repo/crate-a/Cargo.toml":
            return '[package]\nname = "rootcrate"\n'
        if path == "/cache/org_repo/crate-b/Cargo.toml":
            return '[package]\nname = "helper"\n'
        raise FileNotFoundError

    def fake_path_join(*args: str) -> str:
        return "/".join(args)

    mock_path_join = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.path_join",
        side_effect=fake_path_join,
    )
    mock_path_exists = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.path_exists",
        return_value=True,
    )
    mock_open_file = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.open_file",
        side_effect=fake_open_file,
    )
    mock_run_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.run_command_with_check",
        side_effect=[
            (
                0,
                "Component,Origin,License,Copyright\n"
                "rootcrate,https://github.com/org/repo,Apache-2.0,Datadog\n"
                "dep1,https://github.com/org/dep1,MIT,Alice\n",
                "",
            ),
            (
                0,
                "Component,Origin,License,Copyright\n"
                "helper,https://github.com/org/repo/tree/main/crates/helper,"
                "Apache-2.0,Datadog\n"
                "dep2,https://github.com/org/dep2,BSD-3-Clause,Bob\n",
                "",
            ),
        ],
    )
    strategy = RustMetadataCollectionStrategy(
        "https://github.com/org/repo",
        source_code_manager,
        ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES,
    )
    initial_metadata = [
        Metadata(
            name="github.com/org/repo",
            origin="https://github.com/org/repo",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        )
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert [metadata.name for metadata in result] == [
        "dep1",
        "dep2",
    ]
    source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/org/repo"
    )
    source_code_manager.get_code.assert_called_once_with("https://github.com/org/repo")
    mock_run_command.assert_has_calls(
        [
            call(
                [
                    RUST_LICENSE_TOOL_COMMAND,
                    "dump",
                ],
                cwd="/cache/org_repo/crate-a",
                timeout=RUST_LICENSE_TOOL_COMMAND_TIMEOUT_SECONDS,
            ),
            call(
                [
                    RUST_LICENSE_TOOL_COMMAND,
                    "dump",
                ],
                cwd="/cache/org_repo/crate-b",
                timeout=RUST_LICENSE_TOOL_COMMAND_TIMEOUT_SECONDS,
            ),
        ]
    )
    mock_path_exists.assert_has_calls(
        [
            call("/cache/org_repo/crate-a/Cargo.toml"),
            call("/cache/org_repo/crate-b/Cargo.toml"),
        ]
    )
    mock_open_file.assert_has_calls(
        [
            call("/cache/org_repo/crate-a/Cargo.toml"),
            call("/cache/org_repo/crate-b/Cargo.toml"),
        ]
    )
    assert mock_path_join.call_count == 2


def test_github_mode_transitive_scope_removes_seed_when_no_code_available(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    source_code_manager.get_code.return_value = None
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.walk_directory"
    )
    strategy = RustMetadataCollectionStrategy(
        "https://github.com/org/repo",
        source_code_manager,
        ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES,
    )
    initial_metadata = [
        Metadata(
            name="github.com/org/repo",
            origin="https://github.com/org/repo",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
        Metadata(
            name="preserved-dep",
            origin="https://github.com/org/preserved-dep",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        ),
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == [
        Metadata(
            name="preserved-dep",
            origin="https://github.com/org/preserved-dep",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        )
    ]
    source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/org/repo"
    )
    source_code_manager.get_code.assert_called_once_with("https://github.com/org/repo")
    mock_walk_directory.assert_not_called()


def test_github_mode_transitive_scope_removes_canonicalized_seed(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    source_code_manager.get_canonical_urls.return_value = (
        "https://github.com/new-org/new-repo",
        "https://api.github.com/repos/new-org/new-repo",
    )
    source_code_manager.get_code.return_value = SourceCodeReference(
        repo_url="https://github.com/new-org/new-repo",
        branch="main",
        local_root_path="/cache/new-org-new-repo",
        local_full_path="/cache/new-org-new-repo",
    )
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.walk_directory",
        return_value=[],
    )
    mock_run_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.run_command_with_check"
    )
    strategy = RustMetadataCollectionStrategy(
        "https://github.com/old-org/old-repo",
        source_code_manager,
        ProjectScope.ONLY_TRANSITIVE_DEPENDENCIES,
    )
    initial_metadata = [
        Metadata(
            name="github.com/new-org/new-repo",
            origin="https://github.com/new-org/new-repo",
            local_src_path=None,
            license=["Apache-2.0"],
            version=None,
            copyright=["Datadog"],
        )
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == []
    source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/old-org/old-repo"
    )
    source_code_manager.get_code.assert_called_once_with(
        "https://github.com/new-org/new-repo"
    )
    mock_walk_directory.assert_called_once_with("/cache/new-org-new-repo")
    mock_run_command.assert_not_called()


def test_find_cargo_project_roots_prunes_nested_projects(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    strategy = RustMetadataCollectionStrategy(
        "https://github.com/org/repo",
        source_code_manager,
        ProjectScope.ALL,
    )

    def fake_walk_directory(
        source_root: str,
    ) -> Iterator[tuple[str, list[str], list[str]]]:
        root_dirs = ["crates", "target", ".git"]
        yield source_root, root_dirs, ["Cargo.toml"]
        if "crates" in root_dirs:
            yield f"{source_root}/crates/helper", [], ["Cargo.toml"]

    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.walk_directory",
        side_effect=fake_walk_directory,
    )

    result = strategy._find_cargo_project_roots("/cache/org_repo")

    assert result == ["/cache/org_repo"]
    source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/org/repo"
    )
    mock_walk_directory.assert_called_once_with("/cache/org_repo")


def test_github_mode_returns_unchanged_metadata_when_no_code_available(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    source_code_manager.get_code.return_value = None
    mock_walk_directory = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.walk_directory"
    )
    strategy = RustMetadataCollectionStrategy(
        "https://github.com/org/repo",
        source_code_manager,
        ProjectScope.ALL,
    )
    initial_metadata = [
        Metadata(
            name="github.com/org/repo",
            origin="https://github.com/org/repo",
            local_src_path=None,
            license=[],
            version=None,
            copyright=[],
        )
    ]

    result = strategy.augment_metadata(initial_metadata)

    assert result == initial_metadata
    source_code_manager.get_canonical_urls.assert_called_once_with(
        "https://github.com/org/repo"
    )
    source_code_manager.get_code.assert_called_once_with("https://github.com/org/repo")
    mock_walk_directory.assert_not_called()


def test_ensure_rust_license_tool_installed_runs_version_check(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_run_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.run_command_with_check",
        return_value=(0, "dd-rust-license-tool 0.1.0", ""),
    )

    ensure_rust_license_tool_installed()

    mock_run_command.assert_called_once_with(
        [RUST_LICENSE_TOOL_COMMAND, "--version"],
        timeout=RUST_LICENSE_TOOL_COMMAND_TIMEOUT_SECONDS,
    )


def test_ensure_rust_license_tool_installed_raises_when_binary_is_missing(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_run_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.run_command_with_check",
        side_effect=FileNotFoundError("dd-rust-license-tool not found"),
    )

    with pytest.raises(RustLicenseToolNotInstalledError) as exc_info:
        ensure_rust_license_tool_installed()

    assert str(exc_info.value) == RUST_LICENSE_TOOL_INSTALL_HINT
    mock_run_command.assert_called_once_with(
        [RUST_LICENSE_TOOL_COMMAND, "--version"],
        timeout=RUST_LICENSE_TOOL_COMMAND_TIMEOUT_SECONDS,
    )


def test_ensure_rust_license_tool_installed_raises_for_os_error(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_run_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.run_command_with_check",
        side_effect=OSError("permission denied"),
    )

    with pytest.raises(RustLicenseToolNotInstalledError) as exc_info:
        ensure_rust_license_tool_installed()

    assert str(exc_info.value) == RUST_LICENSE_TOOL_INSTALL_HINT
    mock_run_command.assert_called_once_with(
        [RUST_LICENSE_TOOL_COMMAND, "--version"],
        timeout=RUST_LICENSE_TOOL_COMMAND_TIMEOUT_SECONDS,
    )


def test_ensure_rust_license_tool_installed_raises_when_version_check_fails(
    mocker: pytest_mock.MockFixture,
) -> None:
    mock_run_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.run_command_with_check",
        return_value=(1, "version stdout", "version stderr"),
    )

    with pytest.raises(RustLicenseToolNotInstalledError) as exc_info:
        ensure_rust_license_tool_installed()

    assert RUST_LICENSE_TOOL_INSTALL_HINT in str(exc_info.value)
    assert "stdout:\nversion stdout\nstderr:\nversion stderr" in str(exc_info.value)
    mock_run_command.assert_called_once_with(
        [RUST_LICENSE_TOOL_COMMAND, "--version"],
        timeout=RUST_LICENSE_TOOL_COMMAND_TIMEOUT_SECONDS,
    )


def test_missing_dd_rust_license_tool_raises_typed_error(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    _, mock_path_exists, mock_open_file, mock_run_command = _patch_common_io(
        mocker, _csv_output()
    )
    mock_run_command.side_effect = FileNotFoundError("dd-rust-license-tool not found")
    strategy = RustMetadataCollectionStrategy(
        "serde",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )

    with pytest.raises(RustLicenseToolNotInstalledError) as exc_info:
        strategy.augment_metadata([])

    assert str(exc_info.value) == RUST_LICENSE_TOOL_INSTALL_HINT
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_exists.assert_not_called()
    mock_open_file.assert_not_called()


def test_nonzero_missing_binary_output_raises_typed_error(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    _, mock_path_exists, mock_open_file, mock_run_command = _patch_common_io(
        mocker, _csv_output()
    )
    mock_run_command.return_value = (
        127,
        "",
        "dd-rust-license-tool: command not found",
    )
    strategy = RustMetadataCollectionStrategy(
        "serde",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )

    with pytest.raises(RustLicenseToolNotInstalledError):
        strategy.augment_metadata([])

    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_exists.assert_not_called()
    mock_open_file.assert_not_called()


@pytest.mark.parametrize(
    "error_text",
    [
        "dd-rust-license-tool: command not found",
        "No such file or directory: dd-rust-license-tool",
        "could not execute dd-rust-license-tool",
    ],
)
def test_missing_binary_detection_matches_supported_errors(error_text: str) -> None:
    assert _looks_like_missing_binary(error_text)


@pytest.mark.parametrize(
    "error_text",
    [
        "cargo: command not found",
        "dd-rust-license-tool returned an invalid CSV",
        "permission denied",
    ],
)
def test_missing_binary_detection_rejects_unrelated_errors(error_text: str) -> None:
    assert not _looks_like_missing_binary(error_text)


def test_invalid_csv_keeps_non_seed_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            "bad,header\nvalue,value\n",
            '[package]\nname = "serde"\nversion = "1.0.0"\n',
        )
    )
    strategy = RustMetadataCollectionStrategy(
        "serde",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )
    preserved_metadata = Metadata(
        name="existing",
        origin="existing-origin",
        local_src_path=None,
        license=["MIT"],
        version=None,
        copyright=[],
    )

    result = strategy.augment_metadata(
        [
            Metadata(
                name="serde",
                origin="serde",
                local_src_path=None,
                license=[],
                version=None,
                copyright=[],
            ),
            preserved_metadata,
        ]
    )

    assert result == [
        preserved_metadata,
        Metadata(
            name="serde",
            origin="serde",
            local_src_path="/tmp/rust-resolve/serde",
            license=[],
            version="1.0.0",
            copyright=[],
        ),
    ]
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_join.assert_called_once_with("/tmp/rust-resolve/serde", "Cargo.toml")
    mock_path_exists.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")
    mock_open_file.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")


def test_empty_tool_output_keeps_non_seed_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            "",
            '[package]\nname = "dd-rust-license-tool"\nversion = "1.0.6"\n',
        )
    )
    mock_run_command.return_value = (
        0,
        "",
        "warning: ddla-rust-resolve ignoring invalid dependency",
    )
    strategy = RustMetadataCollectionStrategy(
        "dd-rust-license-tool",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/dd-rust-license-tool",
    )
    preserved_metadata = Metadata(
        name="existing",
        origin="existing-origin",
        local_src_path=None,
        license=["MIT"],
        version=None,
        copyright=[],
    )

    result = strategy.augment_metadata(
        [
            Metadata(
                name="dd-rust-license-tool",
                origin="dd-rust-license-tool",
                local_src_path=None,
                license=[],
                version=None,
                copyright=[],
            ),
            preserved_metadata,
        ]
    )

    assert result == [
        preserved_metadata,
        Metadata(
            name="dd-rust-license-tool",
            origin="dd-rust-license-tool",
            local_src_path="/tmp/rust-resolve/dd-rust-license-tool",
            license=[],
            version="1.0.6",
            copyright=[],
        ),
    ]
    _assert_dump_called_once(
        mock_run_command,
        "/tmp/rust-resolve/dd-rust-license-tool",
    )
    mock_path_join.assert_called_once_with(
        "/tmp/rust-resolve/dd-rust-license-tool", "Cargo.toml"
    )
    mock_path_exists.assert_called_once_with(
        "/tmp/rust-resolve/dd-rust-license-tool/Cargo.toml"
    )
    mock_open_file.assert_called_once_with(
        "/tmp/rust-resolve/dd-rust-license-tool/Cargo.toml"
    )


def test_local_project_path_value_error_when_missing(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    strategy = RustMetadataCollectionStrategy(
        "serde",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )
    strategy.local_project_path = None
    mock_run_command = mocker.patch(
        "dd_license_attribution.metadata_collector.strategies.rust_collection_strategy.run_command_with_check"
    )

    with pytest.raises(ValueError):
        strategy._augment_metadata_from_local_path([])

    source_code_manager.get_canonical_urls.assert_not_called()
    mock_run_command.assert_not_called()


def test_os_error_that_looks_like_missing_binary_raises_typed_error(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    _, mock_path_exists, mock_open_file, mock_run_command = _patch_common_io(
        mocker, _csv_output()
    )
    mock_run_command.side_effect = OSError("dd-rust-license-tool: no such file")
    strategy = RustMetadataCollectionStrategy(
        "serde",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )

    with pytest.raises(RustLicenseToolNotInstalledError):
        strategy.augment_metadata([])

    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_exists.assert_not_called()
    mock_open_file.assert_not_called()


def test_non_missing_os_error_returns_non_seed_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            _csv_output(),
            '[package]\nname = "serde"\nversion = "1.0.0"\n',
        )
    )
    mock_run_command.side_effect = OSError("permission denied")
    strategy = RustMetadataCollectionStrategy(
        "serde",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )
    preserved_metadata = Metadata(
        name="existing",
        origin="existing-origin",
        local_src_path=None,
        license=["MIT"],
        version=None,
        copyright=[],
    )

    result = strategy.augment_metadata(
        [
            Metadata(
                name="serde",
                origin="serde",
                local_src_path=None,
                license=[],
                version=None,
                copyright=[],
            ),
            preserved_metadata,
        ]
    )

    assert result == [
        preserved_metadata,
        Metadata(
            name="serde",
            origin="serde",
            local_src_path="/tmp/rust-resolve/serde",
            license=[],
            version="1.0.0",
            copyright=[],
        ),
    ]
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_join.assert_called_once_with("/tmp/rust-resolve/serde", "Cargo.toml")
    mock_path_exists.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")
    mock_open_file.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")


def test_nonzero_tool_failure_returns_non_seed_metadata(
    mocker: pytest_mock.MockFixture,
) -> None:
    source_code_manager = _mock_source_code_manager()
    mock_path_join, mock_path_exists, mock_open_file, mock_run_command = (
        _patch_common_io(
            mocker,
            _csv_output(),
            '[package]\nname = "serde"\nversion = "1.0.0"\n',
        )
    )
    mock_run_command.return_value = (1, "stdout", "license-tool error")
    strategy = RustMetadataCollectionStrategy(
        "serde",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )
    preserved_metadata = Metadata(
        name="existing",
        origin="existing-origin",
        local_src_path=None,
        license=["MIT"],
        version=None,
        copyright=[],
    )

    result = strategy.augment_metadata(
        [
            Metadata(
                name="serde",
                origin="serde",
                local_src_path=None,
                license=[],
                version=None,
                copyright=[],
            ),
            preserved_metadata,
        ]
    )

    assert result == [
        preserved_metadata,
        Metadata(
            name="serde",
            origin="serde",
            local_src_path="/tmp/rust-resolve/serde",
            license=[],
            version="1.0.0",
            copyright=[],
        ),
    ]
    _assert_dump_called_once(mock_run_command, "/tmp/rust-resolve/serde")
    mock_path_join.assert_called_once_with("/tmp/rust-resolve/serde", "Cargo.toml")
    mock_path_exists.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")
    mock_open_file.assert_called_once_with("/tmp/rust-resolve/serde/Cargo.toml")


def test_parse_csv_defaults_missing_cells_to_empty_strings() -> None:
    source_code_manager = _mock_source_code_manager()
    strategy = RustMetadataCollectionStrategy(
        "root-crate",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )

    rows = strategy._parse_csv(
        "Component,Origin,License,Copyright\n"
        "serde,https://github.com/serde-rs/serde,,\n"
        ",,MIT,\n"
    )

    assert rows == [
        {
            "Component": "serde",
            "Origin": "https://github.com/serde-rs/serde",
            "License": "",
            "Copyright": "",
        },
        {
            "Component": "",
            "Origin": "",
            "License": "MIT",
            "Copyright": "",
        },
    ]
    source_code_manager.get_canonical_urls.assert_not_called()


def test_parse_crate_name_preserves_version_suffix_after_first_at() -> None:
    source_code_manager = _mock_source_code_manager()
    strategy = RustMetadataCollectionStrategy(
        "root-crate",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )

    result = strategy._parse_crate_name("crate@1.0@metadata")

    assert result == "crate"
    source_code_manager.get_canonical_urls.assert_not_called()


def test_ingest_updates_existing_metadata_when_fields_are_missing() -> None:
    source_code_manager = _mock_source_code_manager()
    strategy = RustMetadataCollectionStrategy(
        "root-crate",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )
    existing_metadata = Metadata(
        name="serde",
        origin="https://github.com/serde-rs/serde",
        local_src_path=None,
        license=[],
        version=None,
        copyright=[],
    )
    metadata = [existing_metadata]

    strategy._ingest_rows(
        metadata,
        [
            {
                "Component": "serde",
                "Origin": "https://github.com/serde-rs/serde",
                "License": "MIT OR Apache-2.0",
                "Copyright": "The serde developers",
            }
        ],
        set(),
    )

    assert metadata == [
        Metadata(
            name="serde",
            origin="https://github.com/serde-rs/serde",
            local_src_path=None,
            license=["MIT OR Apache-2.0"],
            version=None,
            copyright=["The serde developers"],
        )
    ]
    source_code_manager.get_canonical_urls.assert_not_called()


def test_ingest_preserves_existing_fields_when_already_present() -> None:
    source_code_manager = _mock_source_code_manager()
    strategy = RustMetadataCollectionStrategy(
        "root-crate",
        source_code_manager,
        ProjectScope.ALL,
        local_project_path="/tmp/rust-resolve/serde",
    )
    existing_metadata = Metadata(
        name="serde",
        origin="https://github.com/serde-rs/serde",
        local_src_path=None,
        license=["Apache-2.0"],
        version="1.0.0",
        copyright=["Existing"],
    )
    metadata = [existing_metadata]

    strategy._ingest_rows(
        metadata,
        [
            {
                "Component": "serde",
                "Origin": "https://github.com/serde-rs/serde",
                "License": "MIT OR Apache-2.0",
                "Copyright": "The serde developers",
            }
        ],
        set(),
    )

    assert metadata == [
        Metadata(
            name="serde",
            origin="https://github.com/serde-rs/serde",
            local_src_path=None,
            license=["Apache-2.0"],
            version="1.0.0",
            copyright=["Existing"],
        )
    ]
    source_code_manager.get_canonical_urls.assert_not_called()

