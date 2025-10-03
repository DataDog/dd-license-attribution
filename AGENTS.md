# AI Agent Guidelines for dd-license-attribution

This document provides comprehensive guidelines for AI agents working on the dd-license-attribution codebase. These rules ensure code quality, maintainability, and consistency across all contributions.

## 🚨 Critical Requirements

All code changes must comply with these non-negotiable requirements:

- **100% typing coverage** validated by MyPy
- **95%+ unit test coverage** for all business logic
- **OS operations through adaptors only** (no direct imports)
- **Formatted with isort and black**
- **CHANGELOG.md updates** for user-facing changes

## 📋 Pre-Commit Validation Checklist

Before suggesting any code changes, verify:

- [ ] `mypy src/ tests/` passes with no errors
- [ ] All functions have complete type annotations
- [ ] No direct OS imports in `src/` code (use adaptors)
- [ ] `pytest --cov=src/dd_license_attribution --cov-fail-under=95` passes
- [ ] New code has corresponding unit tests with proper mocking
- [ ] Unit tests mock all external dependencies (adaptors, network calls, etc.)
- [ ] No unit tests make real filesystem, network, or database calls
- [ ] Tests focus on public interfaces, not internal implementation details
- [ ] `isort --check-only src/ tests/` and `black --check src/ tests/` pass
- [ ] CHANGELOG.md updated for user-facing changes

## 🔧 Type Safety Requirements

### Mandatory Type Annotations

All code must have complete type annotations:

```python
# ✅ REQUIRED: Complete type annotations
def process_data(data: List[str], config: Dict[str, Any]) -> Optional[ProcessedResult]:
    result: Optional[str] = None
    items: List[Dict[str, Any]] = []
    return ProcessedResult(result, items)

# ❌ FORBIDDEN: Missing type annotations
def process_data(data, config):
    result = None
    return result
```

### Required Imports for Typing

```python
from typing import Dict, List, Optional, Union, Any, Protocol, TypeAlias, Literal
```

### Class and Method Typing

```python
# ✅ REQUIRED: Typed class with all methods annotated
class DataProcessor:
    def __init__(self, config: Dict[str, Any]) -> None:
        self.config: Dict[str, Any] = config
        self.cache: Dict[str, Any] = {}
    
    def process(self, data: str) -> Optional[str]:
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
# ✅ REQUIRED: Create new adaptor with Protocol
from typing import Protocol

class NetworkAdaptor(Protocol):
    def make_request(self, url: str) -> str: ...

class RealNetworkAdaptor:
    def make_request(self, url: str) -> str:
        import requests  # OK in adaptor implementation
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
        
        # Verify no unnecessary calls were made
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
    
    assert result == expected_result
    self.os_adaptor.read_file.assert_called_once_with("LICENSE")

# ✅ Reset mocks between tests if needed
def teardown_method(self) -> None:
    """Clean up after each test."""
    self.os_adaptor.reset_mock()
    self.network_adaptor.reset_mock()
```

### Contract Tests for External Libraries

```python
# tests/contract/test_github_api.py
class TestGitHubAPIContract:
    def test_repository_endpoint_structure(self) -> None:
        """Ensure GitHub API returns expected structure."""
        response = github_api.get_repository("owner/repo")
        assert "name" in response
        assert "full_name" in response
        assert isinstance(response["name"], str)
```

## 🎨 Code Formatting

### Automatic Formatting Commands

```bash
# REQUIRED: Format all code before committing
isort src/ tests/ && black src/ tests/

# Validation commands
isort --check-only src/ tests/
black --check src/ tests/
```

### IDE Configuration

Configure your IDE to auto-format on save:
- Enable isort and black formatting
- Set line length to 88 (black default)
- Configure import sorting according to isort rules

## 📝 CHANGELOG Maintenance

### What to Document

**Include in CHANGELOG:**
- New features visible to users
- Bug fixes that affect user experience
- Breaking changes
- Security updates
- Deprecated functionality

**Exclude from CHANGELOG:**
- Internal refactoring
- Test improvements
- Code style changes
- Documentation updates

### CHANGELOG Format

```markdown
## [Unreleased]

### Added
- New feature for license attribution
- Support for GitHub repositories

### Changed
- Updated dependency versions
- Improved error handling

### Fixed
- Bug in license detection (#123)
- Memory leak in large repositories

### Security
- Updated vulnerable dependencies
```

## 🚀 Development Workflow

### For New Features

1. **Plan**: Break down complex features into smaller, testable components
2. **Type**: Write fully typed interfaces and classes
3. **Adapt**: Use adaptors for any OS operations
4. **Test**: Write comprehensive unit tests (95%+ coverage)
5. **Format**: Run isort and black
6. **Validate**: Run MyPy and pytest
7. **Document**: Update CHANGELOG.md

### For Bug Fixes

1. **Reproduce**: Write a failing test that demonstrates the bug
2. **Fix**: Implement the minimal fix with proper typing
3. **Test**: Ensure the test now passes and coverage is maintained
4. **Format**: Run formatting tools
5. **Validate**: Run all checks
6. **Document**: Update CHANGELOG.md if user-facing

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

# ✅ CORRECT: Complete type annotations
def process(data: List[str]) -> Dict[str, Any]:
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

# ✅ CORRECT: Test public interface with mocked dependencies
def test_public_behavior_with_mocked_dependencies(self):
    os_adaptor = Mock()
    os_adaptor.read_file.return_value = "test content"
    
    processor = DataProcessor(os_adaptor=os_adaptor)
    result = processor.process_file("test.txt")
    
    assert result == "processed: test content"
    os_adaptor.read_file.assert_called_once_with("test.txt")

# ✅ CORRECT: Test error handling with mocked exceptions
def test_handles_file_not_found(self):
    os_adaptor = Mock()
    os_adaptor.read_file.side_effect = FileNotFoundError("File not found")
    
    processor = DataProcessor(os_adaptor=os_adaptor)
    
    with pytest.raises(FileNotFoundError):
        processor.process_file("nonexistent.txt")
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
