from io import StringIO
import csv

from giturlparse import parse as giturlparse

from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


def blob_to_tree_url(blob_url: str) -> str:
    parsed = giturlparse(blob_url)
    if not parsed.valid:
        return blob_url
    if "blob/" in parsed.normalized:
        directory_path = "/".join(parsed.path.split("/")[:-1])
        new_url = f"{parsed.protocol}://{parsed.resource}/{parsed.owner}/{parsed.repo}/tree/{directory_path}"
        return new_url
    return blob_url


class GoLicensesMetadataCollectionStrategy(MetadataCollectionStrategy):
    def __init__(self, go_licenses_report_hint: str) -> None:
        expected_columns = ["name", "license_url", "license"]
        csv_reader = csv.DictReader(
            StringIO(go_licenses_report_hint), fieldnames=expected_columns
        )
        self.go_licenses_from_hint = list(csv_reader)

    # method to get the metadata
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]:
        updated_metadata = []
        for package in metadata:
            for hint in self.go_licenses_from_hint:
                if package.name == f"{hint['name']}":
                    if (
                        hint["license"] not in package.license
                        and hint["license"] != "Unknown"
                    ):
                        package.license.append(hint["license"])
                    if not hint["license_url"]:
                        continue
                    hint_origin = giturlparse(hint["license_url"])
                    if not hint_origin.valid:
                        continue
                    if not package.origin and hint_origin.valid:
                        package.origin = blob_to_tree_url(hint["license_url"])
                        continue
                    parsed_origin = giturlparse(package.origin)
                    if not parsed_origin.valid and hint_origin.valid:
                        package.origin = blob_to_tree_url(hint["license_url"])
                        continue
            updated_metadata.append(package)
        return updated_metadata
