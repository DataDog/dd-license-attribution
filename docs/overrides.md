# Override Configuration Guide

When running dd-license-attribution on your project, you might encounter situations where the automatically detected license information is incorrect, incomplete, or includes unwanted dependencies. The override configuration file allows you to manually correct these issues by defining rules that modify the final dependency report.

## What You Can Do with Overrides

Override rules allow you to:

- **Fix incorrect license information** detected by automated tools
- **Add missing dependencies** that weren't automatically discovered
- **Remove false positives** (dependencies that shouldn't be included in your report)
- **Update copyright information** when the detected data is wrong
- **Handle proprietary or internal dependencies** with custom license information

## When to Use Overrides

Common scenarios where you'll want to create override rules:

- 📝 **Incorrect license detection**: A package shows "NOASSERTION" but you know it's MIT licensed
- ➕ **Missing dependencies**: Internal tools or bundled libraries not detected by package managers
- ❌ **Development-only dependencies**: Test frameworks or build tools that shouldn't appear in production SBOM
- 🏢 **Proprietary components**: Internal libraries that need custom license information
- 🔄 **Outdated information**: Package registry data doesn't match the actual license in the source code

## Three Types of Override Operations

### 1. ADD - Include Missing Dependencies
Use when dd-license-attribution missed a dependency that should be in your report.

**Example scenario**: You bundle a JavaScript library directly in your code, but it's not managed by npm.

### 2. REMOVE - Exclude Unwanted Dependencies
Use when dd-license-attribution detected something that shouldn't be in your final report.

**Example scenario**: A test framework appears in your production dependency list.

### 3. REPLACE - Fix Incorrect Information
Use when dd-license-attribution found a dependency but the license or copyright information is wrong.

**Example scenario**: A package shows "Unknown" license but you've verified it's actually Apache-2.0.

## How Override Rules Work

Each override rule works by:

1. **Matching**: You specify criteria to identify which dependency to modify (by name, origin URL, or both)
2. **Action**: You specify what to do (add, remove, or replace)
3. **Data**: For add/replace operations, you provide the correct dependency information

The rule only applies when ALL your matching criteria are met, ensuring precise targeting.

## Creating Your Override File

You have two options for creating override files:

### Option 1: Use the Interactive Command (Recommended) ⚡

The easiest way to create overrides is using the **interactive `generate-overrides` command**, which automatically analyzes your CSV file and prompts you to fix issues:

```bash
dd-license-attribution generate-overrides LICENSE-3rdparty.csv
```

This command will guide you through fixing problematic entries and generate a properly formatted override file. **[See full documentation below](#interactive-override-generation-with-generate-overrides)**.

### Option 2: Manually Create JSON File

If you prefer to write overrides manually, follow these steps:

#### Step 1: Create the JSON File

Create a new file (we recommend naming it `.ddla-overrides`) with a JSON array containing your override rules:

```json
[
  {
    "override_type": "replace",
    "target": {
      "component": "package-name"
    },
    "replacement": {
      "name": "package-name",
      "license": ["MIT"]
    }
  }
]
```

#### Step 2: Build Your Rules

Each rule in the array follows this structure:

### Rule Object Schema

```json
{
  "override_type": "add|remove|replace",
  "target": {
    "origin": "string (optional)",
    "component": "string (optional)"
  },
  "replacement": {
    "name": "string (optional)",
    "origin": "string (optional)",
    "version": "string (optional)",
    "license": ["string array (optional)"],
    "copyright": ["string array (optional)"]
  }
}
```

### Required Fields

#### `override_type` (required)
Tells dd-license-attribution what action to take:
- `"add"` - Add a new dependency to the report
- `"remove"` - Remove an existing dependency from the report
- `"replace"` - Update an existing dependency with new information

#### `target` (required)
Specifies which dependency to modify. You can use one or both criteria:
- `"component"` - Match by package name (e.g., "react", "numpy", "express")
- `"origin"` - Match by package source URL (e.g., "pkg:npm/react@18.0.0", "https://github.com/user/repo")

**Tip**: Use both `component` and `origin` for precise matching when you have multiple packages with similar names.

### Optional Fields

#### `replacement` (required for "add" and "replace")
The dependency information to add or replace with:
- `"name"` - Package name
- `"origin"` - Package source (URL or package manager identifier)
- `"version"` - Version number or commit hash
- `"license"` - Array of license identifiers (use [SPDX format](https://spdx.org/licenses/))
- `"copyright"` - Array of copyright holders

**Note**: For "remove" operations, don't include a `replacement` field.

## Usage Examples

### Example 1: Adding Missing Dependency

```json
[
  {
    "override_type": "add",
    "target": {
      "origin": "github.com/example/project"
    },
    "replacement": {
      "name": "missing-dependency",
      "origin": "pkg:npm/missing-dependency@1.0.0",
      "version": "1.0.0",
      "license": ["MIT"],
      "copyright": ["Copyright 2024 Example Corp"]
    }
  }
]
```

This rule adds a new dependency entry when processing any metadata that has an origin of "github.com/example/project".

### Example 2: Removing False Positive

```json
[
  {
    "override_type": "remove",
    "target": {
      "component": "test-only-package",
      "origin": "pkg:npm/test-only-package"
    }
  }
]
```

This rule removes any dependency that matches both the component name "test-only-package" AND the specified origin.

### Example 3: Correcting License Information

```json
[
  {
    "override_type": "replace",
    "target": {
      "origin": "pkg:npm/incorrect-license-package@1.2.3"
    },
    "replacement": {
      "name": "incorrect-license-package",
      "origin": "pkg:npm/incorrect-license-package@1.2.3",
      "version": "1.2.3",
      "license": ["Apache-2.0"],
      "copyright": ["Copyright 2024 Correct Owner"]
    }
  }
]
```

This rule replaces the entire metadata entry for a package with corrected license and copyright information.

### Example 4: Multiple Rules

```json
[
  {
    "override_type": "add",
    "target": {
      "origin": "github.com/company/main-repo"
    },
    "replacement": {
      "name": "internal-tool",
      "origin": "internal://tools/internal-tool",
      "version": "2.1.0",
      "license": ["Proprietary"],
      "copyright": ["Copyright 2024 Company Inc"]
    }
  },
  {
    "override_type": "remove",
    "target": {
      "component": "dev-dependency"
    }
  },
  {
    "override_type": "replace",
    "target": {
      "origin": "pkg:pypi/old-package@1.0.0"
    },
    "replacement": {
      "name": "old-package",
      "origin": "pkg:pypi/old-package@1.0.0",
      "version": "1.0.0",
      "license": ["BSD-3-Clause"],
      "copyright": ["Copyright 2024 New Maintainer"]
    }
  }
]
```

## Best Practices

### 1. Specific Targeting
Use both `origin` and `component` fields when possible to make rules as specific as possible and avoid unintended matches.

```json
{
  "target": {
    "origin": "pkg:npm/package-name@1.0.0",
    "component": "package-name"
  }
}
```

### 2. Complete Replacement Data
When using "replace" operations, provide complete metadata to avoid missing information:

```json
{
  "replacement": {
    "name": "package-name",
    "origin": "pkg:npm/package-name@1.0.0",
    "version": "1.0.0",
    "license": ["MIT"],
    "copyright": ["Copyright 2024 Author"]
  }
}
```

### 3. SPDX License Format
Use SPDX license identifiers for consistency:
- `"MIT"`
- `"Apache-2.0"`
- `"BSD-3-Clause"`
- `"GPL-3.0-or-later"`

### 4. Validation
Test your override configuration by running the tool and checking:
- That intended overrides are applied
- No unexpected matches occur
- All rules are used (unused rules may indicate configuration errors)

## Error Handling

The override strategy validates configuration and will raise errors for:

- Invalid override types (must be "add", "remove", or "replace")
- Invalid target fields (must be "origin" or "component")
- Missing replacement data for "add" or "replace" operations
- Invalid JSON syntax
- Missing configuration files

## Usage

### Using Override Rules

To use override rules with dd-license-attribution:

1. **Create an override configuration file** with your override rules (see examples above)
2. **Run dd-license-attribution with the `--override-spec` argument**:
   ```bash
   dd-license-attribution --override-spec path/to/your-overrides.json <repository-url>
   ```

### Example CLI Usage

```bash
# Using a custom override file
dd-license-attribution --override-spec ./my-overrides.json https://github.com/user/repo

# Using the conventional .ddla-overrides file
dd-license-attribution --override-spec ./.ddla-overrides https://github.com/user/repo
```

### Best Practice: Commit Override Files to Your Repository

It's recommended to commit your override configuration file to your project repository for:
- **Version control**: Track changes to override rules over time
- **Team consistency**: Ensure all team members use the same overrides
- **CI/CD integration**: Automated builds use consistent override rules
- **Documentation**: Override rules serve as documentation of known licensing issues

**Recommended filename**: `.ddla-overrides` (following the conventional dotfile pattern)

**Example**: See the [dd-license-attribution project's own override file](https://github.com/DataDog/dd-license-attribution/blob/main/.ddla-overrides) for a real-world example.

Place the file in your project root:
```
your-project/
├── .ddla-overrides          # Your override rules
├── .gitignore
├── README.md
└── src/
```

Then reference it in your CI/CD pipeline or documentation:
```bash
dd-license-attribution --override-spec ./.ddla-overrides https://github.com/your-org/your-project
```

## Monitoring Unused Rules

The `OverrideCollectionStrategy` tracks unused rules through the `unused_targets()` method. This helps identify:

- Rules that don't match any metadata (possibly due to typos or outdated configurations)
- Rules that may no longer be necessary
- Potential issues with target matching criteria

Monitor unused rules in your pipeline to maintain an effective override configuration.

## Interactive Override Generation with `generate-overrides`

Creating override rules manually can be tedious and error-prone. The `generate-overrides` command provides an **interactive wizard** that helps you quickly generate override files from existing CSV reports.

### What is `generate-overrides`?

The `generate-overrides` command is an interactive tool that:

1. **Analyzes** your LICENSE-3rdparty.csv file
2. **Identifies** entries with missing or incomplete license/copyright information
3. **Prompts** you interactively to provide the correct information
4. **Generates** a properly formatted override JSON file

This eliminates the need to manually write JSON and reduces the chance of syntax errors.

### When to Use `generate-overrides`

Use this command when:

- 📊 You've already generated a LICENSE-3rdparty.csv and noticed entries with missing data
- 🔄 You want to quickly fix multiple entries with missing license or copyright information
- ⚡ You need to create overrides but don't want to write JSON manually
- ✅ You want to ensure your override file is correctly formatted

### Basic Usage

```bash
dd-license-attribution generate-overrides LICENSE-3rdparty.csv
```

This will:
1. Scan the CSV file for entries with empty license or copyright fields
2. Prompt you interactively for each problematic entry
3. Generate `.ddla-overrides` file in the current directory

### Command Options

#### Output File Location

Specify a custom output file:

```bash
dd-license-attribution generate-overrides LICENSE-3rdparty.csv --output my-overrides.json
```

#### Filter by License Issues Only

Only check for entries with missing license information:

```bash
dd-license-attribution generate-overrides LICENSE-3rdparty.csv --only-license
```

This will skip entries that only have missing copyright (but have a license).

#### Filter by Copyright Issues Only

Only check for entries with missing copyright information:

```bash
dd-license-attribution generate-overrides LICENSE-3rdparty.csv --only-copyright
```

This will skip entries that only have missing license (but have copyright).

### Interactive Workflow

When you run the command, you'll see an interactive prompt for each problematic entry:

```
Found 3 entries with missing license or copyright information.

Component: test-package-1
Origin: https://github.com/test/package1
Current License: ['MIT']
Current Copyright: (empty)

Do you want to fix this entry? [Y/n]: y

Enter the corrected information:
(Press Enter to keep the current value)
Origin [https://github.com/test/package1]:
License(s) (comma-separated) [current: MIT]:
Copyright holder(s) (comma-separated): Copyright 2024 Test Corp
✓ Override rule created.
```

#### Interactive Features

1. **Skip Entries**: Answer `n` to skip entries you don't want to fix
2. **Keep Existing Values**: Press Enter without typing to keep the current value (for fields that already have data)
3. **Multiple Values**: Provide comma-separated values for multiple licenses or copyright holders
4. **Current Value Display**: The tool shows current values in brackets to help you decide

### Usage Examples

#### Example 1: Fix All Missing Information

```bash
dd-license-attribution generate-overrides LICENSE-3rdparty.csv
```

The tool will prompt you for every entry that's missing either license or copyright information.

#### Example 2: Only Fix Missing Licenses

```bash
dd-license-attribution generate-overrides LICENSE-3rdparty.csv --only-license -o license-fixes.json
```

Use this when you want to focus specifically on license information and ignore copyright issues.

#### Example 3: Only Fix Missing Copyright

```bash
dd-license-attribution generate-overrides LICENSE-3rdparty.csv --only-copyright
```

Use this when licenses are correct but copyright information needs to be added.

#### Example 4: Keep Existing Values

When prompted:
```
License(s) (comma-separated) [current: MIT]: [Press Enter]
```

Simply press Enter to keep "MIT" as the license. This is useful when only one field needs to be updated.

### Generated Override File

The command generates a JSON file with proper override rules:

```json
[
  {
    "override_type": "replace",
    "target": {
      "component": "test-package-1",
      "origin": "https://github.com/test/package1"
    },
    "replacement": {
      "name": "test-package-1",
      "origin": "https://github.com/test/package1",
      "license": ["MIT"],
      "copyright": ["Copyright 2024 Test Corp"]
    }
  }
]
```

You can then use this file with the main generation command:

```bash
dd-license-attribution generate-sbom-csv https://github.com/user/repo --override-spec .ddla-overrides
```

### Tips for Using `generate-overrides`

1. **Run After Initial Scan**: First generate your CSV report, then use `generate-overrides` to fix issues

2. **Use Filters for Large Files**: If you have many entries, use `--only-license` or `--only-copyright` to focus on specific issues

3. **Commit the Generated File**: Add the generated override file to version control so your team uses the same overrides

4. **Iterative Approach**: You can run the command multiple times with different filters to tackle issues incrementally

5. **Combine with Manual Edits**: The generated file is JSON, so you can manually edit it if needed after generation

### Typical Workflow

A typical workflow might look like:

```bash
# Step 1: Generate initial SBOM
dd-license-attribution generate-sbom-csv https://github.com/user/repo > LICENSE-3rdparty.csv

# Step 2: Generate overrides interactively
dd-license-attribution generate-overrides LICENSE-3rdparty.csv

# Step 3: Regenerate SBOM with overrides
dd-license-attribution generate-sbom-csv https://github.com/user/repo --override-spec .ddla-overrides > LICENSE-3rdparty.csv

# Step 4: Commit both files
git add LICENSE-3rdparty.csv .ddla-overrides
git commit -m "Update license attribution with overrides"
```
