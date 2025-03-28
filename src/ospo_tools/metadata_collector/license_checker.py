import sys
from typing import List

from ospo_tools.metadata_collector.metadata import Metadata
from ospo_tools.config.cli_configs import default_config


class LicenseChecker:
    """A class to check for cautionary licenses in a list of Metadata objects."""

    def __init__(self) -> None:
        pass

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
            for keyword in default_config.preset_cautionary_licenses
        )
