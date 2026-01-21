# Datadog License Attribution Tracker

[![CI](https://github.com/DataDog/dd-license-attribution/actions/workflows/integration-test.yml/badge.svg)](https://github.com/DataDog/dd-license-attribution/actions/workflows/integration-test.yml)
[![Linters](https://github.com/DataDog/dd-license-attribution/actions/workflows/linters.yml/badge.svg)](https://github.com/DataDog/dd-license-attribution/actions/workflows/linters.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/DataDog/dd-license-attribution/badge)](https://api.securityscorecards.dev/projects/github.com/DataDog/dd-license-attribution)
[![Coverage](https://img.shields.io/badge/coverage-90%25+-brightgreen)](https://github.com/DataDog/dd-license-attribution)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://pycqa.github.io/isort/)
[![Type checker: mypy](https://img.shields.io/badge/type%20checker-mypy-blue.svg)](https://mypy-lang.org/)

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
dd-license-attribution generate-sbom-csv https://github.com/owner/repo > LICENSE-3rdparty.csv
```

For more advanced usage, see the sections below.

### Available Commands

`dd-license-attribution` provides three main commands:

1. **`generate-sbom-csv`** - Generate a CSV report (SBOM) of third-party dependencies
2. **`generate-overrides`** - Interactively generate override configuration files
3. **`clean-spdx-id`** - Convert long license descriptions to valid SPDX identifiers using AI

Run `dd-license-attribution --help` to see all available commands.

### Requirements

- python3.11+ - [Python install instructions](https://www.python.org/downloads/)
- libmagic (only on MacOS):
  - `brew install libmagic`
- libuci (only on MacOS)
  - `brew install icu4c && brew link icu4c --force`

#### Optional Requirements

- gopkg - [GoLang and GoPkg install instructions](https://go.dev/doc/install). Not required when skipping the GoPkg strategy (--no-gopkg-strategy)
- Node.js (v14 or newer) and npm (v7 or newer) - [Node.js install instructions](https://nodejs.org/en/download/). Not required when skipping the NPM strategy (--no-npm-strategy)

### Usage

#### Generating SBOM Reports

To install and run the command after cloning the repository:

```bash
#starting at the root of the repository
pip install .

# Optionally you can define a GITHUB_TOKEN, if used it will raise the throttling threashold and maspeed up your generation calls to github APIs.
export GITHUB_TOKEN=YOUR_TOKEN
dd-license-attribution generate-sbom-csv https://github.com/owner/repo > LICENSE-3rdparty.csv
```

The following optional parameters are available for `generate-sbom-csv`:

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
- `--no-scancode-strategy`: Skips the strategy that gets licenses and copyright attribution using ScanCode Toolkit.

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
aiohttp,https://github.com/aio-libs/aiohttp,Apache-2.0,"aio-libs"
requests,https://github.com/psf/requests,Apache-2.0,"Kenneth Reitz"
```

#### Output string configuration

There's a file at `src/dd_license_attribution/config/string_formatting_config.py` that you can customize. It's used to help formatting of the "Copyright" part of the output. These are strings that often come after a comma (like the Inc in "Datadog, Inc.") that should be exceptions to splitting the string on the comma.

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

#### Override Configuration

Sometimes `dd-license-attribution` may not detect all dependencies correctly, or the detected license information may be inaccurate. For these cases, you can provide an override configuration file to:

- **Fix incorrect license information** detected by automated tools
- **Add related dependencies** that weren't automatically discovered
- **Remove false positives** from your dependency report
- **Update copyright information** when the detected data is wrong

##### Creating Overrides Interactively (Recommended)

The easiest way to create overrides is using the **interactive `generate-overrides` command**:

```bash
# Generate the SBOM first
dd-license-attribution generate-sbom-csv https://github.com/owner/repo > LICENSE-3rdparty.csv

# Interactively fix entries with missing information
dd-license-attribution generate-overrides LICENSE-3rdparty.csv

# Regenerate with overrides applied
dd-license-attribution generate-sbom-csv https://github.com/owner/repo --override-spec .ddla-overrides > LICENSE-3rdparty.csv
```

The `generate-overrides` command will:
- Analyze your CSV file for entries with missing license or copyright
- Prompt you interactively to provide the correct information
- Generate a properly formatted `.ddla-overrides` file

**Options:**
- `--output` or `-o`: Specify custom output file location
- `--only-license`: Only fix entries with missing license information
- `--only-copyright`: Only fix entries with missing copyright information

##### Creating Overrides Manually

Alternatively, you can manually create an override configuration file:

**Quick Example:**
```json
[
  {
    "override_type": "replace",
    "target": {"component": "package-name"},
    "replacement": {
      "name": "package-name",
      "license": ["MIT"],
      "copyright": ["Copyright 2024 Author"]
    }
  }
]
```

Then use it with the `--override-spec` parameter:

```bash
dd-license-attribution generate-sbom-csv --override-spec .ddla-overrides https://github.com/your-org/your-project
```

📖 **For complete documentation, examples, and best practices, see [Override Configuration Guide](overrides.md)**

> **Recommendation**: When using overrides, consider creating a PR or feature request to improve `dd-license-attribution` or the target dependency to add missing information upstream. Overrides should ideally be a temporary measure.

#### Cleaning License Identifiers with AI

Sometimes the license information extracted by automated tools contains long license text instead of concise SPDX identifiers. For example, instead of "BSD-3-Clause", you might see the entire BSD license text. The `clean-spdx-id` command uses Large Language Models (LLMs) to intelligently convert these long descriptions into proper SPDX identifiers.

**Prerequisites:**
- An API key for OpenAI or Anthropic Claude
- Set the API key as an environment variable or pass it via `--api-key`

**Basic Usage:**

```bash
# Using OpenAI (default)
export OPENAI_API_KEY=your_openai_key
dd-license-attribution clean-spdx-id input.csv output.csv

# Or pass the API key directly
dd-license-attribution clean-spdx-id input.csv output.csv --api-key your_openai_key
```

**Using Anthropic Claude:**

```bash
export ANTHROPIC_API_KEY=your_anthropic_key
dd-license-attribution clean-spdx-id input.csv output.csv --llm-provider anthropic
```

**Options:**

- `--llm-provider`: Choose between `openai` (default) or `anthropic`
- `--api-key`: Your LLM provider API key (can also use `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` environment variables)
- `--model`: Specify a custom model (e.g., `gpt-4`, `gpt-3.5-turbo`, `claude-3-5-sonnet-20241022`)
- `--silent`: Run without prompting for confirmation (automatic mode)
- `--log-level`: Set logging level (DEBUG, INFO, WARNING, ERROR)

**Interactive Mode (Default):**

By default, the command runs in interactive mode, prompting you for each license conversion as it happens:

```bash
dd-license-attribution clean-spdx-id LICENSE-3rdparty.csv LICENSE-cleaned.csv --api-key your_key

# Output (for each conversion):
# INFO: Converting long license text to SPDX for component: jupyter-core
# 
# --- Proposed Change ---
# Component: jupyter-core
# Origin: https://github.com/jupyter/jupyter_core
# Original: BSD 3-Clause License\n\nCopyright (c) 2022, Jupyter...
# Converted to: BSD-3-Clause
# 
# Apply this change? [Y/n]:
# 
# (Repeats for each license that needs cleaning)
```

This allows you to review and approve/reject each conversion individually in real-time as the LLM processes each license.

**Silent Mode:**

For automated workflows, use `--silent` to apply changes without prompts:

```bash
dd-license-attribution clean-spdx-id LICENSE-3rdparty.csv LICENSE-cleaned.csv --api-key your_key --silent
```

**Complete Workflow Example:**

```bash
# Step 1: Generate SBOM
dd-license-attribution generate-sbom-csv https://github.com/owner/repo > LICENSE-3rdparty.csv

# Step 2: Clean up license identifiers with AI
dd-license-attribution clean-spdx-id LICENSE-3rdparty.csv LICENSE-cleaned.csv --api-key your_key

# Step 3: Review the cleaned output
cat LICENSE-cleaned.csv
```

**When to Use:**
- When you see long license text instead of SPDX identifiers (e.g., full MIT or BSD license text)
- After using `--deep-scanning` which may extract full license texts
- To standardize license identifiers across your SBOM

**Note:** The AI-based cleaning requires API access to OpenAI or Anthropic and will incur costs based on your usage. Review the changes in interactive mode before accepting them to ensure accuracy.

### Common Use Cases

#### Basic License Attribution
```bash
dd-license-attribution generate-sbom-csv https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Deep Scanning with Caching
```bash
dd-license-attribution generate-sbom-csv --deep-scanning --cache-dir ./cache https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Working with Private Repositories
```bash
export GITHUB_TOKEN=your_token
dd-license-attribution generate-sbom-csv https://github.com/owner/private-repo > LICENSE-3rdparty.csv
```

#### Using Mirror Repositories
```bash
# Create mirrors.json with your mirror configurations
dd-license-attribution generate-sbom-csv --use-mirrors=mirrors.json https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Interactive Override Generation
```bash
# Step 1: Generate initial SBOM
dd-license-attribution generate-sbom-csv https://github.com/owner/repo > LICENSE-3rdparty.csv

# Step 2: Fix entries with missing information interactively
dd-license-attribution generate-overrides LICENSE-3rdparty.csv

# Step 3: Regenerate with overrides
dd-license-attribution generate-sbom-csv --override-spec .ddla-overrides https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Cleaning License Identifiers
```bash
# Clean up long license descriptions and convert to SPDX identifiers
export OPENAI_API_KEY=your_key
dd-license-attribution clean-spdx-id LICENSE-3rdparty.csv LICENSE-cleaned.csv
```

### Development and Contributing

For instructions on how to develop or contribute to the project, read our [CONTRIBUTING.md guidelines](./CONTRIBUTING.md).

### Current Development State

- Initial set of dependencies is collected via github-sbom api, gopkg listing, and PyPI.
- Action packages are ignored.
- Python usage of PyPI metadata is limited to pure Python projects. If there are native dependencies or out-of-pypi requirements, failures are expected. The usage of the PyPI strategy can be disabled in those cases, but will reduce the coverage of the tool.
