# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from abc import ABC, abstractmethod
from typing import List
from ospo_tools.metadata_collector.metadata import Metadata


class MetadataCollectionStrategy(ABC):
    @abstractmethod
    def augment_metadata(self, metadata: List[Metadata]) -> List[Metadata]:
        raise NotImplementedError
