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

### Step 1: Create the JSON File

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

### Step 2: Build Your Rules

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
