"""Thin dataset command group for build and verified inspection."""

from __future__ import annotations

from typing import cast

import typer

from commander_ai.application.errors import ApplicationError

from .composition import CliServices
from .rendering import render_error, render_result

app = typer.Typer(no_args_is_help=True)


@app.command("build")
def build(
    ctx: typer.Context,
    config: str = typer.Option(..., "--config"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Build one task-specific dataset from a strict dataset configuration."""
    try:
        render_result(_services(ctx).build_dataset.execute(config), as_json=json_output)
    except ApplicationError as error:
        render_error(error, as_json=json_output)
        raise typer.Exit(code=error.exit_code) from None


@app.command("inspect")
def inspect(
    ctx: typer.Context,
    dataset_id: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Verify and summarize one immutable task-specific dataset."""
    try:
        render_result(_services(ctx).inspect_dataset.execute(dataset_id), as_json=json_output)
    except ApplicationError as error:
        render_error(error, as_json=json_output)
        raise typer.Exit(code=error.exit_code) from None


def _services(ctx: typer.Context) -> CliServices:
    return cast(CliServices, ctx.find_root().obj)


__all__ = ["app"]
