# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2025-present Datadog, Inc.

# Command for generating override configuration files

from collections.abc import Callable
from typing import Annotated

import typer

from dd_license_attribution.adaptors.os import write_file
from dd_license_attribution.metadata_collector.metadata import Metadata
from dd_license_attribution.metadata_collector.strategies.license_3rdparty_metadata_collection_strategy import (  # noqa: E501
    License3rdPartyMetadataCollectionStrategy,
)
from dd_license_attribution.metadata_collector.strategies.override_strategy import (  # noqa: E501
    OverrideRule,
    OverrideTargetField,
    OverrideType,
)
from dd_license_attribution.overrides_generator.overrides_generator import (
    OverridesGenerator,
)
from dd_license_attribution.overrides_generator.writers.json_overrides_writer import (  # noqa: E501
    JSONOverridesWriter,
)
from dd_license_attribution.utils.custom_splitting import CustomSplit


def only_license_or_copyright_callback() -> (
    Callable[[typer.Context, typer.CallbackParam, bool], bool | None]
):
    """
    Callback to ensure --only-license and --only-copyright are mutually
    exclusive.
    """
    group = set()

    def callback(
        ctx: typer.Context, param: typer.CallbackParam, value: bool
    ) -> bool | None:
        # Add cli option to group if it was called with a value
        if (
            value is True
            and param.name not in group
            and (param.name == "only_license" or param.name == "only_copyright")
        ):
            group.add(param.name)

        if len(group) == 2:
            raise typer.BadParameter(
                "Cannot specify both --only-license and --only-copyright"
            )

        return value

    return callback


only_license_or_copyright_exclusive = only_license_or_copyright_callback()


def generate_overrides(
    csv_file: Annotated[
        str,
        typer.Argument(
            help=(
                "Path to the LICENSE-3rdparty.csv file to analyze for "
                "missing license or copyright information."
            )
        ),
    ],
    output_file: Annotated[
        str,
        typer.Option(
            "--output",
            "-o",
            help=(
                "Path to the output JSON file for overrides. "
                "Default is .ddla-overrides"
            ),
        ),
    ] = ".ddla-overrides",
    only_license: Annotated[
        bool,
        typer.Option(
            "--only-license",
            help=("Only check for entries with missing license information."),
            callback=only_license_or_copyright_exclusive,
        ),
    ] = False,
    only_copyright: Annotated[
        bool,
        typer.Option(
            "--only-copyright",
            help=("Only check for entries with missing copyright information."),
            callback=only_license_or_copyright_exclusive,
        ),
    ] = False,
) -> None:
    """
    Generate an override configuration file from a LICENSE-3rdparty.csv file.

    This command analyzes a LICENSE-3rdparty.csv file and prompts the user to fix entries with
    empty license or copyright information, generating a valid .ddla-overrides JSON file.
    """
    try:
        strategy = License3rdPartyMetadataCollectionStrategy(csv_file)
        metadata_list = strategy.augment_metadata([])
    except FileNotFoundError:
        typer.echo(f"Error: File '{csv_file}' not found.", err=True)
        raise typer.Exit(code=1)
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1)
    except Exception as e:
        typer.echo(f"Error reading CSV file: {e}", err=True)
        raise typer.Exit(code=1)

    if not metadata_list:
        typer.echo("Error: CSV file is empty.", err=True)
        raise typer.Exit(code=1)

    # Find entries with empty license or copyright
    problematic_entries = []
    for meta in metadata_list:
        is_problematic = False
        if only_license:
            if not meta.license:
                is_problematic = True
        elif only_copyright:
            if not meta.copyright:
                is_problematic = True
        else:
            if not meta.license or not meta.copyright:
                is_problematic = True

        if is_problematic:
            problematic_entries.append(meta)

    if not problematic_entries:
        typer.echo("No entries with missing license or copyright information found.")
        return

    num_entries = len(problematic_entries)
    typer.echo(
        f"Found {num_entries} entries with missing license or "
        f"copyright information.\n"
    )

    # Collect override rules from user input
    override_rules = []
    splitter = CustomSplit()
    for entry in problematic_entries:
        typer.echo(f"Component: {entry.name}")
        typer.echo(f"Origin: {entry.origin}")
        license_display = entry.license if entry.license else "(empty)"
        typer.echo(f"Current License: {license_display}")
        copyright_display = entry.copyright if entry.copyright else "(empty)"
        typer.echo(f"Current Copyright: {copyright_display}")

        # Ask if user wants to fix this entry
        fix_it = typer.confirm("\nDo you want to fix this entry?", default=True)

        if not fix_it:
            typer.echo("Skipping...\n")
            continue

        # Collect the new values
        typer.echo("\nEnter the corrected information:")
        typer.echo("(Press Enter to keep the current value)")

        # Ask for origin (show current value as default)
        new_origin = typer.prompt(
            "Origin", default=entry.origin if entry.origin else ""
        )

        license_prompt = "License(s) (comma-separated, use quotes to preserve commas)"
        current_licenses = ", ".join(entry.license)
        license_prompt += f" [current: {current_licenses}]"
        license_input = typer.prompt(license_prompt, default="")
        # If user pressed Enter (empty input), keep current value
        if not license_input.strip():
            new_licenses = entry.license
        else:
            new_licenses = splitter.custom_split(license_input)

        copyright_prompt = (
            "Copyright holder(s) (comma-separated, use quotes to preserve commas)"
        )
        current_copyrights = ", ".join(entry.copyright)
        copyright_prompt += f" [current: {current_copyrights}]"
        copyright_input = typer.prompt(copyright_prompt, default="")
        # If user pressed Enter (empty input), keep current value
        if not copyright_input.strip():
            new_copyrights = entry.copyright
        else:
            new_copyrights = splitter.custom_split(copyright_input)

        # Create the override rule using the existing OverrideRule structure
        # Build the target dictionary with OverrideTargetField keys
        target: dict[OverrideTargetField, str] = {
            OverrideTargetField.COMPONENT: str(entry.name),
            OverrideTargetField.ORIGIN: str(entry.origin),
        }

        # Create the replacement Metadata object
        replacement = Metadata(
            name=entry.name,
            origin=new_origin,
            version=entry.version,
            local_src_path=None,
            license=new_licenses,
            copyright=new_copyrights,
        )

        override_rule = OverrideRule(
            override_type=OverrideType.REPLACE,
            target=target,
            replacement=replacement,
        )

        override_rules.append(override_rule)
        typer.echo("✓ Override rule created.\n")

    # Generate the override rules JSON using the generator
    if override_rules:
        try:
            json_writer = JSONOverridesWriter()
            generator = OverridesGenerator(json_writer)
            json_output = generator.generate_overrides(override_rules)

            # Write the JSON string to the output file
            write_file(output_file, json_output)

            num_rules = len(override_rules)
            typer.echo(
                f"\n✓ Successfully created override file: {output_file} "
                f"with {num_rules} rule(s)."
            )
        except Exception as e:
            typer.echo(f"Error writing override file: {e}", err=True)
            raise typer.Exit(code=1)
    else:
        typer.echo("\nNo override rules were created.")
