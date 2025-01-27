from dataclasses import dataclass


# Keeping this class short initially, we should eventually getting it closer
# to the CycloneDX/SPDX standard as we grow the project.
@dataclass
class Metadata:
    """Metadata class to store metadata of a package."""

    name: str | None  # AKA component
    version: str | None  # package version or commit hash
    origin: str | None  # package manager purl or repository url
    local_src_path: str | None  # local path to the source code
    license: list[str]  # SPDX format license
    copyright: list[str]  # Copyright owners
