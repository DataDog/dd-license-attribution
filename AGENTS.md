# AI Agent Guidelines for dd-license-attribution

This document provides comprehensive guidelines for AI agents working on the dd-license-attribution codebase. These rules ensure code quality, maintainability, and consistency across all contributions.

## 🚨 Critical Requirements

All code changes must comply with these non-negotiable requirements:

- **100% typing coverage** validated by MyPy
- **95%+ unit test coverage** for all business logic
- **OS operations through adaptors only** (no direct imports)
- **Formatted with isort and black**
- **CHANGELOG.md updates** for user-facing changes
- **SPDX-License-Identifier header** in all source files

## 📄 File Headers and Licensing

### Required File Header Format

**MANDATORY**: Every Python source file (`.py`) and test file must include the following header at the very top:

```python
# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.
```

### Header Components

1. **SPDX-License-Identifier** (Line 1):
   - REQUIRED on the first line of every source file
   - Format: `# SPDX-License-Identifier: Apache-2.0`
   - Enables automated license scanning and compliance
   - Follows [SPDX specification](https://spdx.dev/)

2. **License Statement** (After blank line):
   - Standard Datadog Apache 2.0 license statement
   - Must include full text as shown above

3. **Copyright Notice**:
   - Company: Datadog (https://www.datadoghq.com/)
   - Year: `YYYY-present` where YYYY is the year the file was first created (e.g., `2025-present` for files created in 2025)

### When to Include Headers

**REQUIRED in**:
- ✅ All Python source files in `src/`
- ✅ All test files in `tests/`
- ✅ All Python scripts

**NOT REQUIRED in**:
- ❌ `__init__.py` files that are empty or near-empty
- ❌ Configuration files (`.toml`, `.yaml`, `.json`)
- ❌ Documentation files (`.md`, `.txt`)

### Examples

```python
# ✅ CORRECT: Complete header with SPDX identifier
# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import logging
from typing import Any
# ... rest of file ...

# ❌ FORBIDDEN: Missing SPDX-License-Identifier
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

import logging
# ... rest of file ...

# ❌ FORBIDDEN: SPDX identifier not on first line
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
# SPDX-License-Identifier: Apache-2.0
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.
```

## 📋 Pre-Commit Validation Checklist

Before suggesting any code changes, verify:

- [ ] `mypy src/ tests/` passes with no errors
- [ ] All functions have complete type annotations
- [ ] No direct OS imports in `src/` code (use adaptors)
- [ ] `pytest --cov=src/dd_license_attribution --cov-fail-under=95` passes
- [ ] New code has corresponding unit tests with proper mocking
- [ ] Unit tests mock all external dependencies (adaptors, network calls, etc.)
- [ ] All mocks are verified with assertions (call count AND parameters)
- [ ] No unit tests make real filesystem, network, or database calls
- [ ] Tests focus on public interfaces, not internal implementation details
- [ ] `isort --check-only src/ tests/` and `black --check src/ tests/` pass
- [ ] No unused imports remain in the code
- [ ] CHANGELOG.md updated for ALL user-facing changes
- [ ] Modern Python 3.11+ syntax used for type hints (e.g., `list[str]` not `List[str]`)
- [ ] Logging follows consistent format and patterns
- [ ] Contract tests added for any new external library dependencies
- [ ] All Python files include SPDX-License-Identifier header on first line

## 🔧 Type Safety Requirements

### Mandatory Type Annotations

All code must have complete type annotations:

```python
# ✅ REQUIRED: Complete type annotations with modern syntax
from typing import Any

def process_data(data: list[str], config: dict[str, Any]) -> ProcessedResult | None:
    result: str | None = None
    items: list[dict[str, Any]] = []
    return ProcessedResult(result, items)

# ❌ FORBIDDEN: Missing type annotations
def process_data(data, config):
    result = None
    return result
```

### Modern Python 3.11+ Type Syntax

**REQUIRED**: Use modern built-in generics (PEP 585) instead of importing from `typing`:

```python
# ✅ REQUIRED: Python 3.11+ modern syntax
def process_data(data: list[str], config: dict[str, any]) -> str | None:
    items: list[dict[str, any]] = []
    result: str | None = None
    mapping: dict[str, list[int]] = {}
    return result

# ❌ FORBIDDEN: Old-style typing imports (Python 3.9 syntax)
from typing import Dict, List, Optional
def process_data(data: List[str], config: Dict[str, Any]) -> Optional[str]:
    return None
```

**Import from `typing` only when necessary**:
```python
from typing import Any, Protocol, TypeAlias, Literal, TypeVar, Generic

# Use for protocols, type aliases, literals, and advanced features
class Handler(Protocol):
    def handle(self, data: str) -> bool: ...

ConfigType: TypeAlias = dict[str, str | int | bool]
Mode = Literal["read", "write", "append"]
```

### Class and Method Typing

```python
# ✅ REQUIRED: Typed class with all methods annotated (modern syntax)
from typing import Any

class DataProcessor:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config: dict[str, Any] = config
        self.cache: dict[str, Any] = {}
    
    def process(self, data: str) -> str | None:
        return data.upper() if data else None
    
    @classmethod
    def from_config(cls, config_path: str) -> "DataProcessor":
        return cls({})
    
    @staticmethod
    def validate_input(data: str) -> bool:
        return len(data) > 0
```

### Protocol Classes for Interfaces

```python
# ✅ REQUIRED: Use Protocol for structural typing
from typing import Protocol

class DataHandler(Protocol):
    def process(self, data: str) -> str: ...
    def validate(self, data: str) -> bool: ...

def use_handler(handler: DataHandler) -> str:
    if handler.validate("test"):
        return handler.process("test")
    return "invalid"
```

## 🔌 OS Operations Through Adaptors

### FORBIDDEN Direct OS Imports

Never import these modules directly in `src/` code:

```python
# ❌ FORBIDDEN in src/ code
import os
import sys
import subprocess
import pathlib
import shutil
import tempfile
```

### CLI and Infrastructure Exceptions

**The following are EXCEPTIONS to the OS import rules** and are permitted in specific contexts:

1. **CLI Output (`print()` for STDOUT)**:
   - ✅ **ALLOWED** in CLI command functions for final output intended for piping/redirection
   - ✅ Example: `print(csv_output, end="")` in `generate_sbom_csv_command.py`
   - ❌ **NOT ALLOWED** for debug messages or progress updates (use logging instead)
   - 💡 **Best Practice**: Add a comment to clarify intentional STDOUT usage

2. **CLI Error Handling (`sys.exit()`)**:
   - ✅ **ALLOWED** in CLI command functions to exit with error codes
   - ✅ Example: `sys.exit(1)` after logging errors in CLI commands
   - ❌ **NOT ALLOWED** in business logic or library code (raise exceptions instead)
   - 💡 **Preferred Alternative**: Raise custom exceptions and handle at CLI boundary

3. **Logging Infrastructure (`sys.stderr`)**:
   - ✅ **ALLOWED** in `utils/logging.py` for configuring log output destinations
   - ✅ Example: `logging.StreamHandler(sys.stderr)` for stderr output
   - ❌ **NOT ALLOWED** for direct writing to stderr (use logging instead)

**Summary of Exceptions**:
```python
# ✅ ALLOWED: CLI output to STDOUT
def generate_sbom_csv(...) -> None:
    # ... business logic ...
    # Output CSV to STDOUT for piping (e.g., command | grep "MIT")
    print(csv_output, end="")

# ✅ ALLOWED: CLI error handling
def generate_sbom_csv(...) -> None:
    try:
        # ... logic ...
    except SomeError as e:
        logger.error(str(e))
        sys.exit(1)  # Exit with error code for shell scripts

# ✅ ALLOWED: Logging infrastructure setup
def setup_logging(level: int) -> None:
    console_handler = logging.StreamHandler(sys.stderr)
    # ... configure logging ...
```

### REQUIRED Adaptor Usage

```python
# ✅ REQUIRED: Use adaptors for OS operations
from dd_license_attribution.adaptors.os import OSAdaptor

class FileProcessor:
    def __init__(self, os_adaptor: OSAdaptor) -> None:
        self.os_adaptor = os_adaptor
    
    def process_file(self, path: str) -> str:
        if self.os_adaptor.path_exists(path):
            return self.os_adaptor.read_file(path)
        return ""
```

### Creating New Adaptors

When OS functionality is needed that doesn't exist:

```python
# ✅ REQUIRED: Create new adaptor with Protocol (imports at top)
from typing import Protocol

import requests

class NetworkAdaptor(Protocol):
    def make_request(self, url: str) -> str: ...

class RealNetworkAdaptor:
    def make_request(self, url: str) -> str:
        return requests.get(url).text

class MockNetworkAdaptor:
    def make_request(self, url: str) -> str:
        return "mocked_response"
```

## 🧪 Testing Requirements

### Coverage Targets

- **Core business logic**: 100% line coverage, 90% branch coverage
- **CLI interfaces**: 100% line coverage, 85% branch coverage
- **Adaptors**: Not unit tested (simple wrappers)
- **Configuration**: Integration tested only

### Test Structure Template

```python
# tests/unit/test_example.py
import pytest
from unittest.mock import Mock, patch
from dd_license_attribution.example import ExampleClass

class TestExampleClass:
    def setup_method(self) -> None:
        """Setup test fixtures."""
        self.os_adaptor = Mock()
        self.example = ExampleClass(self.os_adaptor)
    
    def test_success_case_returns_expected_result(self) -> None:
        """Test normal operation with valid input."""
        self.os_adaptor.read_file.return_value = "test content"
        result = self.example.process_file("test.txt")
        assert result == "processed: test content"
    
    def test_error_handling_raises_appropriate_exception(self) -> None:
        """Test error scenarios are handled correctly."""
        self.os_adaptor.read_file.side_effect = FileNotFoundError()
        with pytest.raises(FileNotFoundError):
            self.example.process_file("nonexistent.txt")
    
    def test_edge_cases_handle_boundary_conditions(self) -> None:
        """Test boundary conditions and edge cases."""
        self.os_adaptor.read_file.return_value = ""
        result = self.example.process_file("empty.txt")
        assert result == "processed: "
```

### Proper Mocking Practices

**CRITICAL**: Unit tests must remain unit tests. Mock all external dependencies to prevent tests from becoming integration tests.

**MANDATORY MOCK VERIFICATION**: Every mock used in a test MUST be verified with assertions. This is non-negotiable.

- ✅ **REQUIRED**: Verify call count (e.g., `assert_called_once()`, `assert_called()`, `assert_not_called()`)
- ✅ **REQUIRED**: Verify parameters passed (e.g., `assert_called_once_with(...)`, `assert_called_with(...)`)
- ✅ **REQUIRED**: Verify call order when relevant (e.g., `assert_has_calls(...)`)

**Why this matters:**
- Ensures the code under test actually uses the mocked dependencies
- Verifies the correct parameters are passed to external dependencies
- Catches regressions when refactoring
- Documents expected behavior through assertions

#### What to Mock

```python
# ✅ REQUIRED: Mock all external dependencies
from unittest.mock import Mock, patch

class TestDataProcessor:
    def setup_method(self) -> None:
        """Setup test fixtures with mocked dependencies."""
        # Mock adaptors (external dependencies)
        self.os_adaptor = Mock()
        self.network_adaptor = Mock()
        
        # Inject mocks into class under test
        self.processor = DataProcessor(
            os_adaptor=self.os_adaptor,
            network_adaptor=self.network_adaptor
        )
    
    def test_process_file_with_mocked_dependencies(self) -> None:
        """Test business logic with all external calls mocked."""
        # Arrange: Set up mock behavior
        self.os_adaptor.read_file.return_value = "test content"
        self.network_adaptor.fetch_metadata.return_value = {"version": "1.0"}
        
        # Act: Call the method under test
        result = self.processor.process_file("test.txt")
        
        # Assert: Verify behavior and mock calls
        assert result.content == "processed: test content"
        assert result.metadata["version"] == "1.0"
        
        # CRITICAL: ALWAYS verify mocks were called correctly
        self.os_adaptor.read_file.assert_called_once_with("test.txt")
        self.network_adaptor.fetch_metadata.assert_called_once()
```

#### What NOT to Mock

```python
# ❌ FORBIDDEN: Don't mock internal methods
@patch('dd_license_attribution.processor.DataProcessor._internal_helper')
def test_with_internal_mock(self, mock_helper):
    # This makes the test brittle and tests implementation details
    pass

# ❌ FORBIDDEN: Don't mock the class under test
@patch('dd_license_attribution.processor.DataProcessor.process_file')
def test_mocked_method_under_test(self, mock_process):
    # This doesn't test anything meaningful
    pass

# ❌ FORBIDDEN: Don't mock built-in Python functions unless absolutely necessary
@patch('builtins.len')
def test_with_mocked_builtin(self, mock_len):
    # Usually indicates poor test design
    pass
```

#### Dependency Injection for Testability

```python
# ✅ REQUIRED: Design classes for easy mocking via dependency injection
class DataProcessor:
    def __init__(
        self, 
        os_adaptor: OSAdaptor,
        network_adaptor: NetworkAdaptor,
        config: Dict[str, Any]
    ) -> None:
        self.os_adaptor = os_adaptor
        self.network_adaptor = network_adaptor
        self.config = config
    
    def process_file(self, path: str) -> ProcessedResult:
        # Business logic that can be tested in isolation
        if not self.os_adaptor.path_exists(path):
            raise FileNotFoundError(f"File not found: {path}")
        
        content = self.os_adaptor.read_file(path)
        metadata = self.network_adaptor.fetch_metadata(path)
        
        return ProcessedResult(
            content=f"processed: {content}",
            metadata=metadata
        )

# ✅ Easy to test with mocks
class TestDataProcessor:
    def test_file_not_found_raises_exception(self) -> None:
        os_adaptor = Mock()
        network_adaptor = Mock()
        os_adaptor.path_exists.return_value = False
        
        processor = DataProcessor(os_adaptor, network_adaptor, {})
        
        with pytest.raises(FileNotFoundError, match="File not found: test.txt"):
            processor.process_file("test.txt")
        
        # CRITICAL: ALWAYS verify mock interactions
        os_adaptor.path_exists.assert_called_once_with("test.txt")
        os_adaptor.read_file.assert_not_called()
        network_adaptor.fetch_metadata.assert_not_called()
```

#### Advanced Mocking Patterns

```python
# ✅ Mock side effects for error testing
def test_handles_network_timeout(self) -> None:
    self.network_adaptor.fetch_metadata.side_effect = TimeoutError("Network timeout")
    
    with pytest.raises(TimeoutError):
        self.processor.process_file("test.txt")

# ✅ Mock return values for different scenarios
def test_handles_different_file_types(self) -> None:
    test_cases = [
        ("file.txt", "text content", "text/plain"),
        ("file.json", '{"key": "value"}', "application/json"),
        ("file.py", "print('hello')", "text/x-python"),
    ]
    
    for filename, content, expected_type in test_cases:
        with self.subTest(filename=filename):
            self.os_adaptor.read_file.return_value = content
            result = self.processor.detect_file_type(filename)
            assert result == expected_type

# ✅ Verify call arguments and call counts
from unittest.mock import call

def test_calls_adaptor_with_correct_arguments(self) -> None:
    self.processor.process_multiple_files(["file1.txt", "file2.txt"])
    
    # Verify exact calls
    expected_calls = [call("file1.txt"), call("file2.txt")]
    self.os_adaptor.read_file.assert_has_calls(expected_calls)
    assert self.os_adaptor.read_file.call_count == 2
```

#### Mock Configuration Best Practices

```python
# ✅ Use descriptive mock names and return values
def test_processes_license_file_correctly(self) -> None:
    license_content = "MIT License\nCopyright (c) 2024"
    expected_result = LicenseInfo(type="MIT", year="2024")
    
    self.os_adaptor.read_file.return_value = license_content
    
    result = self.processor.parse_license("LICENSE")
    
    # Verify result
    assert result == expected_result
    
    # CRITICAL: ALWAYS verify mock was called with correct parameters
    self.os_adaptor.read_file.assert_called_once_with("LICENSE")

# ✅ Reset mocks between tests if needed
def teardown_method(self) -> None:
    """Clean up after each test."""
    self.os_adaptor.reset_mock()
    self.network_adaptor.reset_mock()
```

#### Mock Verification Requirements

**MANDATORY for every test that uses mocks:**

```python
# ✅ REQUIRED: Complete mock verification
def test_with_complete_verification(self) -> None:
    # Arrange
    self.os_adaptor.read_file.return_value = "content"
    self.os_adaptor.path_exists.return_value = True
    
    # Act
    result = self.processor.process_file("test.txt")
    
    # Assert - Verify result
    assert result == "processed: content"
    
    # Assert - MANDATORY: Verify ALL mock interactions
    self.os_adaptor.path_exists.assert_called_once_with("test.txt")
    self.os_adaptor.read_file.assert_called_once_with("test.txt")

# ❌ FORBIDDEN: Missing mock verification
def test_without_verification(self) -> None:
    # Arrange
    self.os_adaptor.read_file.return_value = "content"
    
    # Act
    result = self.processor.process_file("test.txt")
    
    # Assert - Only checks result, DOES NOT verify mock was called
    assert result == "processed: content"
    # MISSING: self.os_adaptor.read_file.assert_called_once_with("test.txt")

# ✅ REQUIRED: Verify call count for methods called multiple times
def test_multiple_calls_verification(self) -> None:
    # Arrange
    self.os_adaptor.read_file.return_value = "content"
    
    # Act
    self.processor.process_multiple_files(["file1.txt", "file2.txt", "file3.txt"])
    
    # Assert - Verify exact call count
    assert self.os_adaptor.read_file.call_count == 3
    
    # Assert - Verify exact calls with parameters
    expected_calls = [
        call("file1.txt"),
        call("file2.txt"),
        call("file3.txt")
    ]
    self.os_adaptor.read_file.assert_has_calls(expected_calls)

# ✅ REQUIRED: Verify mocks were NOT called when appropriate
def test_early_return_no_calls(self) -> None:
    # Arrange
    self.os_adaptor.path_exists.return_value = False
    
    # Act
    result = self.processor.process_file_if_exists("test.txt")
    
    # Assert - Verify result
    assert result is None
    
    # Assert - MANDATORY: Verify what WAS and WAS NOT called
    self.os_adaptor.path_exists.assert_called_once_with("test.txt")
    self.os_adaptor.read_file.assert_not_called()  # Should not be called
```

### Contract Tests for External Libraries

**REQUIRED**: When introducing any new external library dependency, create corresponding contract tests to validate the library's behavior remains stable across updates.

**Purpose**: Contract tests are NOT about testing the library's functionality—they test the **stability** of the specific features we use. They ensure that after a library update, the assumptions our code made about that library haven't changed.

#### When to Create Contract Tests

Create contract tests when adding dependencies for:
- **External APIs** (GitHub API, PyPI, npm registry, etc.)
- **Third-party libraries with complex behavior** (parsing libraries, network libraries, etc.)
- **System command-line tools** (git, npm, pip, etc.)
- **Data format parsers** (YAML, TOML, JSON schema validators, etc.)

**Important**: Only test the specific features and behaviors that our codebase actually uses from the external library.

#### Contract Test Structure

```python
# tests/contract/test_github_api.py
"""Contract tests for GitHub API to ensure API structure matches expectations."""
import pytest

class TestGitHubAPIContract:
    """Validate GitHub API endpoint contracts."""
    
    def test_repository_endpoint_structure(self) -> None:
        """Ensure GitHub API returns expected repository structure."""
        response = github_api.get_repository("owner/repo")
        
        # Validate required fields exist
        assert "name" in response
        assert "full_name" in response
        assert "html_url" in response
        assert "default_branch" in response
        
        # Validate field types
        assert isinstance(response["name"], str)
        assert isinstance(response["full_name"], str)
        assert isinstance(response["html_url"], str)
    
    def test_api_error_responses(self) -> None:
        """Ensure API error responses have expected structure."""
        with pytest.raises(Exception) as exc_info:
            github_api.get_repository("nonexistent/repo")
        
        # Validate error structure
        assert hasattr(exc_info.value, "status_code")
        assert exc_info.value.status_code == 404

# tests/contract/test_giturlparse.py
"""Contract tests for giturlparse library."""

class TestGitURLParseContract:
    """Validate giturlparse library behavior."""
    
    def test_parses_https_github_urls(self) -> None:
        """Ensure giturlparse handles HTTPS GitHub URLs correctly."""
        parsed = giturlparse.parse("https://github.com/owner/repo.git")
        assert parsed.owner == "owner"
        assert parsed.repo == "repo"
        assert parsed.platform == "github"
    
    def test_parses_ssh_github_urls(self) -> None:
        """Ensure giturlparse handles SSH GitHub URLs correctly."""
        parsed = giturlparse.parse("git@github.com:owner/repo.git")
        assert parsed.owner == "owner"
        assert parsed.repo == "repo"
```

#### Contract Test Best Practices

1. **Place in `tests/contract/` directory**: Keep contract tests separate from unit tests
2. **Test actual library behavior**: Don't mock the external library in contract tests
3. **Test only what we use**: Only validate the specific features and behaviors our code depends on
4. **Document expectations**: Clearly document what behavior you're validating and why we depend on it
5. **Version-specific tests**: Note which library version you're testing against
6. **Detect breaking changes**: These tests should fail if a library update breaks our assumptions
7. **Run less frequently**: Contract tests can be slower; mark with `@pytest.mark.contract` if needed

**Example Rationale**: If we use `giturlparse` to extract owner and repo from URLs, we only test that specific parsing behavior—not every feature the library offers.

## 🎨 Code Formatting and Import Management

### Automatic Formatting Commands

```bash
# REQUIRED: Format all code before committing
isort src/ tests/ && black src/ tests/

# Validation commands
isort --check-only src/ tests/
black --check src/ tests/
```

### Unused Imports Detection

**CRITICAL**: Always verify there are no unused imports before committing code.

```bash
# Use autoflake to detect unused imports
autoflake --check --remove-all-unused-imports src/ tests/

# Or use your IDE's built-in detection
# PyCharm: Code -> Optimize Imports
# VSCode: Organize Imports command
```

#### Common Unused Import Scenarios

```python
# ❌ FORBIDDEN: Unused imports left in code
from typing import Dict, List, Optional  # Optional not used
import os  # Not used (and should use adaptor anyway!)
from dd_license_attribution.utils import helper  # Not used

def process(data: list[str]) -> dict[str, str]:
    return {}

# ✅ REQUIRED: Only import what you use
from typing import Any

def process(data: list[str]) -> dict[str, Any]:
    return {}
```

#### Import Organization with isort

**CRITICAL**: All imports must be at the top of the file. Never import inside functions, methods, or classes.

Follow isort conventions strictly:
1. **Standard library imports** (built-in Python modules)
2. **Third-party imports** (installed packages)
3. **Local application imports** (your project modules)

```python
# ✅ CORRECT: Properly organized imports at top of file
import json
import sys
from pathlib import Path

import requests
from github import Github

from dd_license_attribution.adaptors.os import OSAdaptor
from dd_license_attribution.metadata import Metadata

# ❌ FORBIDDEN: Imports inside functions or classes
class DataProcessor:
    def process(self, data: str) -> str:
        import json  # NEVER do this
        return json.dumps(data)

def helper() -> None:
    from typing import Any  # NEVER do this
    pass
```

**Why imports at the top?**
- Makes dependencies immediately visible
- Easier to identify unused imports
- Follows Python conventions (PEP 8)
- Helps with circular dependency detection

### IDE Configuration

Configure your IDE to auto-format on save:
- Enable isort and black formatting
- Set line length to 88 (black default)
- Configure import sorting according to isort rules
- Enable unused import detection and highlighting

## 📝 CHANGELOG Maintenance

**CRITICAL REQUIREMENT**: Always update CHANGELOG.md when making user-visible changes. This is non-negotiable.

### What to Document

**MUST Include in CHANGELOG:**
- ✅ New features visible to users
- ✅ Bug fixes that affect user experience  
- ✅ Breaking changes (API changes, CLI changes, behavior changes)
- ✅ Deprecated functionality
- ✅ New CLI commands or options
- ✅ Changes to output format
- ✅ New configuration options

**EXCLUDE from CHANGELOG:**
- ❌ Internal refactoring
- ❌ Test improvements
- ❌ Code style changes
- ❌ Internal documentation updates (README updates may be included)
- ❌ Changes to development tools or CI/CD

### When in Doubt

Ask yourself: "Would a user of this tool notice or care about this change?"
- **YES** → Update CHANGELOG.md
- **NO** → Skip CHANGELOG.md

### CHANGELOG Format

```markdown
## [Unreleased]

### Added
- New feature for license attribution (#456)
- Support for GitHub Enterprise repositories
- New `--output-format` CLI option for JSON output

### Changed
- License detection now includes SPDX identifiers

### Fixed
- Bug in license detection for multi-license packages (#123)
- Memory leak when processing large repositories (#456)
- Incorrect copyright year extraction from LICENSE files

### Deprecated
- `--legacy-format` option will be removed in v2.0.0

### Security
- Updated vulnerable dependencies (requests 2.28.0 → 2.31.0, CVE-2023-XXXXX)
```

### Pre-Commit CHANGELOG Checklist

Before submitting any change:
- [ ] Read through your changes
- [ ] Identify any user-facing impacts
- [ ] Update CHANGELOG.md under `## [Unreleased]`
- [ ] Use appropriate section (Added/Changed/Fixed/Deprecated/Security)
- [ ] Include issue/PR reference numbers if applicable
- [ ] Write from user's perspective, not developer's

## 📊 Logging Standards

### Consistent Logging Format

**REQUIRED**: Use consistent logging patterns throughout the codebase.

#### Logging Setup

```python
# ✅ REQUIRED: Standard logging setup in each module
import logging
from typing import Any

logger = logging.getLogger(__name__)

class DataProcessor:
    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        logger.debug("DataProcessor initialized with config: %s", config)
```

#### Logging Levels Usage

Use logging levels consistently:

```python
# ✅ REQUIRED: Appropriate logging levels
import logging

logger = logging.getLogger(__name__)

def process_file(path: str) -> str | None:
    logger.debug("Processing file: %s", path)  # Detailed diagnostic info
    
    try:
        content = read_file(path)
        logger.info("Successfully processed file: %s", path)  # Important events
        return content
    except FileNotFoundError:
        logger.warning("File not found: %s", path)  # Unexpected but recoverable
        return None
    except PermissionError:
        logger.error("Permission denied reading file: %s", path)  # Error conditions
        raise
    except Exception as e:
        logger.critical("Critical failure processing file: %s - %s", path, e)  # System failure
        raise
```

#### Logging Level Guidelines

- **DEBUG**: Detailed diagnostic information for development and debugging
  - Variable values, function entry/exit, iteration details
  - Example: `logger.debug("Retrieved %d items from cache", len(items))`

- **INFO**: General informational messages about program execution
  - Successful operations, milestones reached, configuration loaded
  - Example: `logger.info("Started processing repository: %s", repo_name)`

- **WARNING**: Unexpected situations that don't prevent operation
  - Missing optional configuration, deprecated features used, fallback behavior
  - Example: `logger.warning("Config file not found, using defaults")`

- **ERROR**: Error conditions that prevent specific operations
  - Failed API calls, file read errors, invalid input
  - Example: `logger.error("Failed to fetch metadata for package: %s", package_name)`

- **CRITICAL**: Severe errors that may cause program termination
  - Database corruption, unrecoverable system failures
  - Example: `logger.critical("Unable to access required system resources")`

#### Logging Format Best Practices

```python
# ✅ REQUIRED: Use lazy formatting (% style) for better performance
logger.info("Processing %d files from %s", file_count, directory)

# ❌ FORBIDDEN: String concatenation or f-strings in log calls
logger.info(f"Processing {file_count} files from {directory}")  # Evaluated even if not logged
logger.info("Processing " + str(file_count) + " files")  # Inefficient

# ✅ REQUIRED: Include context in log messages
logger.error("Failed to parse license file: %s - %s", filename, error_msg)

# ❌ FORBIDDEN: Vague log messages without context
logger.error("Parse failed")

# ✅ REQUIRED: Log exceptions with exc_info for stack traces
try:
    risky_operation()
except Exception as e:
    logger.error("Operation failed: %s", e, exc_info=True)

# ✅ ALTERNATIVE: Use exception() for automatic stack trace
try:
    risky_operation()
except Exception as e:
    logger.exception("Operation failed: %s", e)
```

#### Structured Logging with Context

```python
# ✅ REQUIRED: Add context to loggers for better tracing
import logging
from typing import Any

logger = logging.getLogger(__name__)

class MetadataCollector:
    def __init__(self, repository: str) -> None:
        self.repository = repository
        self.logger = logging.LoggerAdapter(logger, {"repository": repository})
    
    def collect(self) -> dict[str, Any]:
        self.logger.info("Starting metadata collection")  # Includes repository context
        # ... collection logic ...
        self.logger.info("Completed metadata collection")
        return {}
```

#### Logging Anti-Patterns to Avoid

```python
# ❌ FORBIDDEN: Logging in loops without rate limiting
for item in large_list:
    logger.info("Processing item: %s", item)  # Will flood logs

# ✅ CORRECT: Log summary or use appropriate level
logger.debug("Processing %d items", len(large_list))
for item in large_list:
    logger.debug("Processing item: %s", item)  # DEBUG level for details
logger.info("Completed processing %d items", len(large_list))

# ❌ FORBIDDEN: Logging sensitive information
logger.info("User authenticated with password: %s", password)
logger.info("API key: %s", api_key)

# ✅ CORRECT: Log without sensitive data
logger.info("User authenticated successfully: %s", username)
logger.info("API key configured: %s", "***" if api_key else "not set")

# ❌ FORBIDDEN: Print statements instead of logging
print("Processing file...")  # Not configurable, no levels

# ✅ CORRECT: Use appropriate logging
logger.info("Processing file: %s", filename)
```

## 🚀 Development Workflow

### Development Environment

**CRITICAL**: This project uses **pipenv** exclusively for dependency management and development environment setup.

```bash
# Install dependencies
pipenv install --dev

# Activate virtual environment
pipenv shell

# Run commands in pipenv environment
pipenv run pytest
pipenv run mypy src/ tests/
pipenv run black src/ tests/
pipenv run isort src/ tests/

# Add new dependencies
pipenv install package-name
pipenv install --dev package-name  # For development dependencies
```

**NEVER use:**
- ❌ `pip install` directly
- ❌ `venv` or `virtualenv` manually
- ❌ `poetry` or other package managers
- ❌ `conda` environments

**ALWAYS use:**
- ✅ `pipenv install` for dependencies
- ✅ `pipenv run` for commands
- ✅ `pipenv shell` for interactive development

### For New Features

1. **Plan**: Break down complex features into smaller, testable components
2. **Type**: Write fully typed interfaces and classes with modern Python 3.11+ syntax
3. **Adapt**: Use adaptors for any OS operations
4. **Test**: Write comprehensive unit tests (95%+ coverage)
5. **Contract**: Add contract tests for any new external library dependencies
6. **Format**: Run isort and black, remove unused imports
7. **Log**: Add appropriate logging with consistent format
8. **Validate**: Run MyPy and pytest
9. **Document**: Update CHANGELOG.md (REQUIRED for user-facing changes)

### For Bug Fixes

1. **Reproduce**: Write a failing test that demonstrates the bug
2. **Fix**: Implement the minimal fix with proper typing (modern syntax)
3. **Log**: Add or improve logging to help diagnose similar issues
4. **Test**: Ensure the test now passes and coverage is maintained
5. **Format**: Run formatting tools and remove unused imports
6. **Validate**: Run all checks
7. **Document**: Update CHANGELOG.md (REQUIRED if user-facing)

### For Refactoring

1. **Maintain**: Keep all existing tests passing
2. **Type**: Ensure typing coverage remains 100%
3. **Test**: Maintain 95%+ test coverage
4. **Adapt**: Continue using adaptors for OS operations
5. **Format**: Apply consistent formatting
6. **Skip**: Don't update CHANGELOG for internal changes

## ⚠️ Common Pitfalls to Avoid

### Type Safety Pitfalls

```python
# ❌ AVOID: Bare types and missing annotations
def process(data) -> dict:
    return {}

# ❌ AVOID: Old-style typing imports
from typing import List, Dict
def process(data: List[str]) -> Dict[str, Any]:
    return {}

# ✅ CORRECT: Complete type annotations with modern syntax
from typing import Any
def process(data: list[str]) -> dict[str, Any]:
    return {}
```

### OS Operations Pitfalls

```python
# ❌ AVOID: Direct OS usage in src/
import os
if os.path.exists("file.txt"):
    pass

# ✅ CORRECT: Use adaptors
if self.os_adaptor.path_exists("file.txt"):
    pass
```

### Testing Pitfalls

```python
# ❌ AVOID: Testing implementation details
@patch('dd_license_attribution.processor.DataProcessor._internal_method')
def test_internal_behavior(self, mock_internal):
    # This makes tests brittle and couples them to implementation
    pass

# ❌ AVOID: Not mocking external dependencies (creates integration tests)
def test_without_mocking(self):
    processor = DataProcessor()  # Uses real OS operations
    result = processor.process_file("real_file.txt")  # Depends on filesystem
    assert result is not None

# ❌ AVOID: Over-mocking (mocking the class under test)
@patch('dd_license_attribution.processor.DataProcessor.process_file')
def test_over_mocked(self, mock_process):
    mock_process.return_value = "mocked"
    # This doesn't test any real logic
    pass

# ❌ FORBIDDEN: Not verifying mock interactions
def test_without_mock_verification(self):
    os_adaptor = Mock()
    os_adaptor.read_file.return_value = "test content"
    
    processor = DataProcessor(os_adaptor=os_adaptor)
    result = processor.process_file("test.txt")
    
    assert result == "processed: test content"
    # MISSING: Mock verification - this test is incomplete!

# ✅ CORRECT: Test public interface with mocked dependencies AND verification
def test_public_behavior_with_mocked_dependencies(self):
    os_adaptor = Mock()
    os_adaptor.read_file.return_value = "test content"
    
    processor = DataProcessor(os_adaptor=os_adaptor)
    result = processor.process_file("test.txt")
    
    # Verify result
    assert result == "processed: test content"
    
    # CRITICAL: ALWAYS verify mock interactions
    os_adaptor.read_file.assert_called_once_with("test.txt")

# ✅ CORRECT: Test error handling with mocked exceptions AND verification
def test_handles_file_not_found(self):
    os_adaptor = Mock()
    os_adaptor.read_file.side_effect = FileNotFoundError("File not found")
    
    processor = DataProcessor(os_adaptor=os_adaptor)
    
    with pytest.raises(FileNotFoundError):
        processor.process_file("nonexistent.txt")
    
    # CRITICAL: ALWAYS verify mock was called
    os_adaptor.read_file.assert_called_once_with("nonexistent.txt")
```

## 🎯 Quality Gates

All code must pass these automated checks:

1. **MyPy**: 100% typing coverage, strict mode
2. **Pytest**: 95%+ test coverage
3. **isort**: Import organization
4. **black**: Code formatting
5. **CI Pipeline**: All checks must pass

## 📚 Additional Resources

- [MyPy Documentation](https://mypy.readthedocs.io/)
- [pytest Documentation](https://docs.pytest.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Black Code Style](https://black.readthedocs.io/)
- [isort Documentation](https://pycqa.github.io/isort/)

---

**Remember**: These guidelines are not suggestions—they are requirements. Every line of code must be properly typed, use adaptors for OS operations, be thoroughly tested, properly formatted, and documented in the CHANGELOG when user-facing.
