from __future__ import annotations

import platform
import sys

import typer

from commander_ai import __version__

app = typer.Typer(no_args_is_help=True)


@app.callback()
def main() -> None:
    """Commander Deck AI command-line interface."""


@app.command()
def doctor() -> None:
    """Print only local, non-secret environment diagnostics."""
    typer.echo(f"commander-deck-ai={__version__}")
    typer.echo(f"python={platform.python_version()}")
    typer.echo(f"executable={sys.executable}")
    typer.echo("status=foundation-ok")


if __name__ == "__main__":
    app()
