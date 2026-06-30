# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from abc import ABC, abstractmethod

from dd_license_attribution.metadata_collector.metadata import Metadata


class MetadataCollectionStrategy(ABC):
    @abstractmethod
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        raise NotImplementedError


class DependencyFinderStrategy(MetadataCollectionStrategy):
    """Base for experimental strategies that only grow the dependency graph.

    Implementations must append new Metadata entries but must not set license
    or copyright — those are the exclusive concern of MetadataEnricherStrategy.
    """

    @abstractmethod
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        raise NotImplementedError


class MetadataEnricherStrategy(MetadataCollectionStrategy):
    """Base for experimental strategies that only extract license and copyright.

    Implementations must not add new Metadata entries — dependency discovery is
    the exclusive concern of DependencyFinderStrategy.  Data already fetched
    (clones, API responses) during the finder phase must be reused via the
    shared cache rather than re-fetched.
    """

    @abstractmethod
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        raise NotImplementedError
