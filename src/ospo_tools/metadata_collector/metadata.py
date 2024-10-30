from dataclasses import dataclass


# Keeping this class short initially, we should eventually getting it closer to the CycloneDX/SPDX standard
# as we grow the project.
@dataclass
class Metadata:
    """Metadata class to store metadata of a package."""

    name: str  # AKA component
    version: str  # package version or commit hash
    origin: str  # package manager purl or repository url
    license: str  # SPDX format license
    copyright: str
