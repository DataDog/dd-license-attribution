# Datadog License Attribution Tracker

Datadog License Attribution Tracker is a tool that collects license and copyright information for third party dependencies of a project and returns a list of said dependencies and their licenses and copyright attributions, if found.

As of today, Datadog License Attribution Tracker supports Go, Python, and NodeJS projects. It will be extended in the future to support more languages.

The tool collects license and other metadata information using multiple sources, including the GitHub API, pulled source code, the go-pkg list command output, and metadata collected from PyPI and NPM.
It supports gathering data from various repositories to generate a comprehensive list of third party dependencies.

Runs may take minutes or hours depending on the size of the project dependency tree and the depth of the scanning.

### Getting Started

1. Install the required dependencies (see the [Requirements](#requirements) section below)
2. Clone this repository
3. Install the package:

```bash
pip install .
```
4. Run the tool on a GitHub repository:
```bash
dd-license-attribution https://github.com/owner/repo > LICENSE-3rdparty.csv
```

For more advanced usage, see the sections below.

### Requirements

- python3.11+ - [Python install instructions](https://www.python.org/downloads/)
- gopkg - [GoLang and GoPkg install instructions](https://go.dev/doc/install)
- Node.js (v14 or newer) and npm (v7 or newer) - [Node.js install instructions](https://nodejs.org/en/download/)
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

#### Scanning Options

##### Scope Control
- `--only-transitive-dependencies`: Extracts license and copyright from the passed package, only its dependencies.
- `--only-root-project`: Extracts information from the licenses and copyright of the passed package, not its dependencies.

##### Strategy Selection
- `--deep-scanning`: Enables intensive source code analysis using [scancode-toolkit](https://scancode-toolkit.readthedocs.io/en/latest/getting-started/home.html). This will parse license and copyright information from full package source code. Note: This is a resource-intensive task that may take hours or days to process depending on package size.
- `--no-pypi-strategy`: Skips the strategy that collects dependencies from PyPI.
- `--no-gopkg-strategy`: Skips the strategy that collects dependencies from GoPkg.
- `--no-github-sbom-strategy`: Skips the strategy that gets the dependency tree from GitHub.
- `--no-npm-strategy`: Skips the strategy that collects dependencies from NPM.

#### Cache Configuration

- `--cache-dir`: if a directory is passed to this parameter all the dependencies source code downloaded for analysis is kept in the directory and can be reused between runs. By default, nothing is reused between runs.
- `--cache-ttl`: seconds until cached data is considered expired, by default 1 day.

For more details about optional parameters pass `--help` to the command.

#### Output Format

The tool generates a CSV file with the following columns:
- `Component`: The name of the dependency
- `Origin`: The source URL of the dependency
- `License`: The detected license(s)
- `Copyright`: Copyright attribution(s) if found

Example output:
```csv
Component,Origin,License,Copyright
aiohttp,https://github.com/aio-libs/aiohttp,Apache-2.0,"Copyright (c) 2013-present aio-libs"
requests,https://github.com/psf/requests,Apache-2.0,"Copyright 2019 Kenneth Reitz"
```

#### Manual repository override configuration

In some cases, the code we want to scan is not in the main branch of a github repository or we do not have access to it. For example, when we are reviewing a PR, or preparing one in our local machine. Or when we are evaluating alternative dependency sources. In those cases, we would like to replace what is used to be scanned for a particular github URL.

To do so, we can create a json file where we map full repositories to a mirror repository, and, optionally, remap internal references, as for example, to use my PR branch in place of the main branch.

- `--use-mirrors`: Path to a JSON file containing mirror specifications for repositories. This is useful when you need to use alternative repository URLs to fetch source code. The JSON file should contain an array of mirror configurations, where each configuration has:
  - `original_url`: The original repository URL
  - `mirror_url`: The URL of the mirror repository
  - `ref_mapping` (optional): A mapping of references between the original and mirror repositories

Example mirror configuration file:
```json
[
    {
        "original_url": "https://github.com/DataDog/test",
        "mirror_url": "https://github.com/mirror/test",
        "ref_mapping": {
            "branch:main": "branch:development",
            "tag:v1.0": "branch:development"
        }
    }
]
```

Note: Currently, only branch-to-branch mapping is supported. The mirror URLs must also be GitHub repositories.

#### Manual output override configuration

In some cases, `dd-license-attribution` is not be able to extract a particular dependency information, or the information is not be available in the dependency itself to extract.
For those cases, there is an option to override, remove, or manually inject the information needed.
When this parameter is used we recommend that a PR or feature request is created against this project -- if `dd-license-attribution` needs to be improved -- or to the target dependency -- to add the missing information. This overrides should be a temporary measure while the changes are upstreamed.

- `--override-spec`: a file with a override description.

The override description file needs to be defined as a json file similar to the following example.

```json
[
  {
    "override_type":"ADD",
    "target":{"component":"aiohttp"},
    "replacement": {
      "component": "httpref",
      "origin":"https://github.com/http/ref",
      "license": "APACHE-2.0",
      "copyright": "testing inc."
    }
  }
]
```

Each element of the array in the spec is a rule.
Each rule has an override type:

- `ADD` means that the override is a new dependency to be added to the closure as specified in the replacement field.
- `REMOVE` means that the dependency needs to be removed from the closure.
- `REPLACE` means that any data about the specified dependency needs to be replaced by the one passed in the replacement field.

In all cases, the application depends on a matching condition specified as a `"field":"value"` where the field can be `component` or `origin`.
Component refers to the canonical name of the dependency as reported by the tool.
Origin refers to the purl used to find the dependency by package management tools.

If a override is never used, then a warning will be emitted at the end of execution.
The warnings allow users to identify unexpected target matching failures.

### Common Use Cases

#### Basic License Attribution
```bash
dd-license-attribution https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Deep Scanning with Caching
```bash
dd-license-attribution --deep-scanning --cache-dir ./cache https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Working with Private Repositories
```bash
export GITHUB_TOKEN=your_token
dd-license-attribution https://github.com/owner/private-repo > LICENSE-3rdparty.csv
```

#### Using Mirror Repositories
```bash
# Create mirrors.json with your mirror configurations
dd-license-attribution --use-mirrors=mirrors.json https://github.com/owner/repo > LICENSE-3rdparty.csv
```

### Development and Contributing

For instructions on how to develop or contribute to the project, read our [CONTRIBUTING.md guidelines](./CONTRIBUTING.md).

### Current Development State

- Initial set of dependencies is collected via github-sbom api, gopkg listing, and PyPI.
- Action packages are ignored.
- Python usage of PyPI metadata is limited to pure Python projects. If there are native dependencies or out-of-pypi requirements, failures are expected. The usage of the PyPI strategy can be disabled in those cases, but will reduce the coverage of the tool.
