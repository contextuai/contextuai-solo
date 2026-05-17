"""Minimal click CLI starter — extend with new subcommands.

Run `python main.py --help` to list commands, or `python main.py hello --name=world`.
"""

import click


@click.group()
def cli():
    """Coder CLI starter."""


@cli.command()
@click.option("--name", default="world", help="Name to greet.")
def hello(name: str):
    """Say hello."""
    click.echo(f"Hello, {name}!")


if __name__ == "__main__":
    cli()
