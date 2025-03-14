# ospo-tools

A set of tools mantained by ospo to work with open source projects

## get-licenses-copyrights

This is a tool to generate 3party-license csv files used to track dependencies licenses.

As of today, we support Go and Python. We plan to expand to other languages soon.

This tool collects license and other metadata information using multiple sources, including the GitHub API, pulled source code, the go-pkg list command output, and the metadata collected from successful dependency installation via PyPI.
It supports gathering data from various repositories to generate a comprehensive 3rd-party license CSV file.

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
get-licenses-copyrights https://github.com/owner/repo > LICENSE-3rdparty.csv
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

### Development

To develop, install the development dependencies in a virtual environment:

```bash
# starting at the root of the repository
# create and activate a venv
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

#### Coverage report

To generate test coverage reports locally run these commands in the root of the repository:

```bash
# for unit tests
pytest --cov-report=xml --cov-fail-under=90 tests/unit
# for integration tests
pytest tests/integration
```

Github PRs and Push will trigger a run of unit tests for validation and fail if coverage is below 90%.

#### Linting

We currently use `black` to reformat files.
If you use VSCode, files will be automatically reformatted on saving. You can also run black from the command line:

```bash
venv/bin/black src tests
```

We use MyPy for validating typing of the project. We keep 100% typing coverage.

```bash
venv/bin/mypy src tests
```

Both, black and mypy requirements are enforced by CI workflow in PRs.

### Testing

The project uses `pytest` and `mutmut` (configured via `pyproject.toml`).
Unit tests are located in `tests/unit`.

Running `pytest` without parameters in the root of the project runs all unit tests.
By default, a coverage report is created from the run. A less than 90% coverage fails the pytest run.

To generate and run mutation tests, run `mutmut run`.
To read the results of mutation tests in more detail than the initial output, run `mutmut results`.

The CI step in PRs and merge to main runs all tests and a few end to end tests defined as github workflows in the .github directory.
Mutation tests are not evaluated for CI.

Contract tests are available to validate assumptions of external tools/libraries usages that are mocked in unit tests.
These tests do not run by default. To execute them, run `pytest tests/contract`.
CI runs the contract tests before attempting to run the unit tests.

### Current Development State

- Initial set of dependencies is collected via github-sbom api, gopkg listing, and PyPI.
- Action packages are ignored.
- Python usage of PyPI metadata is limited to pure Python projects. If there are native dependencies or out-of-pypi requirements, failures are expected. The usage of the PyPI strategy can be disabled in those cases, but will reduce they coverage of the tool.
