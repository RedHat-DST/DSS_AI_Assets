"""
LinkedIn Sales Navigator CLI.

Usage:
    python -m src.cli auth              # Open Chrome, sign in to Sales Navigator
    python -m src.cli whoami            # Show current LinkedIn user
    python -m src.cli leads "VP Sales"  # Search leads
    python -m src.cli companies "Red Hat"  # Search companies
    python -m src.cli auth_status       # Session + Chrome CDP status
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Optional

import click

from .auth import AuthRequired, get_auth
from .linkedin import SessionExpired
from .ops import (
    get_company,
    get_profile,
    get_saved_list,
    list_saved_lists,
    search_companies,
    search_from_url,
    search_leads,
    whoami,
)


def _run(coro):
    return asyncio.run(coro)


def _print(payload) -> None:
    click.echo(json.dumps(payload, indent=2, default=str))


def _die_auth(err: Exception) -> None:
    click.echo(click.style(str(err), fg="yellow"))
    sys.exit(2)


@click.group()
def cli():
    """LinkedIn Sales Navigator assistant (Voyager API via Chrome session)."""


@cli.command("auth")
@click.option("--wait/--no-wait", default=True, help="Wait until Sales Navigator is visible")
@click.option("--force", is_flag=True, help="Ignore saved session and re-harvest from Chrome")
def auth_cmd(wait: bool, force: bool):
    """Open Chrome and harvest a LinkedIn session after login."""
    auth = get_auth()
    try:
        session = _run(auth.authenticate(force_login=force, wait=wait))
    except AuthRequired as e:
        _die_auth(e)
    click.echo(click.style("Authenticated", fg="green", bold=True))
    _print(
        {
            "name": session.get("name"),
            "public_id": session.get("public_id"),
            "profile_url": session.get("profile_url"),
            "has_sales_nav_cookie": bool((session.get("cookies") or {}).get("li_a")),
        }
    )


@cli.command("auth_status")
def auth_status():
    """Show saved session and whether Chrome CDP is alive."""
    auth = get_auth()
    _print(auth.status_dict())


@cli.command("import-cookies")
@click.argument("cookie_file", type=click.Path(exists=True, dir_okay=False))
def import_cookies_cmd(cookie_file: str):
    """Import cookies from a Cookie-Editor JSON file."""
    auth = get_auth()
    raw = open(cookie_file, encoding="utf-8").read()
    try:
        session = _run(auth.import_cookies(raw))
    except Exception as e:
        click.echo(click.style(str(e), fg="red"))
        sys.exit(1)
    click.echo(click.style("Cookies imported", fg="green", bold=True))
    _print(
        {
            "name": session.get("name"),
            "public_id": session.get("public_id"),
            "has_sales_nav_cookie": bool((session.get("cookies") or {}).get("li_a")),
        }
    )


@cli.command("whoami")
def whoami_cmd():
    """Show the authenticated LinkedIn user."""
    try:
        _print(_run(whoami()))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("leads")
@click.argument("keywords")
@click.option("--start", default=0, show_default=True)
@click.option("--limit", default=25, show_default=True)
def leads_cmd(keywords: str, start: int, limit: int):
    """Search Sales Navigator leads."""
    try:
        _print(_run(search_leads(keywords, start=start, limit=limit)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("companies")
@click.argument("keywords")
@click.option("--start", default=0, show_default=True)
@click.option("--limit", default=25, show_default=True)
def companies_cmd(keywords: str, start: int, limit: int):
    """Search Sales Navigator companies."""
    try:
        _print(_run(search_companies(keywords, start=start, limit=limit)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("profile")
@click.argument("profile_ref")
def profile_cmd(profile_ref: str):
    """Get a lead profile."""
    try:
        _print(_run(get_profile(profile_ref)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("company")
@click.argument("company_ref")
def company_cmd(company_ref: str):
    """Get a company profile."""
    try:
        _print(_run(get_company(company_ref)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("lists")
@click.option("--type", "list_type", default="people", type=click.Choice(["people", "company"]))
def lists_cmd(list_type: str):
    """List saved Sales Navigator lists."""
    try:
        _print(_run(list_saved_lists(list_type)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("list")
@click.argument("list_id")
@click.option("--type", "list_type", default="people", type=click.Choice(["people", "company"]))
@click.option("--start", default=0, show_default=True)
@click.option("--limit", default=25, show_default=True)
def list_cmd(list_id: str, list_type: str, start: int, limit: int):
    """Get items from a saved list."""
    try:
        _print(_run(get_saved_list(list_id, list_type, start=start, limit=limit)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("url")
@click.argument("search_url")
@click.option("--start", default=0, show_default=True)
@click.option("--limit", default=25, show_default=True)
def url_cmd(search_url: str, start: int, limit: int):
    """Run a search from a Sales Navigator URL."""
    try:
        _print(_run(search_from_url(search_url, start=start, limit=limit)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


if __name__ == "__main__":
    cli()
