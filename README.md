# ospo-tools

A set of tools mantained by ospo to work with open source projects

## get-licenses-copyrights

This is a tool to generate 3party-license csv files used to track dependencies licenses.

As Today, only golang is supported. We plan to expand to other languages soon.

This tool collects license and other metadata information using multiple sources, including the GitHub API and the go-licenses package.
It supports gathering data from various repositories to generate a comprehensive 3rd-party license CSV file.
Because, these tools require calls to public APIs, and the APIs may trottle down based in usage, it is spected that run takes many minutes depeding mostly in the size of the project dependency tree.

### requirements

- python3.10+ - [Python install instructions](https://www.python.org/downloads/)
- gopkg - [GoLang and GoPkg install instructions](https://go.dev/doc/install)
- go-licenses - [GoLicenses install instructions](https://github.com/google/go-licenses?tab=readme-ov-file#installation)
- libmagic (only on mac):
  - `brew install libmagic`

### usage

To install and run the command after cloning the repository:

```bash
#starting at the root of the repository
pip install .

# Optionally you can define a GITHUB_TOKEN, if used it will raise the throttling threashold and maspeed up your generation calls to github APIs.
export GITHUB_TOKEN=YOUR_TOKEN
get-licenses-copyrights https://github.com/owner/repo > LICENSE-3rdparty.csv
```

The following optional parameters are available:

- `--deep-scanning`: it will attemp to parse license and copyright information from full package sourcecode using codescan, this is a intensive task, that depending in the package size, may take hours or even days to process.
- `--only-transitive-dependencies`: it will not attempt to extract license and copyright from the passed package, only its dependencies.
- `--only-root-project`: it will only extract information from the licenses and copyright of the passed package, not its dependencies.
- `--cache-dir`: if a directory is passed to this parameter all the dependencies source code downloaded for analysis is kept in the directory and can be reused between runs. By default, nothing is reused between runs.                                 │
- `--go-licenses-csv-file`: The path to the Go licenses CSV output file to be used as hint. If your package is a Go project, passing the hint helps identifying the origin of the dependencies.

For more details about optional parameters pass `--help` to the command.

### Development

To develop install the development dependencies in a virtual environment:

```bash
# starting at the root of the repository
# create and activate a venv
python3 -m venv venv
source venv/bin/activate
pip install -e ".[dev]"
```

#### Coverage report

To generate test coverage reports locally the following lines need to be run in the root of the repository.

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
venv/bin/black src/ tests/
```

We use MyPy for validating typing of the project. We keep 100% typing coverage.

```bash
venv/bin/mypy .
```

Both, black and mypy requirements are enforced by CI workflow in PRs.

### Testing

We are using pytest and mutmut and configuring them via `pyproject.toml`.
Unit tests are located in `tests/unit`.

Running `pytest` without parameters in the root of the project runs all unit tests.
By default, a coverage report is created from the run. 
A less than 90% coverage fails the pytest run.

For generating and running mutation tests, we run `mutmut run`.
To read the results of mutation test in more detail than the initial output, we run `mutmut results`.

The CI step in PRs and merge to main runs all tests and a few end to end tests defined as github workflows in the .github directory.
Mutation tests are not evaluated for CI.

### current development state

- Initial set of dependencies is collected via github-sbom api.
- Action packages are ignored.
- Go packages can use go-licenses output as hint when passed by the `--go-licenses-csv-file` argument.
- Purls are only parsed for Go.
