# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from abc import ABC, abstractmethod

from dd_license_attribution.metadata_collector.metadata import Metadata


class ReportingWritter(ABC):
    @abstractmethod
    def write(self, metadata: list[Metadata]) -> str:
        raise NotImplementedError
