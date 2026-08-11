# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased]

### Added
- New reusable composite GitHub Action (`action.yml` at the repository root) that regenerates a third-party license SBOM and validates it against a committed `LICENSE-3rdparty.csv` file. It sets up its own Python, Go, Node.js/npm/Yarn, and Rust/dd-rust-license-tool toolchains as needed, installs the pinned tool version, and takes the target as an `owner/name` `repository` input (defaulting to the current repository). It automatically builds a mirror so the branch actually under test (`pull_request` head, merge-queue, or pushed branch) is scanned; when `github-token` is provided, the mirror supports cloning **private repositories**. `pull_request_target` intentionally remains on the base branch to avoid exposing privileged tokens while scanning untrusted code. Additional inputs control `ecosystem`/`package`, the `csv-path` to compare, `--override-spec`, per-strategy enable/disable toggles including `rust-strategy`, `--experimental-strategy`, `--deep-scanning`, `--yarn-subdir`, the `default-branch`, the `github-token`, Python/Go/Node.js/Rust versions (each can be set to `false` to skip the internal toolchain setup when the calling workflow already provides it), and the exact-vs-structural `compare` mode; it exposes `sbom-path` and `matches` outputs. Callers with special needs can supply their own mirror-specification file via `use-mirrors`, whose entries are merged ahead of (and thus take precedence over) the auto-built mirror. Reference it as `DataDog/dd-license-attribution@<ref>`.
- New `yarn-subdir` action input accepts newline-separated paths and forwards each path as a `--yarn-subdir` argument.
- New `--experimental-strategy` flag for `generate-sbom`. When enabled, dependency discovery and metadata extraction run in three phases: pre-finders run once on the root package (e.g. GitHub SBOM, which already returns a full transitive closure); finders run in a fixpoint loop (up to 5 iterations) until the dependency set stabilises; enrichers run once on the complete set. When combined with `--ecosystem`, only the ecosystem-relevant finder is enabled by default; `--no-*` flags still override these defaults. This resolves cases where transitive dependencies discovered by one finder were not explored by other finders.
- New `markdown` value for `generate-sbom --format` to emit Markdown license compliance reports.
- New repeatable `generate-sbom --format` support with `--output-dir` to emit CSV, Markdown, and SPDX report files in one run.
- New `generate-sbom` subcommand with a `--format` option supporting CSV output by default and SPDX 2.3 JSON output via `--format spdx`.
- `generate-sbom-csv` now emits a WARNING for each package whose license value is not a properly written SPDX expression composed entirely of OSI-approved identifiers. Using a non-OSI-approved license may be acceptable depending on your project's requirements. The warning message includes a reference to `generate-overrides` (interactive) and `clean-spdx-id` (AI-assisted) as remediation options.
- Add `--ecosystem go` support for direct Go package/module dependency analysis (e.g., `ddla generate-sbom-csv --ecosystem go github.com/stretchr/testify@v1.9.0`)
- New `--ecosystem` CLI option for `generate-sbom-csv` to accept package names by ecosystem. Supports `npm`, `python`, and `pypi` (e.g., `ddla generate-sbom-csv --ecosystem python --no-gh-auth requests==2.31.0`)
- Support for GitHub renamed/transferred repositories
- Support for Yarn package manager in npm collection
- New `--yarn-subdir` CLI option for specifying subdirectories with additional `yarn.lock` files in monorepos
- New `clean-spdx-id` CLI command to convert long license descriptions to valid SPDX license expressions using LLMs (OpenAI, Anthropic), including support for composite licenses (e.g., "MIT OR Apache-2.0")
- Rust ecosystem support: auto-detect Cargo projects in GitHub URL mode, plus `--ecosystem rust` for direct crate analysis. Delegates to dd-rust-license-tool and honors per-project `license-tool.toml`.
- `--ecosystem rust` now supports binary-only crates by falling back to the published crates.io source archive when Cargo cannot use the crate as a library dependency.

### Changed
- The action's `github-token` input now defaults to empty. Public and untrusted targets run without credentials unless the caller explicitly provides a token.
- The minimum supported Typer version is now 0.27.0.
- Markdown `generate-sbom` reports now show the root package version explicitly, exclude the root package from the dependency table, and include root license and copyright in the summary.
- PyPI collection strategy now performs case-insensitive key matching for project_urls dictionary to better handle different key capitalizations from PyPI metadata
- PyPI package name is now `datadog-license-attribution` to follow Datadog's PyPI packaging conventions. The CLI command name (`dd-license-attribution`) is unchanged.
- `authors` metadata in `pyproject.toml` now lists Datadog, Inc. instead of individual maintainers, and `project.urls` now also sets `Repository`.

### Deprecated
- `generate-sbom-csv` is deprecated in favor of `generate-sbom --format csv`; it still works and emits a deprecation warning.

### Fixed
- Fixed Rust crates.io source archive handling by moving download and extraction logic out of OS adaptors and enforcing bounded decompression before extraction.
- Fixed repeated action invocations overwriting earlier SBOM outputs by creating a unique output file for each invocation.
- Fixed the action's default tokenless mode failing before a scan because it did not pass `--no-gh-auth` when `github-token` was empty.
- Fixed the action requiring `csv-path` to exist during structural-only validation with `compare: false`.
- Fixed `generate-sbom --no-gh-auth` so it ignores a `GITHUB_TOKEN` environment variable instead of using a potentially invalid token.
- Fixed npm ecosystem SBOM generation when `npm list --json` emits warnings on stderr, which previously caused empty CSV output for packages such as `dd-trace`.
- Fixed npm metadata collection using semver ranges instead of resolved versions, causing incorrect or failed npm registry API lookups
- Fixed support for package aliases in both Yarn and npm projects (e.g., `"@datadog/source-map": "npm:source-map@^0.6.0"`). The tool now parses both yarn.lock and package-lock.json files to resolve aliases to their real package names before fetching npm registry metadata, eliminating 404 errors for aliased packages
- Fixed CSV output to use consistent Windows-style line endings (`\r\n`) across all platforms and Python versions, preventing line ending inconsistencies between different Python versions

## [0.5.0] - 2025-10-29

### Added
- New `generate-overrides` CLI command to create valid ddla-overrides files (#124, #115)
- New collection strategy that reads existing LICENSE-3rdparty.csv files (#114)
- Node.js/NPM support for collecting Node.js dependency metadata (#88)
- `--no-scancode-toolkit-strategy` parameter to skip the ScanCode Toolkit strategy (#90)
- `--no-github-sbom-strategy` parameter to skip the GitHub SBOM strategy
- `--use-mirrors` parameter to support alternative repository URLs for source code fetching
- Support for reference mapping for mirror declarations
- Copyright metadata cleanup strategy that eliminates extra whitespace, dates, and copyright strings (#107)
- Custom splitting utility for copyright metadata used in GitHub SBOM and PyPI collection strategies (#111)

### Changed
- Improved UTF encoding handling to support UTF-16 and system default encodings (#106)
- Enhanced NPM strategy to skip projects using workspaces with a warning
- Enhanced NPM strategy to skip execution when package.json is not available
- Improved logging to avoid noisy debug messages from third-party dependencies (#101)
- Improved PyPI strategy metadata extraction to handle packages with None values in project_urls
- Improved PyPI strategy to log warnings when packages return 404 or 503 errors
- Performance improvements by removing repeated HEAD check calls on remote repositories for Go
- Better handling of GitHub API rate limits

### Fixed
- Fixed issues with PyPI metadata extraction for packages with missing information explicitly declared
- Fixed bug where PyPI returns dependency with None as project-urls
- Improved error handling for non-existent repositories
- Fixed copyright metadata output to remove 'ed' suffix when word was 'copyrighted'


## [0.4.0-beta] - 2025-04-10

### Added

- `--no-pypi-strategy` optional parameter in CLI to skip pypi usage when unsupported binary dependencies are required.
- `--no-gopkg-strategy` optional parameter in CLI to skip gopkg usage when unsuppord module definition is part of the dependencies required.
- Warning emited when a dependency includes a License that requires special attention. List of cautionary licenses is defined by config.
- Logging support
- `--override-spec` optional parameter in CLI to specify how to manually override known packages.

## Removed

- Autocomplete support for CLI.

## Changed

- `get-licenses-copyright` CLI was renamed to `dd-license-attribution`.

## [0.3.0-beta] - 2025-03-03

### Added

- Pypi support to augment the dependency metadata.
- Better error message when fetching github-sbom returns is called without proper permissions.

## [0.2.1-beta] - 2025-02-21

### Fixed

- Bug crashing excecution for constructing the wrong path for Go projects which root was nested multiple directories inside the root-project repository.

## [0.2.0-beta] - 2025-02-11

### Added

- New strategy based in GoPkg to replace the GoLicenses one and improve results reliability.

### Changed

- Improvements to CLI argument management.
- Performance improvements to the deep scan file collection logic.
- Consolidating testing adaptors in new module.
- Refactor to consolidate cache and fetching of external artifacts in new artifacts management component.

### Fixed

- Silenced detach head warnings from git calls.
- Pin transitive dependency `beautifulsoup4` since latest version breaks `scancode-toolkit` intermidiate dependency.

### Removed

- GoLicenses based strategy. Use the new GoPkg based strategy which provides more reliable output.

## [0.1.0-beta] - 2025-01-08

### Added

- Initial release with support for github-sbom, scancode-toolkit, repository-metadata, and go-license based strategies.
