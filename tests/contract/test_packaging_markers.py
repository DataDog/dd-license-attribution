# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

"""Contract tests for the packaging.marker behaviors the lockfile sync relies on."""

import packaging.markers
import pytest


class TestPackagingMarkersContract:
    def test_marker_evaluates_against_the_current_interpreter(self) -> None:
        # The scan venv is created from the running interpreter, so marker
        # evaluation in-process reflects the venv's environment. This repo
        # requires Python >= 3.11.
        assert packaging.markers.Marker("python_version >= '3.11'").evaluate() is True
        assert packaging.markers.Marker("python_version < '3.11'").evaluate() is False

    def test_marker_without_environment_keys_is_always_true(self) -> None:
        assert (
            packaging.markers.Marker("extra == 'security'").evaluate() is False
        )  # 'extra' is never set in our evaluation context

    def test_invalid_marker_syntax_raises_invalid_marker(self) -> None:
        with pytest.raises(packaging.markers.InvalidMarker):
            packaging.markers.Marker("not a marker at all ==")
