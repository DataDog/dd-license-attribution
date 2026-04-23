# AI Agent Guidelines for dd-license-attribution

This document provides guidelines for AI agents working on the dd-license-attribution codebase.

## 🚨 Critical Requirements

All code changes must comply with these non-negotiable requirements:

- **100% typing coverage** validated by MyPy
- **95%+ unit test coverage** for all business logic
- **OS operations through adaptors only** (no direct imports)
- **Formatted with isort and black**
- **CHANGELOG.md updates** for user-facing changes
- **SPDX-License-Identifier header** in all source files

## 📄 File Headers and Licensing

**⚠️ Always use the current calendar year** in the copyright line (e.g., 2026 for files created in 2026).

Every Python source file (`.py`) and test file must include this header at the very top:

```python
# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2026-present Datadog, Inc.
```

**REQUIRED in**: all `src/` files, all `tests/` files, all Python scripts.

**NOT REQUIRED in**: empty/near-empty `__init__.py` files, config files (`.toml`, `.yaml`, `.json`), documentation (`.md`, `.txt`).

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

Use modern built-in generics (PEP 585). Import from `typing` only for `Any`, `Protocol`, `TypeAlias`, `Literal`, `TypeVar`, `Generic`.

```python
# ✅ REQUIRED
def process(data: list[str], config: dict[str, Any]) -> str | None: ...

# ❌ FORBIDDEN
from typing import Dict, List, Optional
def process(data: List[str], config: Dict[str, Any]) -> Optional[str]: ...
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

These are **permitted** in specific contexts only:

1. **`print()` for STDOUT** — allowed in CLI command functions for output intended for piping/redirection; not for debug messages.
2. **`sys.exit()`** — allowed in CLI command functions; not in business logic (raise exceptions instead).
3. **`sys.stderr`** — allowed in `utils/logging.py` for configuring log handlers only.

### REQUIRED Adaptor Usage

```python
from dd_license_attribution.adaptors.os import OSAdaptor

class FileProcessor:
    def __init__(self, os_adaptor: OSAdaptor) -> None:
        self.os_adaptor = os_adaptor

    def process_file(self, path: str) -> str:
        if self.os_adaptor.path_exists(path):
            return self.os_adaptor.read_file(path)
        return ""
```

### Command Execution Rules

All external command execution MUST go through adaptor functions in `dd_license_attribution.adaptors.os`. Use **argument lists**, not shell strings.

```python
# ✅ REQUIRED
run_command(["git", "clone", "--depth", "1", url, path])
output = output_from_command(["go", "list", "-json", "all"], cwd=project_path, env={"GOTOOLCHAIN": "auto"})

# ❌ FORBIDDEN
subprocess.run(command, shell=True)
os.system(f"git clone {url}")
```

- Use `cwd=` instead of `cd path &&` shell patterns
- Use `env=` instead of `VAR=value` shell prefixes (env is merged with the current environment)
- Use Python string operations instead of shell pipes — e.g., `if ref in output` instead of piping to `grep`

### Creating New Adaptors

When OS functionality is needed that doesn't exist, define a Protocol and both real and mock implementations:

```python
from typing import Protocol

class NetworkAdaptor(Protocol):
    def make_request(self, url: str) -> str: ...

class RealNetworkAdaptor:
    def make_request(self, url: str) -> str:
        return requests.get(url).text
```

## 🧪 Testing Requirements

### Coverage Targets

- **Core business logic**: 100% line coverage, 90% branch coverage
- **CLI interfaces**: 100% line coverage, 85% branch coverage
- **Adaptors**: Not unit tested (simple wrappers)
- **Configuration**: Integration tested only

### Test Structure

```python
# tests/unit/test_example.py
class TestExampleClass:
    def setup_method(self) -> None:
        self.os_adaptor = Mock()
        self.example = ExampleClass(self.os_adaptor)

    def test_success_case_returns_expected_result(self) -> None:
        self.os_adaptor.read_file.return_value = "test content"

        result = self.example.process_file("test.txt")

        assert result == "processed: test content"
        self.os_adaptor.read_file.assert_called_once_with("test.txt")

    def test_file_not_found_raises_exception(self) -> None:
        self.os_adaptor.path_exists.return_value = False

        with pytest.raises(FileNotFoundError):
            self.example.process_file("nonexistent.txt")

        self.os_adaptor.path_exists.assert_called_once_with("nonexistent.txt")
        self.os_adaptor.read_file.assert_not_called()
```

### Mocking Rules

**What to mock**: adaptors and any injected external dependency.

**What NOT to mock**: internal methods, the class under test, built-in Python functions.

**MANDATORY MOCK VERIFICATION**: Every mock used in a test MUST be verified with assertions — both call count AND parameters. Use the mock assertion API (`assert_called_once_with`, `assert_called_once`, `assert_not_called`, `assert_has_calls`), not bare `assert mock.call_count == N`.

### Contract Tests for External Libraries

When introducing a new external library dependency, create contract tests in `tests/contract/` that validate the specific behaviors our code depends on. These tests run against the real library (no mocking) and catch breaking changes on upgrade.

```python
# tests/contract/test_giturlparse.py
class TestGitURLParseContract:
    def test_parses_https_github_urls(self) -> None:
        parsed = giturlparse.parse("https://github.com/owner/repo.git")
        assert parsed.owner == "owner"
        assert parsed.repo == "repo"
        assert parsed.platform == "github"
```

Only test the specific features our codebase uses — not the full library API.

## 🎨 Code Formatting and Import Management

```bash
# Format
isort src/ tests/ && black src/ tests/

# Validate
isort --check-only src/ tests/
black --check src/ tests/
```

All imports must be at the top of the file — never inside functions, methods, or classes:

```python
# ❌ FORBIDDEN
class DataProcessor:
    def process(self, data: str) -> str:
        import json  # NEVER do this
        return json.dumps(data)
```

Follow isort's three-group order: standard library → third-party → local application.

## 📝 CHANGELOG Maintenance

**MUST include** user-visible changes: new features, bug fixes affecting users, breaking changes, new CLI options, output format changes, new config options.

**EXCLUDE**: internal refactoring, test improvements, code style changes, CI/CD changes.

When in doubt, ask: *"Would a user of this tool notice or care about this change?"*

```markdown
## [Unreleased]

### Added
- New `--output-format` CLI option for JSON output

### Fixed
- Bug in license detection for multi-license packages (#123)

### Security
- Updated requests 2.28.0 → 2.31.0 (CVE-2023-XXXXX)
```

## 📊 Logging Standards

Use a module-level logger in every module:

```python
logger = logging.getLogger(__name__)
```

**Level guidelines**: DEBUG for diagnostic details (variable values, iteration); INFO for milestones (started/completed operations); WARNING for recoverable unexpected situations; ERROR for operation failures; CRITICAL for unrecoverable failures.

Always use `%`-style lazy formatting — never f-strings or concatenation in log calls:

```python
# ✅ REQUIRED
logger.info("Processing %d files from %s", file_count, directory)

# ❌ FORBIDDEN
logger.info(f"Processing {file_count} files from {directory}")
```

Use `logger.exception(...)` inside `except` blocks to capture stack traces automatically.

## 🚀 Development Workflow

**CRITICAL**: This project uses **pipenv** exclusively for dependency management.

```bash
pipenv install --dev        # install dependencies
pipenv shell                # activate environment
pipenv run pytest           # run tests
pipenv run mypy src/ tests/ # type check
pipenv run black src/ tests/
pipenv run isort src/ tests/
pipenv install package-name          # add runtime dependency
pipenv install --dev package-name    # add dev dependency
```

**NEVER use** `pip install` directly, `venv`/`virtualenv` manually, `poetry`, or `conda`.

## GitHub Actions Conventions

- **Always pin actions to a full commit SHA** — never use mutable tags like `@v4` or `@main`
- Add a version comment after the SHA for readability: `uses: actions/checkout@34e11487... # v4.3.1`
- To find the SHA for a tag: `gh api repos/OWNER/REPO/git/ref/tags/TAG --jq '.object.sha'`
- Note: tags may be annotated — if the returned object type is `"tag"`, dereference it: `gh api repos/OWNER/REPO/git/tags/SHA --jq '.object.sha'`

## Git Conventions

- **Commit messages:** Do NOT include co-authoring information from coding agents (i.e. avoid "Co-Authored-By: Claude" attribution)
- **Pull requests:** Do NOT add "Generated with Claude Code" or similar footers — keep PR descriptions focused on the technical changes

## 🎯 Quality Gates

All code must pass these automated checks:

1. **MyPy**: 100% typing coverage, strict mode
2. **Pytest**: 95%+ test coverage
3. **isort**: Import organization
4. **black**: Code formatting
5. **ruff**: Security and reliability rules (src/ and tests/)
6. **CI Pipeline**: All checks must pass

## 📚 Additional Resources

- [MyPy Documentation](https://mypy.readthedocs.io/)
- [pytest Documentation](https://docs.pytest.org/)
- [Keep a Changelog](https://keepachangelog.com/)
- [Black Code Style](https://black.readthedocs.io/)
- [isort Documentation](https://pycqa.github.io/isort/)

---

**Remember**: These guidelines are not suggestions—they are requirements. Every line of code must be properly typed, use adaptors for OS operations, be thoroughly tested, properly formatted, and documented in the CHANGELOG when user-facing.
