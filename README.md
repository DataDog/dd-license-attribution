# Datadog License Attribution Tracker

Datadog License Attribution Tracker is a tool that collects license and copyright information for third party dependencies of a project and returns a list of said dependencies and their licenses and copyright attributions, if found.

As of today, Datadog License Attribution Tracker supports Go and Python projects. It will be extended in the future to support more languages.

The tool collects license and other metadata information using multiple sources, including the GitHub API, pulled source code, the go-pkg list command output, and the metadata collected from successful dependency installation via PyPI.
It supports gathering data from various repositories to generate a comprehensive list of third party dependencies.

Runs may take minutes or hours depending on the size of the project dependency tree and the depth of the scanning.

### Requirements

- python3.10+ - [Python install instructions](https://www.python.org/downloads/)
- gopkg - [GoLang and GoPkg install instructions](https://go.dev/doc/install)
- libmagic (only on mac):
  - `brew install libmagic`

### Usage

To install and run the command after cloning the repository:

```bash
#starting at the root of the repository
pip install .

# Optionally you can define a GITHUB_TOKEN, if used it will raise the throttling threashold and maspeed up your generation calls to github APIs.
export GITHUB_TOKEN=YOUR_TOKEN
dd-license-attribution https://github.com/owner/repo > LICENSE-3rdparty.csv
```

The following optional parameters are available:

**Scanning Options**
- `--deep-scanning`: Parses license and copyright information from full package source code using [scancode-toolkit](). This is a intensive task, that depending in the package size, may take hours or even days to process.
- `--only-transitive-dependencies`: Extracts license and copyright from the passed package, only its dependencies.
- `--only-root-project`: Extracts information from the licenses and copyright of the passed package, not its dependencies.
- `--skip-pypi-strategy`: Skips the strategy that collects dependencies from PyPI.
- `--skip-gopkg-strategy`: Skips the strategy that collects dependencies from GoPkg.

**Cache Configuration**
- `--cache-dir`: if a directory is passed to this parameter all the dependencies source code downloaded for analysis is kept in the directory and can be reused between runs. By default, nothing is reused between runs.
- `--cache-ttl`: seconds until cached data is considered expired, by default 1 day.

For more details about optional parameters pass `--help` to the command.

### Development and Contributing

For instructions on how to develop or contribute to the project, read our [CONTRIBUTING.md guidelines](./CONTRIBUTING.md).

### Current Development State

- Initial set of dependencies is collected via github-sbom api, gopkg listing, and PyPI.
- Action packages are ignored.
- Python usage of PyPI metadata is limited to pure Python projects. If there are native dependencies or out-of-pypi requirements, failures are expected. The usage of the PyPI strategy can be disabled in those cases, but will reduce the coverage of the tool.
