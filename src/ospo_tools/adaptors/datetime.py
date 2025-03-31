# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

"""Here we collect a set of datetime wrappers and adaptors to be easily replaced during testing and debugging."""

from datetime import datetime
import pytz


def get_datetime_now() -> datetime:
    return datetime.now(pytz.UTC)
