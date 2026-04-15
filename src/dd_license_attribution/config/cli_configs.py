# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

from dataclasses import dataclass


@dataclass
class Config:
    preset_license_file_locations: list[str]
    preset_copyright_file_locations: list[str]
    preset_cautionary_licenses: list[str]
    recognized_licenses: frozenset[str]


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
        # Some licenses include the copyright in their license file
        "LICENSE",
        "LICENSE.code",
        "LICENSE.txt",
        "LICENSE.md",
        "COPYING",
        "LICENCE",  # I know it is misspelled, but it is common in the wild
        "LICENCE.md",  # I know it is misspelled, but it is common in the wild
        "license/LICENSE.txt",
    ],
    preset_cautionary_licenses=[
        "GPL",
        "EUPL",
        "AGPL",
    ],
    # OSI-approved SPDX license identifiers, fetched from https://spdx.org/licenses/ on 2026-04-15
    recognized_licenses=frozenset(
        {
            "0BSD",
            "AAL",
            "AFL-1.1",
            "AFL-1.2",
            "AFL-2.0",
            "AFL-2.1",
            "AFL-3.0",
            "AGPL-3.0",  # deprecated alias for AGPL-3.0-only
            "AGPL-3.0-only",
            "AGPL-3.0-or-later",
            "Apache-1.1",
            "Apache-2.0",
            "APSL-2.0",
            "Artistic-1.0",
            "Artistic-1.0-cl8",
            "Artistic-1.0-Perl",
            "Artistic-2.0",
            "BSD-1-Clause",
            "BSD-2-Clause",
            "BSD-2-Clause-Patent",
            "BSD-3-Clause",
            "BSL-1.0",
            "CAL-1.0",
            "CAL-1.0-Combined-Work-Exception",
            "CATOSL-1.1",
            "CDDL-1.0",
            "CECILL-2.1",
            "CERN-OHL-P-2.0",
            "CERN-OHL-S-2.0",
            "CERN-OHL-W-2.0",
            "CNRI-Python",
            "CPAL-1.0",
            "CPL-1.0",
            "CUA-OPL-1.0",
            "ECL-1.0",
            "ECL-2.0",
            "EFL-2.0",
            "Entessa",
            "EPL-1.0",
            "EPL-2.0",
            "EUDatagrid",
            "EUPL-1.1",
            "EUPL-1.2",
            "Fair",
            "Frameworx-1.0",
            "GPL-2.0",  # deprecated alias for GPL-2.0-only
            "GPL-2.0-only",
            "GPL-2.0-or-later",
            "GPL-3.0",  # deprecated alias for GPL-3.0-only
            "GPL-3.0-only",
            "GPL-3.0-or-later",
            "HPND",
            "IBM-pibs",
            "Intel",
            "IPA",
            "IPL-1.0",
            "ISC",
            "LGPL-2.0",  # deprecated alias for LGPL-2.0-only
            "LGPL-2.0-only",
            "LGPL-2.0-or-later",
            "LGPL-2.1",  # deprecated alias for LGPL-2.1-only
            "LGPL-2.1-only",
            "LGPL-2.1-or-later",
            "LGPL-3.0",  # deprecated alias for LGPL-3.0-only
            "LGPL-3.0-only",
            "LGPL-3.0-or-later",
            "LPL-1.0",
            "LPL-1.02",
            "LPPL-1.3c",
            "MirOS",
            "MIT",
            "MIT-0",
            "Motosoto",
            "MPL-1.0",
            "MPL-1.1",
            "MPL-2.0",
            "MPL-2.0-no-copyleft-exception",
            "MS-PL",
            "MS-RL",
            "MulanPSL-2.0",
            "Multics",
            "NASA-1.3",
            "NCSA",
            "Nokia",
            "NPOSL-3.0",
            "NTP",
            "OCLC-2.0",
            "OFL-1.0",
            "OFL-1.0-no-RFN",
            "OFL-1.0-RFN",
            "OFL-1.1",
            "OFL-1.1-no-RFN",
            "OFL-1.1-RFN",
            "OGTSL",
            "OSL-1.0",
            "OSL-1.1",
            "OSL-2.0",
            "OSL-2.1",
            "OSL-3.0",
            "PHP-3.0",
            "PHP-3.01",
            "PostgreSQL",
            "PSF-2.0",
            "Python-2.0",
            "QPL-1.0",
            "QPL-1.0-INRIA-2004",
            "RPL-1.1",
            "RPL-1.5",
            "RPSL-1.0",
            "RSCPL",
            "SimPL-2.0",
            "SISSL",
            "Sleepycat",
            "SPL-1.0",
            "SugarCRM-1.1.3",
            "UPL-1.0",
            "VSL-1.0",
            "W3C",
            "Watcom-1.0",
            "Xnet",
            "ZPL-2.0",
            "ZPL-2.1",
            "Zlib",
        }
    ),
)
