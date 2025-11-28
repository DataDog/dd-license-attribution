# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict

from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


class OverrideType(Enum):
    """
    Enum for different types of overrides.
    """

    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"


class OverrideTargetField(Enum):
    """
    Enum for different fields that can be matched for overrides.
    """

    ORIGIN = "origin"
    COMPONENT = "component"


@dataclass
class OverrideRule:
    """
    A class representing a rule for overriding metadata.
    """

    override_type: OverrideType
    target: Dict[OverrideTargetField, str]
    replacement: Metadata | None


class OverrideCollectionStrategy(MetadataCollectionStrategy):
    """
    A metadata collection strategy that overrides specific elements in the metadata.
    """

    def __init__(self, override_rules: list[OverrideRule]) -> None:
        self.override_rules = override_rules
        self.unused_rules = override_rules

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        # find the matching rules for each metadata
        for meta in metadata:
            for rule in self.override_rules:
                # check if the rule matches the metadata
                if rule.target and all(
                    (field == OverrideTargetField.COMPONENT and meta.name == value)
                    or (field == OverrideTargetField.ORIGIN and meta.origin == value)
                    for field, value in rule.target.items()
                ):
                    # apply the override based on the rule type
                    if rule.override_type == OverrideType.ADD:
                        if rule.replacement is None:
                            raise ValueError(
                                "Replacement for add should always be a dictionary."
                            )
                        metadata.append(rule.replacement)
                        # remove the rule from the unused rules
                        self.unused_rules.remove(rule)
                    elif rule.override_type == OverrideType.REMOVE:
                        metadata.remove(meta)
                        # remove the rule from the unused rules
                        self.unused_rules.remove(rule)
                    elif rule.override_type == OverrideType.REPLACE:
                        if rule.replacement is None:
                            raise ValueError(
                                "Replacement for replace should always be a dictionary."
                            )
                        metadata.remove(meta)
                        metadata.append(rule.replacement)
                        # remove the rule from the unused rules
                        self.unused_rules.remove(rule)
        return metadata

    def unused_targets(self) -> list[dict[OverrideTargetField, str]]:
        return [rule.target for rule in self.unused_rules]

    @staticmethod
    def json_to_override_rules(json_obj: list[dict[str, Any]]) -> list[OverrideRule]:
        """
        Convert a JSON object to a list of OverrideRule objects.
        """
        override_rules = []
        for rule in json_obj:
            targets: Dict[OverrideTargetField, str] = {}
            for target in rule.get("target", {}):
                try:
                    match_field = OverrideTargetField(target)
                except Exception as e:
                    print(f"Error: {e}")
                    raise ValueError(
                        f"Target field must be a origin or component: {target}"
                    )
                match_value = rule["target"][target]
                targets[match_field] = match_value
            replacement_data = rule.get("replacement", {})
            # if replacement_data is None it has to be a REMOVE rule
            if replacement_data is None and rule["override_type"] != "remove":
                raise ValueError("Replacement for remove should always be empty.")
            # if rule is a ADD or REPLACE rule, validate the replacement data is not None
            if replacement_data is None and (
                rule["override_type"] == "add" or rule["override_type"] == "replace"
            ):
                raise ValueError(
                    "Replacement must be a dictionary if for add or replace rules."
                )

            # Validate and add missing fields with default values
            replacement = None
            if rule["override_type"] != "remove":
                replacement = Metadata(
                    name=replacement_data.get("name", ""),
                    origin=replacement_data.get("origin", ""),
                    version=replacement_data.get("version", ""),
                    local_src_path=None,
                    license=replacement_data.get("license", []),
                    copyright=replacement_data.get("copyright", []),
                )
            override_rule = OverrideRule(
                override_type=OverrideType(rule["override_type"]),
                target=targets,
                replacement=replacement,
            )
            override_rules.append(override_rule)
        return override_rules
