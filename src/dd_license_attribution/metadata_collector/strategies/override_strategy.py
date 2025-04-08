from dd_license_attribution.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)
from enum import Enum
from dataclasses import dataclass
from typing import Dict, Any
from dd_license_attribution.metadata_collector.metadata import Metadata


class OverrideType(Enum):
    """
    Enum for different types of overrides.
    """

    ADD = "add"
    REMOVE = "remove"
    REPLACE = "replace"


class OverrideMatchField(Enum):
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
    matcher: Dict[OverrideMatchField, str]
    replacement: Metadata | None


class OverrideCollectionStrategy(MetadataCollectionStrategy):
    """
    A metadata collection strategy that overrides specific elements in the metadata.
    """

    def __init__(self, override_rules: list[OverrideRule]) -> None:
        self.override_rules = override_rules
        self.matched_rules: list[OverrideRule] = []

    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        # find the matching rules for each metadata
        for meta in metadata:
            for rule in self.override_rules:
                # check if the rule matches the metadata
                if rule.matcher and all(
                    (field == OverrideMatchField.COMPONENT and meta.name == value)
                    or (field == OverrideMatchField.ORIGIN and meta.origin == value)
                    for field, value in rule.matcher.items()
                ):
                    # apply the override based on the rule type
                    if rule.override_type == OverrideType.ADD:
                        if rule.replacement is None:
                            raise ValueError(
                                "Replacement for add should always be a dictionary."
                            )
                        metadata.append(rule.replacement)
                        self.matched_rules.append(rule)
                    elif rule.override_type == OverrideType.REMOVE:
                        metadata.remove(meta)
                        self.matched_rules.append(rule)
                    elif rule.override_type == OverrideType.REPLACE:
                        if rule.replacement is None:
                            raise ValueError(
                                "Replacement for replace should always be a dictionary."
                            )
                        metadata.remove(meta)
                        metadata.append(rule.replacement)
                        self.matched_rules.append(rule)
        return metadata

    def all_matches_used(self) -> bool:
        """
        Check if all matches in the override rules are used.
        """
        # dedup the matched rules
        unique_rules = []
        for rule in self.matched_rules:
            if rule not in unique_rules:
                unique_rules.append(rule)
        self.matched_rules = unique_rules

        return len(self.matched_rules) == len(self.override_rules)

    @staticmethod
    def json_to_override_rules(json_obj: list[dict[str, Any]]) -> list[OverrideRule]:
        """
        Convert a JSON object to a list of OverrideRule objects.
        """
        override_rules = []
        for rule in json_obj:
            matchers: Dict[OverrideMatchField, str] = {}
            for matcher in rule.get("matcher", {}):
                try:
                    match_field = OverrideMatchField(matcher)
                except Exception as e:
                    print(f"Error: {e}")
                    raise ValueError(
                        f"Matcher field must be a origin or component: {matcher}"
                    )
                match_value = rule["matcher"][matcher]
                matchers[match_field] = match_value
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
                matcher=matchers,
                replacement=replacement,
            )
            override_rules.append(override_rule)
        return override_rules
