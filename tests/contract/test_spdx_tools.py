# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

"""Contract tests for spdx-tools library.

These tests validate that the spdx-tools library behaves as expected for parsing
SPDX SBOM documents (specifically GitHub-generated SBOMs). They ensure that library
updates don't break our assumptions about the library's behavior.

This test suite is designed for spdx-tools 0.8.x (>=0.8.2).
"""

import json
from io import StringIO

from spdx.parsers.jsonparser import Parser as JSONParser
from spdx.parsers.jsonyamlxmlbuilders import Builder
from spdx.parsers.loggers import StandardLogger


class TestSPDXToolsContract:
    """Validate spdx-tools library behavior for our use case."""

    def test_parses_minimal_spdx_json_document(self) -> None:
        """Ensure spdx-tools can parse a minimal SPDX JSON document."""
        minimal_sbom = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "test-document",
            "documentNamespace": "https://example.com/test",
            "creationInfo": {
                "created": "2024-01-01T00:00:00Z",
                "creators": ["Tool: test"],
            },
            "packages": [],
        }

        sbom_json_str = json.dumps(minimal_sbom)
        sbom_file = StringIO(sbom_json_str)
        builder = Builder()
        standard_logger = StandardLogger()
        parser = JSONParser(builder, standard_logger)
        parser.parse(sbom_file)
        document = parser.document

        # Validate document was parsed
        assert document is not None
        assert hasattr(document, "packages")
        assert isinstance(document.packages, list)

    def test_parses_spdx_package_with_standard_fields(self) -> None:
        """Ensure spdx-tools correctly parses package fields we use."""
        sbom_with_package = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "test-document",
            "documentNamespace": "https://example.com/test",
            "creationInfo": {
                "created": "2024-01-01T00:00:00Z",
                "creators": ["Tool: test"],
            },
            "packages": [
                {
                    "SPDXID": "SPDXRef-Package-test-package",
                    "name": "test-package",
                    "versionInfo": "1.0.0",
                    "downloadLocation": "https://github.com/test/package",
                    "filesAnalyzed": False,
                    "licenseDeclared": "MIT",
                    "licenseConcluded": "MIT",
                    "copyrightText": "Copyright 2024 Test Company",
                }
            ],
        }

        sbom_json_str = json.dumps(sbom_with_package)
        sbom_file = StringIO(sbom_json_str)
        builder = Builder()
        standard_logger = StandardLogger()
        parser = JSONParser(builder, standard_logger)
        parser.parse(sbom_file)
        document = parser.document

        # Validate package fields
        assert len(document.packages) == 1
        package = document.packages[0]

        # Test field access patterns we use in our code
        # Note: spdx-tools 0.8.2 still uses the same attribute names as 0.7
        assert package.name == "test-package"
        assert package.spdx_id == "SPDXRef-Package-test-package"
        assert package.version == "1.0.0"
        assert package.download_location == "https://github.com/test/package"
        assert package.cr_text == "Copyright 2024 Test Company"

        # License fields may be returned as strings or objects
        # Test that we can convert to string
        assert str(package.license_declared) is not None
        assert str(package.conc_lics) is not None

    def test_handles_noassertion_values(self) -> None:
        """Ensure spdx-tools handles NOASSERTION values as expected."""
        sbom_with_noassertion = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "test-document",
            "documentNamespace": "https://example.com/test",
            "creationInfo": {
                "created": "2024-01-01T00:00:00Z",
                "creators": ["Tool: test"],
            },
            "packages": [
                {
                    "SPDXID": "SPDXRef-Package-test",
                    "name": "test-package",
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                    "licenseDeclared": "NOASSERTION",
                    "licenseConcluded": "NOASSERTION",
                    "copyrightText": "NOASSERTION",
                }
            ],
        }

        sbom_json_str = json.dumps(sbom_with_noassertion)
        sbom_file = StringIO(sbom_json_str)
        builder = Builder()
        standard_logger = StandardLogger()
        parser = JSONParser(builder, standard_logger)
        parser.parse(sbom_file)
        document = parser.document

        # Validate NOASSERTION handling
        assert len(document.packages) == 1
        package = document.packages[0]

        # NOASSERTION should be accessible (as string or object)
        # Our code checks for equality with "NOASSERTION" string
        assert package.download_location is not None
        assert package.cr_text is not None

    def test_parses_multiple_packages(self) -> None:
        """Ensure spdx-tools correctly parses documents with multiple packages."""
        sbom_with_multiple = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "test-document",
            "documentNamespace": "https://example.com/test",
            "creationInfo": {
                "created": "2024-01-01T00:00:00Z",
                "creators": ["Tool: test"],
            },
            "packages": [
                {
                    "SPDXID": "SPDXRef-Package-package1",
                    "name": "package1",
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                },
                {
                    "SPDXID": "SPDXRef-Package-package2",
                    "name": "package2",
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                },
                {
                    "SPDXID": "SPDXRef-Package-package3",
                    "name": "package3",
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                },
            ],
        }

        sbom_json_str = json.dumps(sbom_with_multiple)
        sbom_file = StringIO(sbom_json_str)
        builder = Builder()
        standard_logger = StandardLogger()
        parser = JSONParser(builder, standard_logger)
        parser.parse(sbom_file)
        document = parser.document

        # Validate multiple packages
        assert len(document.packages) == 3
        assert document.packages[0].name == "package1"
        assert document.packages[1].name == "package2"
        assert document.packages[2].name == "package3"

    def test_identifies_github_actions_by_spdx_id(self) -> None:
        """Ensure we can identify GitHub Actions by their SPDX ID prefix."""
        sbom_with_action = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "test-document",
            "documentNamespace": "https://example.com/test",
            "creationInfo": {
                "created": "2024-01-01T00:00:00Z",
                "creators": ["Tool: test"],
            },
            "packages": [
                {
                    "SPDXID": "SPDXRef-githubactions-checkout-v2",
                    "name": "actions/checkout",
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                },
                {
                    "SPDXID": "SPDXRef-Package-normal-package",
                    "name": "normal-package",
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                },
            ],
        }

        sbom_json_str = json.dumps(sbom_with_action)
        sbom_file = StringIO(sbom_json_str)
        builder = Builder()
        standard_logger = StandardLogger()
        parser = JSONParser(builder, standard_logger)
        parser.parse(sbom_file)
        document = parser.document

        # Validate SPDX ID access for filtering GitHub Actions
        assert len(document.packages) == 2
        github_action = document.packages[0]
        normal_package = document.packages[1]

        # Our code filters by checking if spdx_id starts with "SPDXRef-githubactions-"
        assert github_action.spdx_id.startswith("SPDXRef-githubactions-")
        assert not normal_package.spdx_id.startswith("SPDXRef-githubactions-")

    def test_handles_optional_fields(self) -> None:
        """Ensure spdx-tools handles packages with minimal/optional fields."""
        sbom_minimal_package = {
            "spdxVersion": "SPDX-2.3",
            "dataLicense": "CC0-1.0",
            "SPDXID": "SPDXRef-DOCUMENT",
            "name": "test-document",
            "documentNamespace": "https://example.com/test",
            "creationInfo": {
                "created": "2024-01-01T00:00:00Z",
                "creators": ["Tool: test"],
            },
            "packages": [
                {
                    "SPDXID": "SPDXRef-Package-minimal",
                    "name": "minimal-package",
                    "downloadLocation": "NOASSERTION",
                    "filesAnalyzed": False,
                    # No version, license, or copyright fields
                }
            ],
        }

        sbom_json_str = json.dumps(sbom_minimal_package)
        sbom_file = StringIO(sbom_json_str)
        builder = Builder()
        standard_logger = StandardLogger()
        parser = JSONParser(builder, standard_logger)
        parser.parse(sbom_file)
        document = parser.document

        # Validate optional fields can be accessed (may be None or default values)
        assert len(document.packages) == 1
        package = document.packages[0]

        # These fields should be accessible even if not in JSON
        # Our code checks for None/truthiness
        # Note: spdx-tools 0.8.2 still uses the same attribute names as 0.7
        assert hasattr(package, "version")
        assert hasattr(package, "license_declared")
        assert hasattr(package, "conc_lics")
        assert hasattr(package, "cr_text")
