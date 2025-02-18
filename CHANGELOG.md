
# Change Log

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](http://keepachangelog.com/)
and this project adheres to [Semantic Versioning](http://semver.org/).

## [Unreleased]

### Added

- Better error message when fetching github-sbom returns a 404 status code.

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
