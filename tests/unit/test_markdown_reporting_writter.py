# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

from datetime import datetime

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.report_generator.writters.markdown_reporting_writter import (
    MarkdownReportingWritter,
)


def test_markdown_reporting_writter_writes_combined_metadata_table() -> None:
    metadata = [
        Metadata(
            name="root-project",
            version="1.0.0",
            origin="https://github.com/example/root-project",
            local_src_path=None,
            license=["MIT"],
            copyright=["Copyright root"],
        ),
        Metadata(
            name="dep|alpha",
            version="1.0.0",
            origin="git+ssh://git@github.com/example/dep|alpha.git",
            local_src_path=None,
            license=["MIT"],
            copyright=["Copyright | alpha"],
        ),
        Metadata(
            name="dep|alpha",
            version="1.0.0",
            origin="git+ssh://git@github.com/example/dep|alpha.git",
            local_src_path=None,
            license=["Apache-2.0"],
            copyright=["Copyright beta"],
        ),
        Metadata(
            name="z-dep",
            version="2.0.0",
            origin="git://github.com/example/z-dep.git",
            local_src_path=None,
            license=["BSD-3-Clause"],
            copyright=["Copyright z"],
        ),
    ]

    markdown_report_writter = MarkdownReportingWritter(
        document_name="root-project@1.0.0",
        ecosystem="npm",
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    markdown = markdown_report_writter.write(metadata)

    expected = "\n".join(
        [
            "# License Compliance Report: root-project",
            "",
            "| Field | Value |",
            "| --- | --- |",
            "| Package | `root-project` |",
            "| Version | 1.0.0 |",
            "| Ecosystem | npm |",
            "| Date | 2026-06-24 |",
            "| Dependencies | 2 |",
            "| License | ['MIT'] |",
            "| Copyright | ['Copyright root'] |",
            "",
            "## Third-Party Dependencies",
            "",
            "| Component | Origin | License | Copyright |",
            "| --- | --- | --- | --- |",
            "| dep\\|alpha | git+ssh://git@github.com/example/dep\\|alpha.git | "
            "['Apache-2.0', 'MIT'] | "
            "['Copyright beta', 'Copyright \\| alpha'] |",
            "| z-dep | git://github.com/example/z-dep.git | "
            "['BSD-3-Clause'] | ['Copyright z'] |",
            "",
        ]
    )
    assert markdown == expected


def test_markdown_reporting_writter_escapes_underscores_in_dependency_cells() -> None:
    metadata = [
        Metadata(
            name="root_project",
            version="1.0.0",
            origin="https://github.com/example/root_project",
            local_src_path=None,
            license=["MIT"],
            copyright=["Copyright root"],
        ),
        Metadata(
            name="dep_alpha",
            version="1.0.0",
            origin="https://github.com/example/dep_alpha",
            local_src_path=None,
            license=["MIT_License"],
            copyright=["Copyright dep_alpha"],
        ),
    ]
    markdown_report_writter = MarkdownReportingWritter(
        document_name="root_project@1.0.0",
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    markdown = markdown_report_writter.write(metadata)

    assert "| Package | `root_project` |" in markdown
    assert (
        "| dep\\_alpha | https://github.com/example/dep\\_alpha | "
        "['MIT\\_License'] | ['Copyright dep\\_alpha'] |"
    ) in markdown


def test_markdown_reporting_writter_matches_pypi_exact_version_spec_root() -> None:
    metadata = [
        Metadata(
            name="requests",
            version="2.31.0",
            origin="https://github.com/psf/requests",
            local_src_path=None,
            license=["Apache-2.0"],
            copyright=["Python Software Foundation"],
        ),
        Metadata(
            name="urllib3",
            version="2.2.0",
            origin="https://github.com/urllib3/urllib3",
            local_src_path=None,
            license=["MIT"],
            copyright=["urllib3 contributors"],
        ),
    ]
    markdown_report_writter = MarkdownReportingWritter(
        document_name="Requests==2.31.0",
        ecosystem="pypi",
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    markdown = markdown_report_writter.write(metadata)

    assert markdown.startswith("# License Compliance Report: requests\n")
    assert "| Package | `requests` |" in markdown
    assert "| Version | 2.31.0 |" in markdown
    assert "| Dependencies | 1 |" in markdown
    assert "| License | ['Apache-2.0'] |" in markdown
    assert "| requests | https://github.com/psf/requests |" not in markdown
    assert (
        "| urllib3 | https://github.com/urllib3/urllib3 | "
        "['MIT'] | ['urllib3 contributors'] |"
    ) in markdown


def test_markdown_reporting_writter_matches_rust_requirement_root_by_name() -> None:
    metadata = [
        Metadata(
            name="serde",
            version="1.0.228",
            origin="https://github.com/serde-rs/serde",
            local_src_path=None,
            license=["MIT OR Apache-2.0"],
            copyright=["Serde Developers"],
        ),
        Metadata(
            name="serde_derive",
            version="1.0.228",
            origin="https://github.com/serde-rs/serde",
            local_src_path=None,
            license=["MIT OR Apache-2.0"],
            copyright=["Serde Developers"],
        ),
    ]
    markdown_report_writter = MarkdownReportingWritter(
        document_name="serde@1.0",
        ecosystem="rust",
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    markdown = markdown_report_writter.write(metadata)

    assert markdown.startswith("# License Compliance Report: serde\n")
    assert "| Package | `serde` |" in markdown
    assert "| Version | 1.0.228 |" in markdown
    assert "| Dependencies | 1 |" in markdown
    assert "| License | ['MIT OR Apache-2.0'] |" in markdown
    assert "| serde | https://github.com/serde-rs/serde |" not in markdown
    assert (
        "| serde\\_derive | https://github.com/serde-rs/serde | "
        "['MIT OR Apache-2.0'] | ['Serde Developers'] |"
    ) in markdown


def test_markdown_reporting_writter_matches_exact_rust_version_root() -> None:
    metadata = [
        Metadata(
            name="serde",
            version="1.0.228",
            origin="https://github.com/serde-rs/serde/v1",
            local_src_path=None,
            license=["MIT OR Apache-2.0"],
            copyright=["Serde Developers"],
        ),
        Metadata(
            name="serde",
            version="1.0.229",
            origin="https://github.com/serde-rs/serde/v2",
            local_src_path=None,
            license=["MIT"],
            copyright=["Serde Developers 2"],
        ),
    ]
    markdown_report_writter = MarkdownReportingWritter(
        document_name="serde@1.0.229",
        ecosystem="rust",
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    markdown = markdown_report_writter.write(metadata)

    assert markdown.startswith("# License Compliance Report: serde\n")
    assert "| Package | `serde` |" in markdown
    assert "| Version | 1.0.229 |" in markdown
    assert "| Dependencies | 1 |" in markdown
    assert "| License | ['MIT'] |" in markdown
    assert "| serde | https://github.com/serde-rs/serde/v2 |" not in markdown
    assert (
        "| serde | https://github.com/serde-rs/serde/v1 | "
        "['MIT OR Apache-2.0'] | ['Serde Developers'] |"
    ) in markdown


def test_markdown_reporting_writter_does_not_guess_ambiguous_rust_root_by_name() -> (
    None
):
    metadata = [
        Metadata(
            name="serde",
            version="1.0.228",
            origin="https://github.com/serde-rs/serde/v1",
            local_src_path=None,
            license=["MIT OR Apache-2.0"],
            copyright=["Serde Developers"],
        ),
        Metadata(
            name="serde",
            version="1.0.229",
            origin="https://github.com/serde-rs/serde/v2",
            local_src_path=None,
            license=["MIT"],
            copyright=["Serde Developers 2"],
        ),
    ]
    markdown_report_writter = MarkdownReportingWritter(
        document_name="serde@^1.0",
        ecosystem="rust",
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    markdown = markdown_report_writter.write(metadata)

    assert markdown.startswith("# License Compliance Report: serde\n")
    assert "| Package | `serde` |" in markdown
    assert "| Version | ^1.0 |" in markdown
    assert "| Dependencies | 2 |" in markdown
    assert "| License | [] |" in markdown
    assert (
        "| serde | https://github.com/serde-rs/serde/v1 | "
        "['MIT OR Apache-2.0'] | ['Serde Developers'] |"
    ) in markdown
    assert (
        "| serde | https://github.com/serde-rs/serde/v2 | "
        "['MIT'] | ['Serde Developers 2'] |"
    ) in markdown


def test_markdown_reporting_writter_uses_defaults_for_empty_metadata() -> None:
    markdown_report_writter = MarkdownReportingWritter(
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    markdown = markdown_report_writter.write([])

    expected = "\n".join(
        [
            "# License Compliance Report: sbom",
            "",
            "| Field | Value |",
            "| --- | --- |",
            "| Package | `sbom` |",
            "| Version |  |",
            "| Ecosystem | N/A |",
            "| Date | 2026-06-24 |",
            "| Dependencies | 0 |",
            "| License | [] |",
            "| Copyright | [] |",
            "",
            "## Third-Party Dependencies",
            "",
            "| Component | Origin | License | Copyright |",
            "| --- | --- | --- | --- |",
            "",
        ]
    )
    assert markdown == expected


def test_markdown_reporting_writter_uses_first_metadata_name_and_empty_none_cells() -> (
    None
):
    metadata = [
        Metadata(
            name="root-project",
            version="1.0.0",
            origin="https://github.com/example/root-project",
            local_src_path=None,
            license=["MIT"],
            copyright=["Copyright root"],
        ),
        Metadata(
            name=None,
            version=None,
            origin=None,
            local_src_path=None,
            license=[],
            copyright=[],
        ),
    ]
    markdown_report_writter = MarkdownReportingWritter(
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    markdown = markdown_report_writter.write(metadata)

    assert markdown.startswith("# License Compliance Report: root-project\n")
    assert "| Dependencies | 1 |" in markdown
    assert "| License | ['MIT'] |" in markdown
    assert "| Copyright | ['Copyright root'] |" in markdown
    assert "|  |  | [] | [] |" in markdown


def test_markdown_reporting_writter_handles_scoped_packages_and_preserves_origins() -> (
    None
):
    metadata = [
        Metadata(
            name="@scope/root",
            version="1.2.3",
            origin="github.com/scope/root",
            local_src_path=None,
            license=["Apache-2.0"],
            copyright=["Scope"],
        ),
        Metadata(
            name="dep-a",
            version="1.0.0",
            origin="git@github.com:example/dep-a.git",
            local_src_path=None,
            license=["MIT"],
            copyright=[],
        ),
        Metadata(
            name="dep-b",
            version="2.0.0",
            origin="git+https://github.com/example/dep-b.git",
            local_src_path=None,
            license=["BSD-3-Clause"],
            copyright=[],
        ),
        Metadata(
            name="dep-c",
            version="3.0.0",
            origin="github.com/example/dep-c",
            local_src_path=None,
            license=["ISC"],
            copyright=[],
        ),
    ]
    markdown_report_writter = MarkdownReportingWritter(
        document_name="@scope/root@1.2.3",
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    markdown = markdown_report_writter.write(metadata)

    assert markdown.startswith("# License Compliance Report: @scope/root\n")
    assert "| Version | 1.2.3 |" in markdown
    assert "| dep-a | git@github.com:example/dep-a.git | ['MIT'] | [] |" in markdown
    assert (
        "| dep-b | git+https://github.com/example/dep-b.git | ['BSD-3-Clause'] | [] |"
    ) in markdown
    assert "| dep-c | github.com/example/dep-c | ['ISC'] | [] |" in markdown


def test_markdown_reporting_writter_preserves_unsplit_document_names() -> None:
    git_markdown_report_writter = MarkdownReportingWritter(
        document_name="git@github.com:example/root",
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )
    malformed_markdown_report_writter = MarkdownReportingWritter(
        document_name="root@",
        created_at=lambda: datetime(2026, 6, 24, 12, 30, 0),
    )

    git_markdown = git_markdown_report_writter.write([])
    malformed_markdown = malformed_markdown_report_writter.write([])

    assert git_markdown.startswith(
        "# License Compliance Report: git@github.com:example/root\n"
    )
    assert "| Package | `git@github.com:example/root` |" in git_markdown
    assert "| Version |  |" in git_markdown
    assert malformed_markdown.startswith("# License Compliance Report: root@\n")
    assert "| Package | `root@` |" in malformed_markdown
    assert "| Version |  |" in malformed_markdown
