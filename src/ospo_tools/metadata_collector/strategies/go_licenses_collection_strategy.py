import http.client
from io import StringIO
import os
import re
import sys
import csv

from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.metadata_collector.purl_parser import PurlParser
from ospo_tools.metadata_collector.strategies.abstract_collection_strategy import (
    MetadataCollectionStrategy,
)


def change_directory(dir_name: str) -> None:
    os.chdir(dir_name)


def get_current_working_directory() -> str:
    return os.getcwd()


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
                    package.license.append(hint["license"])
            updated_metadata.append(package)
        return updated_metadata
