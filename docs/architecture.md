# dd-license-attribution Architecture

This document describes the full architecture of the dd-license-attribution tool to help developers and coding agents understand how the codebase is structured and how data flows through the system.

## Overview

dd-license-attribution is a Python CLI tool that collects license and copyright information for third-party dependencies in open-source projects. It supports Go, Python (PyPI), and Node.js (npm/yarn) ecosystems.

The tool produces a `LICENSE-3rdparty.csv` file with columns: `component`, `origin`, `license`, `copyright`.

## Project Layout

```
src/dd_license_attribution/
├── cli/                          # CLI entry points (Typer framework)
│   ├── main_cli.py               # App definition, registers commands
│   ├── generate_sbom_csv_command.py   # Main command: build strategy pipeline, run collection, output CSV
│   ├── generate_overrides_command.py  # Interactive override generation
│   └── clean_spdx_id_command.py       # AI-powered SPDX license cleaning
├── metadata_collector/
│   ├── metadata.py               # Metadata dataclass (core data model)
│   ├── metadata_collector.py     # Orchestrator: seeds metadata, runs strategy pipeline
│   ├── project_scope.py          # Enum: ONLY_ROOT_PROJECT, ONLY_TRANSITIVE_DEPENDENCIES, ALL
│   ├── license_checker.py        # Warns about copyleft/cautionary licenses
│   └── strategies/               # All metadata collection strategies
│       ├── abstract_collection_strategy.py
│       ├── github_sbom_strategy.py
│       ├── gopkg_strategy.py
│       ├── pypi_strategy.py
│       ├── npm_collection_strategy.py
│       ├── scancode_strategy.py
│       ├── github_repository_strategy.py
│       ├── override_strategy.py
│       ├── license_3rd_party_strategy.py
│       └── cleanup_copyright_strategy.py
├── artifact_management/
│   ├── artifact_manager.py       # Base class: cache directory + TTL management
│   ├── source_code_manager.py    # Git clone caching, GitHub API, mirrors, canonical URLs
│   ├── go_package_resolver.py    # Resolves Go module/package specs to local dirs
│   ├── npm_package_resolver.py   # Resolves npm package specs to local dirs
│   ├── pypi_package_resolver.py  # Resolves PyPI package specs to local dirs
│   └── python_env_manager.py     # Creates/caches venvs for Python dependency extraction
├── report_generator/
│   ├── report_generator.py       # Delegates to a reporting writer
│   └── writters/
│       └── csv_reporting_writter.py  # Merges duplicates, outputs CSV
├── config/
│   ├── cli_configs.py            # Preset file locations, cautionary licenses
│   └── json_config_parser.py     # Parses mirror configs and override configs
├── adaptors/
│   ├── os.py                     # Wraps all filesystem/subprocess operations
│   └── datetime.py               # Wraps datetime.now() for testability
└── utils/
    ├── license_utils.py          # Detects long license text vs. SPDX identifiers
    ├── custom_splitting.py       # CSV-aware string splitting with quote/protected-term handling
    └── logging.py                # Logging setup (stderr handler)
```

## Core Data Model

```python
@dataclass
class Metadata:
    name: str | None          # Package name (e.g., "github.com/stretchr/testify")
    version: str | None       # Version string or commit hash
    origin: str | None        # Package URL (PURL) or repository URL
    local_src_path: str | None  # Local path to cloned/cached source code
    license: list[str]        # SPDX license identifiers (e.g., ["MIT", "Apache-2.0"])
    copyright: list[str]      # Copyright holders (e.g., ["Datadog, Inc."])
```

Every strategy receives and returns `list[Metadata]`. Strategies can add new entries, remove entries, or enrich existing ones.

## Strategy Pipeline Pattern

The core design is a **pipeline of strategies**. Each strategy implements:

```python
class MetadataCollectionStrategy(ABC):
    def augment_metadata(self, metadata: list[Metadata]) -> list[Metadata]
```

### How the Pipeline Runs

1. `MetadataCollector.collect_metadata(package)` creates a **seed entry**: `Metadata(name=package, version=None, origin=package)`.
2. The seed list is passed through each strategy in order.
3. Each strategy returns a (possibly modified) list of `Metadata`.
4. The final list goes to the report generator.

### Strategy Execution Order

The `generate_sbom_csv_command.py` builds the pipeline based on CLI flags. A typical full pipeline:

| Order | Strategy | Purpose |
|-------|----------|---------|
| 1 | **OverrideCollectionStrategy** (early) | Apply ADD overrides before other strategies |
| 2 | **GitHubSbomMetadataCollectionStrategy** | Fetch GitHub-generated SBOM via API; populates names, versions, origins |
| 3 | **GoPkgMetadataCollectionStrategy** | Parse `go.mod` / `go list -json all` for Go dependencies |
| 4 | **PypiMetadataCollectionStrategy** | Query PyPI API, create venvs, extract Python package metadata |
| 5 | **NpmMetadataCollectionStrategy** | Parse `package-lock.json` / `yarn.lock` for npm dependencies |
| 6 | **License3rdPartyMetadataCollectionStrategy** | Merge data from existing `LICENSE-3rdparty.csv` |
| 7 | **ScanCodeToolkitMetadataCollectionStrategy** | Deep scan source files for license/copyright text |
| 8 | **GitHubRepositoryMetadataCollectionStrategy** | Fetch license/owner from GitHub repo API |
| 9 | **OverrideCollectionStrategy** (late) | Apply REMOVE and REPLACE overrides after collection |
| 10 | **CleanupCopyrightMetadataStrategy** | Normalize copyright strings (remove years, "(c)", deduplicate) |

By default, all strategies are included in the pipeline. Individual strategies can be excluded using opt-out flags: `--no-pypi-strategy`, `--no-gopkg-strategy`, `--no-github-sbom-strategy`, `--no-npm-strategy`, `--no-scancode-strategy`.

### Strategy Details

**GitHubSbomMetadataCollectionStrategy**: Calls GitHub's dependency graph SBOM API. Filters by `ProjectScope`. Extracts license, version, and copyright from the SBOM response. Handles PURL-to-URL translation.

**GoPkgMetadataCollectionStrategy**: Walks directory for `go.mod` files, runs `go list -json all`, translates Go module paths to GitHub repository URLs, discovers HEAD branches via `git ls-remote`. Also supports a `local_project_path` mode (used with `--ecosystem go`): when set, skips source code checkout and runs `go list -m -json all` in the synthetic project created by `GoPackageResolver` to enumerate all transitive module dependencies.

**PypiMetadataCollectionStrategy**: Uses `PythonEnvManager` to create virtual environments and `pip install` dependencies. Queries the PyPI JSON API for metadata. Extracts homepage/repository URLs from multiple possible keys. Handles long license text vs. short SPDX identifiers.

**NpmMetadataCollectionStrategy**: Parses `package-lock.json` or `yarn.lock`. Reads individual `package.json` files from `node_modules`. Extracts license, repository URL, author. Supports `--yarn-subdir` for monorepo layouts. When used in npm-ecosystem mode, receives a `local_project_path` from `NpmPackageResolver`.

**PypiMetadataCollectionStrategy** also supports a `local_project_path` mode (used with `--ecosystem python`/`pypi`). When set, it skips canonical URL resolution and source code checkout, directly using `PythonEnvManager` on the synthetic project created by `PypiPackageResolver`.

**ScanCodeToolkitMetadataCollectionStrategy**: Uses the ScanCode library to scan source code files. Configurable file location filters (defaults: LICENSE, NOTICE, AUTHORS, etc.). Prioritizes holder > author > copyright in text. Cleans up generic/unknown license identifiers.

**GitHubRepositoryMetadataCollectionStrategy**: Fetches repository metadata from GitHub API. Extracts SPDX license ID and repository owner as copyright holder.

**OverrideCollectionStrategy**: Applies manual corrections defined in `.ddla-overrides` JSON files. Three operation types: ADD (insert new entry), REMOVE (delete matching entries), REPLACE (modify matching entries). Matches by `origin` and/or `component` fields. Reports unused rules as warnings.

**License3rdPartyMetadataCollectionStrategy**: Reads an existing CSV file and merges its data with collected metadata. Non-empty values in existing metadata take precedence.

**CleanupCopyrightMetadataStrategy**: Final pass that normalizes copyright strings by removing "copyright", "(c)", year patterns, deduplicating, and sorting.

## Artifact Management

### SourceCodeManager

Central component for git operations and caching.

- **Caching**: Cloned repos stored in timestamped directories (`YYYYMMDD_HHMMSSz/`) with configurable TTL (default 24h).
- **Canonical URLs**: Resolves GitHub 301 redirects for renamed/transferred repositories.
- **GitHub API**: Caches repository info API calls.
- **Mirror support**: Maps original URLs to mirror repositories with optional ref mapping.
- **Branch discovery**: Uses `git ls-remote` to find default (HEAD) branch.

### GoPackageResolver

Resolves Go module/package specs (e.g., `github.com/stretchr/testify@v1.9.0`, `github.com/DataDog/dd-trace-go/v2/ddtrace/tracer`) into local directories containing a synthetic Go project with `go.mod` and `main.go`. Creates a sanitized subdirectory, writes a `go.mod` with the parsed module requirement and a `main.go` with a blank import, then runs `go mod tidy` to resolve dependencies. Uses a **separate temp directory** from SourceCodeManager's cache to avoid collisions.

### NpmPackageResolver

Resolves npm package specs (e.g., `express`, `@scope/pkg@1.0.0`) into local directories containing a `package-lock.json`. Creates a minimal `package.json`, runs `npm install --package-lock-only`, and returns the directory path. Uses a **separate temp directory** from SourceCodeManager's cache to avoid collisions.

### PypiPackageResolver

Resolves PyPI package specs (e.g., `requests`, `requests==2.31.0`, `Flask[async]>=2.0`) into local directories containing a minimal `setup.py` with the package as a dependency. `PythonEnvManager` then installs dependencies from this synthetic project. Uses a **separate temp directory** from SourceCodeManager's cache to avoid collisions.

### PythonEnvManager

Creates and caches Python virtual environments for dependency extraction. Detects Python projects by looking for `requirements.txt`, `setup.py`, `pyproject.toml`, `Pipfile`, etc. Extracts installed packages via `pip list --format=json`.

### ArtifactManager (Base)

Provides shared cache directory validation and TTL management. Defines `SourceCodeReference` dataclass (`repo_url`, `branch`, `local_root_path`, `local_full_path`).

## Adaptors Layer

All filesystem and subprocess operations in `src/` go through adaptors (no direct `os`, `subprocess`, `pathlib` imports). This enables unit testing via mock injection.

**OSAdaptor** (`adaptors/os.py`):
- File I/O: `open_file()`, `write_file()` (handles UTF-8/UTF-16 encoding fallback)
- Directory: `list_dir()`, `walk_directory()`, `create_dirs()`, `is_dir()`
- Path: `path_exists()`, `path_join()`
- Commands: `output_from_command()`, `run_command()`, `run_command_with_check()`
- Navigation: `change_directory()`, `get_current_working_directory()`

**DatetimeAdaptor** (`adaptors/datetime.py`):
- `get_datetime_now()` — returns current UTC datetime

## Report Generation

`ReportGenerator` delegates to `CSVReportingWritter`, which:
1. Groups metadata entries by `(name, origin)` key
2. Merges license and copyright sets for duplicate keys
3. Outputs CSV with columns: `component`, `origin`, `license`, `copyright`
4. Uses `csv.QUOTE_ALL` for proper escaping
5. Sorts output by component name, then origin

## Configuration

### CLI Configs (`config/cli_configs.py`)
- `preset_license_file_locations`: LICENSE, LICENSE.txt, COPYING, LICENCE, etc.
- `preset_copyright_file_locations`: NOTICE, AUTHORS, CONTRIBUTORS, LICENSE, etc.
- `preset_cautionary_licenses`: GPL, EUPL, AGPL variants

### JSON Config Parser (`config/json_config_parser.py`)
- `load_mirror_configs()`: Parses mirror specs with optional ref mapping
- `load_override_configs()`: Parses override rules from `.ddla-overrides` JSON files

## Overrides System

Users can create `.ddla-overrides` JSON files with rules to correct metadata:

- **ADD**: Insert a dependency that wasn't automatically detected
- **REMOVE**: Exclude a dependency from the output
- **REPLACE**: Fix incorrect license/copyright/origin for a dependency

Rules match by `origin` and/or `component`. The override strategy can be placed at multiple points in the pipeline (early for ADD, late for REMOVE/REPLACE).

The `generate-overrides` command provides an interactive workflow to create these files.

## Data Flow: End to End

```
CLI invocation (generate-sbom-csv)
    │
    ├── Parse arguments, setup logging
    ├── Load configs (mirrors, overrides)
    ├── Initialize GitHub client (with GITHUB_TOKEN or unauthenticated)
    ├── Create SourceCodeManager (caching, canonical URLs, mirrors)
    ├── Build strategy pipeline from CLI flags
    │
    ▼
MetadataCollector.collect_metadata(package)
    │
    ├── Create seed: Metadata(name=package, version=None, origin=package)
    ├── Strategy 1: augment_metadata([seed]) → [entries...]
    ├── Strategy 2: augment_metadata([entries...]) → [entries...]
    ├── ...
    └── Strategy N: augment_metadata([entries...]) → [final entries]
    │
    ▼
LicenseChecker.check_cautionary_licenses()
    → Log warnings for GPL/AGPL/EUPL licenses
    │
    ▼
ReportGenerator.generate_report(metadata)
    → CSVReportingWritter: merge duplicates, format CSV
    │
    ▼
Print CSV to STDOUT
    │
    ▼
Log unused override warnings, cleanup temp dirs
```

## Supported Ecosystems

| Ecosystem | Package Resolver | Strategies Used |
|-----------|-----------------|-----------------|
| **Go** (project) | — (uses `go list`) | GitHubSbom, GoPkg, ScanCode, GitHubRepository |
| **Go** (package) | GoPackageResolver | GoPkg, ScanCode, GitHubRepository |
| **Python** | PythonEnvManager | GitHubSbom, PyPI, ScanCode, GitHubRepository |
| **npm** (project) | — (reads lockfiles) | GitHubSbom, Npm, ScanCode, GitHubRepository |
| **npm** (package) | NpmPackageResolver | Npm, ScanCode, GitHubRepository |
| **python** (package, alias: **pypi**) | PypiPackageResolver | PyPI, ScanCode, GitHubRepository |

## Testing Architecture

```
tests/
├── unit/          # 27 files — mock-based, no real I/O
└── contract/      # 5 files — validate external library behavior
```

- **Unit tests**: All external dependencies (adaptors, APIs, filesystem) are mocked via dependency injection. Coverage target: 95%+ (CI enforces 90%).
- **Contract tests**: Hit real libraries/APIs to detect breaking changes on upgrade. Separate from unit tests.
- **Integration tests**: Run via CI workflow against real repositories. Validate end-to-end CSV output.

## Key Design Decisions

1. **Adaptor pattern for OS operations**: Enables pure unit tests with no filesystem or subprocess calls.
2. **Strategy pipeline**: New metadata sources can be added as new strategies without modifying existing code.
3. **Dependency injection**: All classes receive their dependencies (adaptors, managers) via constructor, making them testable.
4. **Seed-based collection**: `MetadataCollector` creates a minimal seed entry; strategies enrich it progressively.
5. **Separate cache directories**: NpmPackageResolver and PypiPackageResolver use their own temp dirs to avoid collisions with SourceCodeManager's cache.
6. **Override interleaving**: Override strategy can appear at multiple points in the pipeline (early ADD, late REMOVE/REPLACE).

## External Dependencies

| Library | Purpose |
|---------|---------|
| typer | CLI framework |
| agithub | GitHub API client |
| scancode-toolkit | License/copyright detection from source files |
| giturlparse | Git URL parsing |
| requests | HTTP client |
| semver | Semantic version parsing |
| openai | OpenAI API (for clean-spdx-id command) |
| anthropic | Anthropic API (for clean-spdx-id command) |
| pytz | Timezone handling |

## CI/CD

| Workflow | Trigger | What It Does |
|----------|---------|--------------|
| `coverage-unit-test.yml` | Push to main, all PRs | MyPy strict, contract tests, unit tests with coverage |
| `integration-test.yml` | Push to main, all PRs | End-to-end CLI tests against real repos |
| `linters.yml` | Push to main, all PRs | black + isort formatting checks |
| `scorecard.yml` | Weekly | OpenSSF security scorecard |
