import json
import pathlib
import sys

import click
import inquirer
from rauth.service import OAuth1Service

from .travel import create_journey, change_journey
from .renderer import build_site


@click.group(invoke_without_command=True)
@click.version_option()
def cli(*lol, **trololol):
    "Interact with the data fueling fernweh.rixx.de"
    if len(sys.argv) > 1:
        return
    inquirer.list_input(
        message="What do you want to do?",
        choices=(
            ("Plan or log a new journey", create_journey),
            ("Edit an existing journey", change_journey),
            ("Build the site", build_site),
        ),
        carousel=True,
    )()


@cli.command()
def build():
    """Build the site, putting output into _html/"""
    build_site()


@cli.command()
def new():
    """Add a new journey"""
    create_journey()


@cli.command()
def add():
    """Add a new journey"""
    create_journey()


@cli.command()
def edit():
    """Edit a journey"""
    change_journey()


@cli.command()
@click.option("--dry-run", "dry_run", default=False, type=bool, is_flag=True)
def social(dry_run):  # TODO
    from .social import post_next

    post_next(dry_run=dry_run)
