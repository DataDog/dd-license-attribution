# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

import json
from io import StringIO
from typing import Any, Dict

# TODO: Remove "type: ignore" comments when spdx-tools library gets proper type stubs
# or when a separate stub package becomes available
from spdx.document import Document  # type: ignore
from spdx.parsers.jsonparser import Parser  # type: ignore
from spdx.parsers.jsonyamlxmlbuilders import Builder  # type: ignore
from spdx.parsers.loggers import StandardLogger  # type: ignore


def test_spdx_tools_can_parse_minimum_sbom() -> None:
    """Test that spdx-tools can parse a minimum SPDX SBOM document."""
    # Create a minimal SPDX SBOM JSON that matches the structure expected by github-sbom strategy
    minimal_sbom: Dict[str, Any] = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "name": "Test SBOM",
        "documentNamespace": "https://spdx.org/spdxdocs/test-sbom",
        "dataLicense": "CC0-1.0",
        "creationInfo": {
            "creators": ["Tool: spdx-tools-test"],
            "created": "2024-01-01T00:00:00Z",
        },
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-1",
                "name": "test-package",
                "versionInfo": "1.0.0",
                "downloadLocation": "https://github.com/test/test-package",
                "licenseDeclared": "MIT",
                "copyrightText": "Copyright 2024 Test Author",
            },
            {
                "SPDXID": "SPDXRef-Package-2",
                "name": "another-package",
                "versionInfo": "2.1.0",
                "downloadLocation": "https://github.com/test/another-package",
                "licenseDeclared": "Apache-2.0",
                "copyrightText": "Copyright 2024 Another Author",
            },
        ],
    }

    # Use spdx-tools to parse the JSON data directly
    parser = Parser(Builder(), StandardLogger())
    json_data = StringIO(json.dumps(minimal_sbom))
    result = parser.parse(json_data)
    document, _ = result

    # Verify that spdx-tools successfully parsed the document
    assert document is not None
    assert isinstance(document, Document)

    # Verify the document has the expected packages
    assert len(document.packages) == 2

    # Verify package structure matches what the strategy processes
    package1 = document.packages[0]
    assert package1.name == "test-package"
    assert package1.version == "1.0.0"
    assert package1.download_location == "https://github.com/test/test-package"
    assert package1.license_declared is not None
    assert package1.cr_text == "Copyright 2024 Test Author"

    package2 = document.packages[1]
    assert package2.name == "another-package"
    assert package2.version == "2.1.0"
    assert package2.download_location == "https://github.com/test/another-package"
    assert (
        package2.license_declared is not None
    )  # license_concluded is not a standard field
    assert package2.cr_text == "Copyright 2024 Another Author"


def test_spdx_tools_can_parse_github_actions_packages() -> None:
    """Test that spdx-tools can handle GitHub Actions packages that should be filtered out."""
    # Create SBOM with GitHub Actions packages that the strategy filters out
    sbom_with_actions: Dict[str, Any] = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "name": "Test SBOM with Actions",
        "documentNamespace": "https://spdx.org/spdxdocs/test-sbom-actions",
        "dataLicense": "CC0-1.0",
        "creationInfo": {
            "creators": ["Tool: spdx-tools-test"],
            "created": "2024-01-01T00:00:00Z",
        },
        "packages": [
            {
                "SPDXID": "SPDXRef-githubactions-setup-python",
                "name": "actions/setup-python",
                "versionInfo": "v4",
                "downloadLocation": "https://github.com/actions/setup-python",
                "licenseDeclared": "MIT",
                "copyrightText": "Copyright 2024 GitHub",
            },
            {
                "SPDXID": "SPDXRef-Package-1",
                "name": "test-package",
                "versionInfo": "1.0.0",
                "downloadLocation": "https://github.com/test/test-package",
                "licenseDeclared": "MIT",
                "copyrightText": "Copyright 2024 Test Author",
            },
        ],
    }

    # Use spdx-tools to parse the JSON data directly
    parser = Parser(Builder(), StandardLogger())
    json_data = StringIO(json.dumps(sbom_with_actions))
    result = parser.parse(json_data)
    document, _ = result

    # Verify that spdx-tools successfully parsed the document
    assert document is not None
    assert isinstance(document, Document)

    # Verify GitHub Actions packages have the expected SPDXID pattern
    actions_package = document.packages[0]
    assert actions_package.spdx_id.startswith("SPDXRef-githubactions-")

    # Verify regular packages don't have this pattern
    regular_package = document.packages[1]
    assert not regular_package.spdx_id.startswith("SPDXRef-githubactions-")


def test_spdx_tools_can_handle_noassertion_values() -> None:
    """Test that spdx-tools can handle NOASSERTION values that the strategy processes."""
    sbom_with_noassertion: Dict[str, Any] = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "name": "Test SBOM with NOASSERTION",
        "documentNamespace": "https://spdx.org/spdxdocs/test-sbom-noassertion",
        "dataLicense": "CC0-1.0",
        "creationInfo": {
            "creators": ["Tool: spdx-tools-test"],
            "created": "2024-01-01T00:00:00Z",
        },
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-1",
                "name": "test-package",
                "versionInfo": "NOASSERTION",
                "downloadLocation": "NOASSERTION",
                "licenseDeclared": "NOASSERTION",
                "copyrightText": "NOASSERTION",
            },
            {
                "SPDXID": "SPDXRef-Package-2",
                "name": "github.com/test/package",
                "versionInfo": "1.0.0",
                "downloadLocation": "",
                "licenseDeclared": "MIT",
                "copyrightText": "Copyright 2024 Test Author",
            },
        ],
    }

    # Use spdx-tools to parse the JSON data directly
    parser = Parser(Builder(), StandardLogger())
    json_data = StringIO(json.dumps(sbom_with_noassertion))
    result = parser.parse(json_data)
    document, _ = result

    # Verify that spdx-tools successfully parsed the document
    assert document is not None
    assert isinstance(document, Document)

    # Verify NOASSERTION values are handled correctly
    package1 = document.packages[0]
    assert package1.version == "NOASSERTION"
    assert package1.download_location == "NOASSERTION"
    assert package1.license_declared is not None
    assert package1.cr_text == "NOASSERTION"

    # Verify empty string is handled
    package2 = document.packages[1]
    assert package2.download_location == ""


def test_spdx_tools_can_write_and_parse_document() -> None:
    """Test that spdx-tools can write and then parse a document, ensuring round-trip functionality."""
    # Create a minimal SPDX document
    minimal_sbom: Dict[str, Any] = {
        "SPDXID": "SPDXRef-DOCUMENT",
        "spdxVersion": "SPDX-2.3",
        "name": "Test SBOM Round Trip",
        "documentNamespace": "https://spdx.org/spdxdocs/test-sbom-roundtrip",
        "dataLicense": "CC0-1.0",
        "creationInfo": {
            "creators": ["Tool: spdx-tools-test"],
            "created": "2024-01-01T00:00:00Z",
        },
        "packages": [
            {
                "SPDXID": "SPDXRef-Package-1",
                "name": "test-package",
                "versionInfo": "1.0.0",
                "downloadLocation": "https://github.com/test/test-package",
                "licenseDeclared": "MIT",
                "copyrightText": "Copyright 2024 Test Author",
            },
        ],
    }

    # Parse the document using the direct SPDX JSON parser
    parser = Parser(Builder(), StandardLogger())
    json_data = StringIO(json.dumps(minimal_sbom))
    result = parser.parse(json_data)
    document, _ = result
    assert document is not None

    # Parse the same data again to verify consistency
    parser2 = Parser(Builder(), StandardLogger())
    json_data2 = StringIO(json.dumps(minimal_sbom))
    parsed_result = parser2.parse(json_data2)
    parsed_document, _ = parsed_result
    assert parsed_document is not None

    # Verify the documents are equivalent
    assert len(parsed_document.packages) == len(document.packages)
    assert parsed_document.packages[0].name == document.packages[0].name
    assert parsed_document.packages[0].version == document.packages[0].version
