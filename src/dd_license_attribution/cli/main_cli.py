# SPDX-License-Identifier: Apache-2.0
#
# Unless explicitly stated otherwise all files in this repository are licensed under the Apache License Version 2.0.
#
# This product includes software developed at Datadog (https://www.datadoghq.com/).
# Copyright 2024-present Datadog, Inc.

# Main entry point for the dd-license-attribution CLI tool

import typer

from dd_license_attribution.cli.generate_overrides_command import (
    generate_overrides,
)
from dd_license_attribution.cli.generate_sbom_csv_command import (
    generate_sbom_csv,
)

app = typer.Typer(add_completion=False)
app.command()(generate_sbom_csv)
app.command()(generate_overrides)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        ctx.exit(2)


if __name__ == "__main__":
    app()
