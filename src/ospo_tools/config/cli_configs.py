from dataclasses import dataclass


@dataclass
class Config:
    preset_license_file_locations: list[str]
    preset_copyright_file_locations: list[str]


default_config = Config(
    preset_license_file_locations=[
        "LICENSE",
        "LICENSE.code",
        "LICENSE.txt",
        "LICENSE.md",
        "COPYING",
        "LICENCE",  # I know it is misspelled, but it is common in the wild
        "LICENCE.md",  # I know it is misspelled, but it is common in the wild
        "license/LICENSE.txt",
    ],
    preset_copyright_file_locations=[
        "NOTICE",
        "NOTICE.md",
        "NOTICE.txt",
        "AUTHORS",
        "AUTHORS.md",
        "AUTHORS.txt",
        "CONTRIBUTORS",
        "CONTRIBUTORS.md",
        "CONTRIBUTORS.txt",
    ],
)
