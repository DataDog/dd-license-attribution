# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased]

### Added
- Support for GitHub renamed/transferred repositories
- Support for Yarn package manager in npm collection

### Changed
- PyPI collection strategy now performs case-insensitive key matching for project_urls dictionary to better handle different key capitalizations from PyPI metadata

### Fixed
- Fixed npm metadata collection using semver ranges instead of resolved versions, causing incorrect or failed npm registry API lookups

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
