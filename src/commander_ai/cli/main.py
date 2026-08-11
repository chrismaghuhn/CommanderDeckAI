from __future__ import annotations

import platform
import sys

import typer

from commander_ai import __version__

from .composition import build_default_services
from .data_commands import app as data_app
from .dataset_commands import app as dataset_app
from .source_commands import app as source_app

app = typer.Typer(no_args_is_help=True)
app.add_typer(source_app, name="source")
app.add_typer(data_app, name="data")
app.add_typer(dataset_app, name="dataset")


@app.callback()
def main(ctx: typer.Context) -> None:
    """Commander Deck AI command-line interface."""
    if ctx.obj is None:
        ctx.obj = build_default_services()


@app.command()
def doctor() -> None:
    """Print only local, non-secret environment diagnostics."""
    typer.echo(f"commander-deck-ai={__version__}")
    typer.echo(f"python={platform.python_version()}")
    typer.echo(f"executable={sys.executable}")
    typer.echo("status=foundation-ok")


if __name__ == "__main__":
    app()
