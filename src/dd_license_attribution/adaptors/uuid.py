# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.

"""UUID wrappers that can be replaced during testing."""

from uuid import uuid4


def get_uuid4() -> str:
    return str(uuid4())
