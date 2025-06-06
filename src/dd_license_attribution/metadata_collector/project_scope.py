# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from enum import Enum


class ProjectScope(Enum):
    ONLY_ROOT_PROJECT = "Only Root Project"
    ONLY_TRANSITIVE_DEPENDENCIES = "Only Transitive Dependencies"
    ALL = "All"
