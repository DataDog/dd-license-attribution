# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.cleanup_copyright_metadata_strategy import (
    CleanupCopyrightMetadataStrategy,
)


def test_cleanup_copyright_metadata() -> None:
    strategy = CleanupCopyrightMetadataStrategy()
    mock_metadata = [
        Metadata(
            name="remove Copyright and 2024",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=["Copyright 2024 Datadog"],
        ),
        Metadata(
            name="remove leading space, 2023-2024, and (c)",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=[" Chartcat Meow 2023-2024 (c)"],
        ),
        Metadata(
            name="remove 2023 - present and copyright",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=["2023 - present Datadog, Inc.", "copyright Filefish"],
        ),
        Metadata(
            name="remove 1 Datadog",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=["Datadog", "Datadog"],
        ),
        Metadata(
            name="no changes",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=["Datadog & Copycat", "Datadog"],
        ),
    ]

    result = strategy.augment_metadata(mock_metadata)
    assert result == [
        Metadata(
            name="remove Copyright and 2024",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=["Datadog"],
        ),
        Metadata(
            name="remove leading space, 2023-2024, and (c)",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=["Chartcat Meow"],
        ),
        Metadata(
            name="remove 2023 - present and copyright",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=["Datadog, Inc.", "Filefish"],
        ),
        Metadata(
            name="remove 1 Datadog",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=["Datadog"],
        ),
        Metadata(
            name="no changes",
            origin=None,
            local_src_path=None,
            license=[],
            version=None,
            copyright=["Datadog", "Datadog & Copycat"],
        ),
    ]
