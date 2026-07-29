# Datadog License Attribution Tracker

[![CI](https://github.com/DataDog/dd-license-attribution/actions/workflows/integration-test.yml/badge.svg)](https://github.com/DataDog/dd-license-attribution/actions/workflows/integration-test.yml)
[![Linters](https://github.com/DataDog/dd-license-attribution/actions/workflows/linters.yml/badge.svg)](https://github.com/DataDog/dd-license-attribution/actions/workflows/linters.yml)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/DataDog/dd-license-attribution/badge)](https://api.securityscorecards.dev/projects/github.com/DataDog/dd-license-attribution)
[![Coverage](https://img.shields.io/badge/coverage-90%25+-brightgreen)](https://github.com/DataDog/dd-license-attribution)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Imports: isort](https://img.shields.io/badge/%20imports-isort-%231674b1?style=flat&labelColor=ef8336)](https://pycqa.github.io/isort/)
[![Linting: ruff](https://img.shields.io/badge/linting-ruff-261230.svg)](https://github.com/astral-sh/ruff)
[![Type checker: mypy](https://img.shields.io/badge/type%20checker-mypy-blue.svg)](https://mypy-lang.org/)
[![Mutation testing: mutmut](https://img.shields.io/badge/mutation%20testing-mutmut-green.svg)](https://github.com/boxed/mutmut)

Datadog License Attribution Tracker is a tool that collects license and copyright information for third party dependencies of a project and returns a list of said dependencies and their licenses and copyright attributions, if found.

As of today, Datadog License Attribution Tracker supports Go, Python, NodeJS, and Rust projects. You can also pass a Go module path directly using the `--ecosystem go` option, an npm package name using `--ecosystem npm`, a PyPI package using `--ecosystem python` (or `--ecosystem pypi`), or a Rust crate using `--ecosystem rust`.

The tool collects license and other metadata information using multiple sources, including the GitHub API, pulled source code, package-manager output, and metadata collected from PyPI, NPM, Cargo, and crates.io.
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
dd-license-attribution generate-sbom https://github.com/owner/repo > LICENSE-3rdparty.csv
```
5. Or run on an npm package directly:
```bash
dd-license-attribution generate-sbom --ecosystem npm --no-gh-auth express > LICENSE-3rdparty.csv
```
6. Or run on a PyPI package directly:
```bash
dd-license-attribution generate-sbom --ecosystem python --no-gh-auth requests==2.31.0 > LICENSE-3rdparty.csv
```
7. Or run on a Go module directly:
```bash
dd-license-attribution generate-sbom --ecosystem go --no-gh-auth github.com/stretchr/testify@v1.9.0 > LICENSE-3rdparty.csv
```
8. Or run on a Rust crate directly:
```bash
dd-license-attribution generate-sbom --ecosystem rust --no-gh-auth serde@1.0 > LICENSE-3rdparty.csv
```

For more advanced usage, see the sections below.

### Available Commands

`dd-license-attribution` provides the following commands:

1. **`generate-sbom`** - Generate an SBOM of third-party dependencies as CSV, Markdown, or SPDX 2.3 JSON
2. **`generate-overrides`** - Interactively generate override configuration files
3. **`clean-spdx-id`** - Convert long license descriptions to valid SPDX license expressions using AI

`generate-sbom-csv` remains available as a deprecated alias for `generate-sbom --format csv`.

Run `dd-license-attribution --help` to see all available commands.

### Requirements

- python3.11+ - [Python install instructions](https://www.python.org/downloads/)
- libmagic (only on macOS):
  - `brew install libmagic`
- libicu (only on macOS):
  - `brew install icu4c pkg-config`
  - Add the following line to your `~/.zshrc` or `~/.bashrc`: `export PKG_CONFIG_PATH="$(brew --prefix icu4c)/lib/pkgconfig${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"`

#### Optional Requirements

- gopkg - [GoLang and GoPkg install instructions](https://go.dev/doc/install). Required for `--ecosystem go` and when using the GoPkg strategy (can be skipped with --no-gopkg-strategy)
- Node.js (v14 or newer) and npm (v7 or newer) - [Node.js install instructions](https://nodejs.org/en/download/). Not required when skipping the NPM strategy (--no-npm-strategy)
- Rust/Cargo and dd-rust-license-tool - install Rust from [rustup](https://rustup.rs/) or your system package manager, then run `cargo install dd-rust-license-tool`. Required for `--ecosystem rust` and when the Rust strategy is enabled against a Rust project (can be skipped with --no-rust-strategy). A `license-tool.toml` file in the target repository is honored automatically.

### Usage

#### Generating SBOM Reports

To install and run the command after cloning the repository:

```bash
#starting at the root of the repository
pip install .

# Optionally you can define a GITHUB_TOKEN, if used it will raise the throttling threashold and maspeed up your generation calls to github APIs.
export GITHUB_TOKEN=YOUR_TOKEN
dd-license-attribution generate-sbom https://github.com/owner/repo > LICENSE-3rdparty.csv

# Emit SPDX 2.3 JSON instead of CSV
dd-license-attribution generate-sbom https://github.com/owner/repo --format spdx > sbom.spdx.json

# Emit a Markdown license compliance report instead of CSV
dd-license-attribution generate-sbom https://github.com/owner/repo --format markdown > LICENSE-3rdparty.md

# Emit multiple formats from a single metadata collection run
dd-license-attribution generate-sbom https://github.com/owner/repo --format csv --format markdown --format spdx --output-dir ./reports
```

The following optional parameters are available for `generate-sbom`:

#### Scanning Options

##### Scope Control
- `--only-transitive-dependencies`: Extracts license and copyright from the passed package, only its dependencies.
- `--only-root-project`: Extracts information from the licenses and copyright of the passed package, not its dependencies.

##### Ecosystem Mode
- `--ecosystem <name>`: Treat the package argument as a package name in the given ecosystem instead of a GitHub repository URL. Supported ecosystems: `go`, `npm`, `python` (alias: `pypi`), `rust`. Both `python` and `pypi` are equivalent and produce identical output. Example: `--ecosystem go github.com/stretchr/testify@v1.9.0`, `--ecosystem npm express`, `--ecosystem python requests==2.31.0`, `--ecosystem pypi requests==2.31.0`, `--ecosystem rust serde@1.0`. Rust ecosystem mode uses Cargo to select the exact crate version, then analyzes that version's published crates.io source archive for both library and binary-only crates. A `Cargo.lock` included in the published archive is preserved for reproducible, release-specific attribution.

##### Strategy Selection
- `--deep-scanning`: Enables intensive source code analysis using [scancode-toolkit](https://scancode-toolkit.readthedocs.io/en/latest/getting-started/home.html). This will parse license and copyright information from full package source code. Note: This is a resource-intensive task that may take hours or days to process depending on package size.
- `--no-pypi-strategy`: Skips the strategy that collects dependencies from PyPI.
- `--no-gopkg-strategy`: Skips the strategy that collects dependencies from GoPkg.
- `--no-github-sbom-strategy`: Skips the strategy that gets the dependency tree from GitHub.
- `--no-npm-strategy`: Skips the strategy that collects dependencies from NPM.
- `--no-rust-strategy`: Skips the strategy that collects dependencies from Cargo projects using dd-rust-license-tool.
- `--no-scancode-strategy`: Skips the strategy that gets licenses and copyright attribution using ScanCode Toolkit.

##### Experimental Three-Phase Collection
- `--experimental-strategy`: Enables a three-phase collection pipeline that separates dependency discovery from metadata extraction.

  **Phase 0 — Pre-finders (once)**: Strategies that already perform full transitive closure run once on the root package only. For example, `GitHubSbomMetadataCollectionStrategy` queries GitHub's dependency graph API which already returns all transitive deps — re-running it on each discovered dependency would fetch unrelated dep trees.

  **Phase 1 — Finder fixpoint loop**: Ecosystem finders (PyPI, GoPkg, npm) run repeatedly (up to 5 iterations) until the dependency set stops growing. This ensures transitive dependencies discovered by one finder are seen by other finders in subsequent iterations.

  **Phase 2 — Enricher cascade**: Once the dependency set is stable, all metadata-enricher strategies run once to extract license and copyright information.

  **Ecosystem-aware defaults**: When `--experimental-strategy` is combined with `--ecosystem`, only the ecosystem-relevant finder is enabled by default. For example, `--experimental-strategy --ecosystem python` enables only the PyPI finder. All `--no-*` flags still apply and override these defaults.

  ```bash
  # Three-phase collection for a Python package — only PyPI finder runs in Phase 1
  dd-license-attribution generate-sbom --experimental-strategy --ecosystem python requests

  # Allow --no-* flags to further restrict strategies
  dd-license-attribution generate-sbom --experimental-strategy --ecosystem python --no-scancode-strategy requests
  ```

  > **Note**: This flag gates experimental behavior that is not yet stable. The strategy classification (pre-finder vs. finder vs. enricher) may change as the feature matures.

#### Output Options
- `--format <csv|spdx|markdown>`: Selects the SBOM output format. Defaults to `csv`. Repeat this option to request multiple formats in one run, for example `--format csv --format markdown --format spdx`.
- `--output-dir <path>`: Writes one file per requested format into the directory instead of writing the report to stdout. The directory is created if it does not exist. This option is required when passing multiple `--format` values. Generated file extensions are `.csv` for CSV, `.md` for Markdown, and `.json` for SPDX.

#### Cache Configuration

- `--cache-dir`: if a directory is passed to this parameter all the dependencies source code downloaded for analysis is kept in the directory and can be reused between runs. By default, nothing is reused between runs.
- `--cache-ttl`: seconds until cached data is considered expired, by default 1 day.

For more details about optional parameters pass `--help` to the command.

#### Output Formats

By default, `generate-sbom` writes a CSV report to stdout so it can be redirected to a file:

```bash
dd-license-attribution generate-sbom https://github.com/owner/repo > LICENSE-3rdparty.csv
```

CSV reports contain the following columns:
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

Markdown reports can be generated with `--format markdown`:

```bash
dd-license-attribution generate-sbom https://github.com/owner/repo --format markdown > LICENSE-3rdparty.md
```

Markdown reports include a root package summary followed by a third-party dependency table. The root package is summarized separately and excluded from the dependency table.

SPDX 2.3 JSON reports can be generated with `--format spdx`:

```bash
dd-license-attribution generate-sbom https://github.com/owner/repo --format spdx > sbom.spdx.json
```

To write more than one report format from the same metadata collection run, repeat `--format` and pass `--output-dir`:

```bash
dd-license-attribution generate-sbom https://github.com/owner/repo --format csv --format markdown --format spdx --output-dir ./reports
```

For a package such as `https://github.com/owner/repo`, this writes `github.com_owner_repo.csv`, `github.com_owner_repo.md`, and `github.com_owner_repo.json` under `./reports`.

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

Note: `original_url` is matched **case-sensitively against the repository's canonical URL**. Before applying mirrors, the tool resolves each scan target to its canonical GitHub `owner/name` (following renames/redirects and using the casing GitHub records for the owner and repository). An `original_url` whose casing differs from that canonical form will never match, so the mirror is silently ignored. Copy the `owner/name` exactly as GitHub displays it.

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
dd-license-attribution generate-sbom https://github.com/owner/repo > LICENSE-3rdparty.csv

# Interactively fix entries with missing information
dd-license-attribution generate-overrides LICENSE-3rdparty.csv

# Regenerate with overrides applied
dd-license-attribution generate-sbom https://github.com/owner/repo --override-spec .ddla-overrides > LICENSE-3rdparty.csv
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
dd-license-attribution generate-sbom --override-spec .ddla-overrides https://github.com/your-org/your-project
```

📖 **For complete documentation, examples, and best practices, see [Override Configuration Guide](docs/overrides.md)**

> **Recommendation**: When using overrides, consider creating a PR or feature request to improve `dd-license-attribution` or the target dependency to add missing information upstream. Overrides should ideally be a temporary measure.

#### Cleaning License Identifiers with AI

Sometimes the license information extracted by automated tools contains long license text instead of concise SPDX license expressions. For example, instead of "BSD-3-Clause", you might see the entire BSD license text. The `clean-spdx-id` command uses Large Language Models (LLMs) to intelligently convert these long descriptions into proper SPDX license expressions, including composite licenses (e.g., "MIT OR Apache-2.0").

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
- `--yes` / `-y`: Automatically confirm all prompts without asking for user confirmation
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

**Auto-Confirm Mode:**

For automated workflows, use `--yes` (or `-y`) to apply changes without prompts:

```bash
dd-license-attribution clean-spdx-id LICENSE-3rdparty.csv LICENSE-cleaned.csv --api-key your_key --yes
# Or use the short form:
dd-license-attribution clean-spdx-id LICENSE-3rdparty.csv LICENSE-cleaned.csv --api-key your_key -y
```

**Complete Workflow Example:**

```bash
# Step 1: Generate SBOM
dd-license-attribution generate-sbom https://github.com/owner/repo > LICENSE-3rdparty.csv

# Step 2: Clean up license identifiers with AI
dd-license-attribution clean-spdx-id LICENSE-3rdparty.csv LICENSE-cleaned.csv --api-key your_key

# Step 3: Review the cleaned output
cat LICENSE-cleaned.csv
```

**When to Use:**
- When you see long license text instead of SPDX license expressions (e.g., full MIT or BSD license text)
- After using `--deep-scanning` which may extract full license texts
- To standardize license expressions across your SBOM (including composite licenses like "MIT OR Apache-2.0")

**Note:** The AI-based cleaning requires API access to OpenAI or Anthropic and may incur costs based on your usage. Review the changes in interactive mode before accepting them to ensure accuracy.

### Common Use Cases

#### Basic License Attribution
```bash
dd-license-attribution generate-sbom https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Analyzing Go Packages by Module Path
```bash
# Analyze a Go module and its transitive dependencies
dd-license-attribution generate-sbom --ecosystem go --no-gh-auth github.com/DataDog/dd-trace-go/v2/ddtrace/tracer > LICENSE-3rdparty.csv

# Analyze a specific version of a Go module
dd-license-attribution generate-sbom --ecosystem go --no-gh-auth github.com/stretchr/testify@v1.9.0 > LICENSE-3rdparty.csv
```

#### Analyzing npm Packages by Name
```bash
# Analyze an npm package without needing a GitHub URL
dd-license-attribution generate-sbom --ecosystem npm --no-gh-auth express > LICENSE-3rdparty.csv

# Analyze a specific version of a scoped npm package
dd-license-attribution generate-sbom --ecosystem npm --no-gh-auth @datadog/browser-sdk@4.0.0 > LICENSE-3rdparty.csv
```

#### Analyzing PyPI Packages by Name
```bash
# Analyze a PyPI package without needing a GitHub URL
dd-license-attribution generate-sbom --ecosystem python --no-gh-auth requests > LICENSE-3rdparty.csv

# Analyze a specific version of a PyPI package
dd-license-attribution generate-sbom --ecosystem python --no-gh-auth "requests==2.31.0" > LICENSE-3rdparty.csv

# The 'pypi' alias also works
dd-license-attribution generate-sbom --ecosystem pypi --no-gh-auth Flask > LICENSE-3rdparty.csv
```

#### Analyzing Rust Crates by Name
```bash
# Analyze a Rust crate without needing a GitHub URL
dd-license-attribution generate-sbom --ecosystem rust --no-gh-auth serde > LICENSE-3rdparty.csv

# Analyze a specific Rust crate version
dd-license-attribution generate-sbom --ecosystem rust --no-gh-auth serde@1.0 > LICENSE-3rdparty.csv

# Binary-only crates use the same published-source analysis path
dd-license-attribution generate-sbom --ecosystem rust --no-gh-auth dd-rust-license-tool > LICENSE-3rdparty.csv
```

Direct Rust crate analysis uses a temporary Cargo project only to resolve the requested version. Dependency attribution runs from the exact source archive published on crates.io. If the crate declares a repository, a root `license-tool.toml` from that repository is applied to the published source before running `dd-rust-license-tool`.

For Rust repository scans, `dd-rust-license-tool` remains the primary metadata source. If Cargo or GitHub dependency data contains a confirmed crates.io dependency with missing fields, the tool fills only those gaps from the selected crates.io release and its published manifest. Existing license and copyright information is never overwritten. Some crates publish no author information; in that case, the repository URL is still supplied so the normal source-scanning strategies can continue attribution discovery.

#### Deep Scanning with Caching
```bash
dd-license-attribution generate-sbom --deep-scanning --cache-dir ./cache https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Working with Private Repositories
```bash
export GITHUB_TOKEN=your_token
dd-license-attribution generate-sbom https://github.com/owner/private-repo > LICENSE-3rdparty.csv
```

#### Using Mirror Repositories
```bash
# Create mirrors.json with your mirror configurations
dd-license-attribution generate-sbom --use-mirrors=mirrors.json https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Interactive Override Generation
```bash
# Step 1: Generate initial SBOM
dd-license-attribution generate-sbom https://github.com/owner/repo > LICENSE-3rdparty.csv

# Step 2: Fix entries with missing information interactively
dd-license-attribution generate-overrides LICENSE-3rdparty.csv

# Step 3: Regenerate with overrides
dd-license-attribution generate-sbom --override-spec .ddla-overrides https://github.com/owner/repo > LICENSE-3rdparty.csv
```

#### Cleaning License Identifiers
```bash
# Clean up long license descriptions and convert to SPDX license expressions
export OPENAI_API_KEY=your_key
dd-license-attribution clean-spdx-id LICENSE-3rdparty.csv LICENSE-cleaned.csv
```

## GitHub Action: Validate `LICENSE-3rdparty.csv`

This repository doubles as a reusable composite GitHub Action that regenerates a
third-party license SBOM and validates it against a committed
`LICENSE-3rdparty.csv` file. Use it in CI to fail a build whenever the committed
file drifts from what `dd-license-attribution` would produce.

The action sets up its own Python and, when their strategies or ecosystems
require them, Go, Node.js, and Rust toolchains. The Node.js setup also provides
npm and Yarn Classic; the Rust setup installs `dd-rust-license-tool`. It
installs the exact version of `dd-license-attribution` shipped with the `@ref`
you pin, so no additional setup steps are required. If your workflow already
provides any of these toolchains, opt out of the corresponding internal setup by
passing `python-version: false`, `go-version: false`, `node-version: false`, or
`rust-version: false`. When `compare` is enabled, your repository must be
checked out so the action can read the committed `LICENSE-3rdparty.csv`.

The action always assumes github.com as the host and takes the target as an
`owner/name` `repository` (defaulting to the repository the workflow runs in).
It builds its own mirror configuration internally and, when validating the
repository the workflow runs in, points that mirror at the branch actually
under test (the PR head branch for `pull_request` events, the merge-queue
branch, or the pushed branch) rather than the default branch. When a
`github-token` is provided, the action embeds it in the mirror so **private
repositories** can be cloned.

> **Authentication security caveat.** The action does not provide a GitHub token
> by default. Source-based dependency discovery may execute code controlled by
> the repository or package being scanned, and child processes may inherit the
> action environment. Leave `github-token` empty for public or untrusted targets.
> For a private repository, provide a read-only token only when you trust the
> target code that will be analyzed.

> **Checkout credential caveat.** `actions/checkout` persists its authentication
> header in the workspace's Git configuration by default. Git commands run by
> the scanner can inherit that header instead of using the action's mirror
> credentials. Set `persist-credentials: false` on the checkout step, as shown
> below, so the action's authentication behavior remains explicit.

> **`pull_request_target` security caveat.** The action intentionally does not
> map `pull_request_target` events to the PR head. Those workflows run in the
> base repository's security context and can expose a privileged token, while
> source-based dependency discovery may execute code from the repository being
> scanned. Mapping the mirror to an untrusted fork head could therefore leak the
> token. Use `pull_request` with read-only permissions to validate untrusted PR
> heads; on `pull_request_target`, the action scans the base/default branch.

> **Branch-under-test caveat.** The mirror only redirects the strategies that
> clone source code. The GitHub SBOM strategy (`github-sbom-strategy`, enabled
> by default) instead reads GitHub's dependency graph for the repository, which
> reflects its default/base branch — not the branch under test. If a pull
> request changes dependencies and you want that change validated, disable it
> with `github-sbom-strategy: false` so discovery is driven by the source-based
> strategies. The action also registers `github-token` as a masked secret so it
> is redacted from the job logs.

### Basic usage

```yaml
jobs:
  validate-licenses:
    runs-on: ubuntu-latest
    permissions:
      contents: read
    steps:
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
        with:
          persist-credentials: false
      # Pin to the full commit SHA of the release you want; `<sha>` is a
      # placeholder — see the repository's tags/releases.
      - uses: DataDog/dd-license-attribution@<sha>
```

### Inputs

| Input | Default | Description |
| --- | --- | --- |
| `repository` | `${{ github.repository }}` | GitHub repository to analyze, as `owner/name`. Ignored when `ecosystem` is set. Use GitHub's canonical `owner/name` casing — the auto-built mirror is matched case-sensitively against the canonical URL, so mismatched casing silently disables it. The default is already canonical. |
| `ecosystem` | _(empty)_ | Value for `--ecosystem` (`npm`, `python`, `pypi`, `go`, or `rust`). When set, `package` is analyzed instead of `repository` (and no mirror is built). |
| `package` | _(empty)_ | Package name to analyze. Only used (and required) when `ecosystem` is set. |
| `csv-path` | `LICENSE-3rdparty.csv` | Path (in the checked-out workspace) of the committed file to validate against. Required only when `compare` is `true`. |
| `override-spec` | _(empty)_ | Value for `--override-spec` (a JSON file of override rules). |
| `compare` | `true` | When `true`, the generated SBOM must match `csv-path` exactly (a unified diff is printed on mismatch). When `false`, only structural validation (non-empty CSV with the expected header) is performed. |
| `github-sbom-strategy` | `true` | Set to `false` to pass `--no-github-sbom-strategy`. |
| `gopkg-strategy` | `true` | Set to `false` to pass `--no-gopkg-strategy`. Go is still set up when `ecosystem` is `go`. |
| `pypi-strategy` | `true` | Set to `false` to pass `--no-pypi-strategy`. |
| `npm-strategy` | `true` | Set to `false` to pass `--no-npm-strategy`. Node.js, npm, and Yarn are still set up when `ecosystem` is `npm`. |
| `scancode-strategy` | `true` | Set to `false` to pass `--no-scancode-strategy`. |
| `rust-strategy` | `auto` | Controls Rust dependency analysis. `auto` enables Rust for `ecosystem: rust` and for checked-out repositories with a production `Cargo.toml`, while passing `--no-rust-strategy` for non-Rust repositories. Set to `true` to always install Rust and `dd-rust-license-tool`; set to `false` to always pass `--no-rust-strategy`. |
| `experimental-strategy` | `false` | Set to `true` to pass `--experimental-strategy`. |
| `deep-scanning` | `false` | Set to `true` to pass `--deep-scanning`. |
| `yarn-subdir` | _(empty)_ | Newline-separated subdirectory paths containing additional `yarn.lock` files. Each non-empty line is passed as a separate `--yarn-subdir` argument. |
| `default-branch` | `${{ github.event.repository.default_branch }}` | Default branch of `repository`, used as the source ref when the mirror is mapped onto the branch under test. Defaults to the default branch of the repository the workflow runs in. |
| `use-mirrors` | _(empty)_ | Path (in the workspace) to a JSON file of mirror specifications. Its entries are merged *ahead* of the auto-built mirror, so they take precedence for any overlapping `original_url` while the auto-built entry remains a fallback. In ecosystem mode it is passed verbatim to `--use-mirrors`. |
| `github-token` | _(empty)_ | Token used for GitHub API calls and, embedded in the mirror URL, for cloning the repository. Leave empty for public or untrusted targets; provide a read-only token for a trusted private repository. |
| `python-version` | `3.14` | Python version to set up and run the tool with. Set to `false` to skip the internal Python setup and use the `python` already on `PATH`. |
| `go-version` | `1.23` | Go version to set up when `gopkg-strategy` is enabled or `ecosystem` is `go`. Set to `false` to skip the internal Go setup and use the calling workflow's Go toolchain. |
| `node-version` | `24` | Node.js version to set up when `npm-strategy` is enabled or `ecosystem` is `npm`; npm and Yarn Classic are also installed. Set to `false` to use the calling workflow's JavaScript toolchain. |
| `rust-version` | `stable` | Rust toolchain to install when Rust crate resolution or analysis requires Cargo; `dd-rust-license-tool` is installed with Cargo when `rust-strategy` is enabled. Set to `false` to use the calling workflow's Rust toolchain and existing `dd-rust-license-tool` installation. |

### Outputs

| Output | Description |
| --- | --- |
| `sbom-path` | Absolute path to the generated SBOM file (useful for uploading as an artifact on failure). |
| `matches` | `true` when the generated SBOM matched `csv-path`. Only meaningful when `compare` is `true`. |

### Controlling strategies

Each collection strategy has a boolean input that defaults to enabled. Set one to
`false` to skip it:

```yaml
      # Pin to the full commit SHA of the release you want; `<sha>` is a
      # placeholder — see the repository's tags/releases.
      - uses: DataDog/dd-license-attribution@<sha>
        with:
          pypi-strategy: false
          scancode-strategy: false
```

For Yarn monorepos, pass each additional lockfile directory on a separate line:

```yaml
      - uses: DataDog/dd-license-attribution@<sha>
        with:
          yarn-subdir: |
            packages/frontend
            packages/admin
```

### Supplying custom mirrors

For special needs — for example mirroring a dependency's repository, or pointing
the target repository at an internal host — commit a mirror-specification JSON
file and pass its path via `use-mirrors`. Your entries are merged *ahead* of the
mirror the action builds automatically, so they win for any repository they
name, while the auto-built mirror still covers the primary repository as a
fallback. Each `original_url` must use GitHub's canonical
`owner/name` casing: the tool resolves scan targets to their canonical URL and
matches mirror entries case-sensitively, so a mismatched-casing entry is
silently ignored.

```yaml
      - uses: actions/checkout@9c091bb21b7c1c1d1991bb908d89e4e9dddfe3e0 # v7.0.0
        with:
          persist-credentials: false
      # Pin to the full commit SHA of the release you want; `<sha>` is a
      # placeholder — see the repository's tags/releases.
      - uses: DataDog/dd-license-attribution@<sha>
        with:
          use-mirrors: .github/ddla-mirrors.json
```

### Development and Contributing

For instructions on how to develop or contribute to the project, read our [CONTRIBUTING.md guidelines](./CONTRIBUTING.md).

### Current Development State

- Initial set of dependencies is collected via github-sbom api, gopkg listing, and PyPI.
- Action packages are ignored.
- Python usage of PyPI metadata is limited to pure Python projects. If there are native dependencies or out-of-pypi requirements, failures are expected. The usage of the PyPI strategy can be disabled in those cases, but will reduce the coverage of the tool.
