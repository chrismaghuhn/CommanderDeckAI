"""Thin data command group for normalization, validation, and reporting."""

from __future__ import annotations

from typing import cast

import typer

from commander_ai.application.errors import ApplicationError

from .composition import CliServices
from .rendering import render_error, render_result

app = typer.Typer(no_args_is_help=True)


@app.command("normalize")
def normalize(
    ctx: typer.Context,
    snapshot_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Normalize one verified, complete source snapshot."""
    try:
        render_result(_services(ctx).normalize.execute(snapshot_id), as_json=json_output)
    except ApplicationError as error:
        render_error(error, as_json=json_output)
        raise typer.Exit(code=error.exit_code) from None


@app.command("validate")
def validate(
    ctx: typer.Context,
    normalized_snapshot_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify one normalized-snapshot manifest and its bound artifacts."""
    try:
        render_result(_services(ctx).validate.execute(normalized_snapshot_id), as_json=json_output)
    except ApplicationError as error:
        render_error(error, as_json=json_output)
        raise typer.Exit(code=error.exit_code) from None


@app.command("report")
def report(
    ctx: typer.Context,
    source: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Write a quality report for one source or all sources."""
    try:
        render_result(_services(ctx).report.execute(source), as_json=json_output)
    except ApplicationError as error:
        render_error(error, as_json=json_output)
        raise typer.Exit(code=error.exit_code) from None


def _services(ctx: typer.Context) -> CliServices:
    return cast(CliServices, ctx.find_root().obj)


__all__ = ["app"]
