import sys
from typing import List

from ospo_tools.metadata_collector.metadata import Metadata


class LicenseChecker:
    """A class to check for cautionary licenses in a list of Metadata objects."""

    def __init__(self, cautionary_licenses: List[str]) -> None:
        self._cautionary_licenses = cautionary_licenses

    def check_cautionary_licenses(self, metadata_list: List[Metadata]) -> None:
        for metadata in metadata_list:
            if not metadata.license:
                continue

            for license_text in metadata.license:
                if self._is_cautionary_license(license_text):
                    msg = "Warning: Package {} has a license ({}) that is in the list of cautionary licenses. Double check that the license is compatible with your project.".format(
                        metadata.name, license_text
                    )
                    print(f"\033[91m{msg}\033[0m", file=sys.stderr)

    def _is_cautionary_license(self, license_text: str) -> bool:
        license_text_upper = license_text.upper()
        return any(
            license_text_upper.startswith(keyword.upper())
            for keyword in self._cautionary_licenses
        )
