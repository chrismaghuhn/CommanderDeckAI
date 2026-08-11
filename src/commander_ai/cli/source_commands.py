"""Thin source command group; business behavior belongs to application use cases."""

from __future__ import annotations

from typing import cast

import typer

from commander_ai.application.errors import ApplicationError

from .composition import CliServices
from .rendering import render_error, render_result

app = typer.Typer(no_args_is_help=True)


@app.command("list")
def list_sources(
    ctx: typer.Context,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """List configured and assessment-only sources."""
    services = _services(ctx)
    try:
        render_result({"sources": services.source.list_sources()}, as_json=json_output)
    except ApplicationError as error:
        render_error(error, as_json=json_output)
        raise typer.Exit(code=error.exit_code) from None


@app.command("review")
def review_source(
    ctx: typer.Context,
    source: str,
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Show the local source-review status without acquiring data."""
    services = _services(ctx)
    try:
        render_result(services.source.review(source), as_json=json_output)
    except ApplicationError as error:
        render_error(error, as_json=json_output)
        raise typer.Exit(code=error.exit_code) from None


@app.command("sync")
def sync_source(
    ctx: typer.Context,
    source: str,
    config: str = typer.Option(..., "--config"),
    json_output: bool = typer.Option(False, "--json"),
) -> None:
    """Acquire one source through its reviewed registry and immutable snapshot store."""
    services = _services(ctx)
    try:
        render_result(services.source.sync(source, config), as_json=json_output)
    except ApplicationError as error:
        render_error(error, as_json=json_output)
        raise typer.Exit(code=error.exit_code) from None


def _services(ctx: typer.Context) -> CliServices:
    return cast(CliServices, ctx.find_root().obj)


__all__ = ["app"]
