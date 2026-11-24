"""
Red Hat Shadowbot CLI (Sales Assistant).

Usage:
    python -m src.cli auth                 # Open Chrome, complete SSO + FreeOTP
    python -m src.cli whoami               # Show current associate
    python -m src.cli ask "Catch me up on account Microsoft"
    python -m src.cli ask "..." --thread THREAD_ID
    python -m src.cli threads
    python -m src.cli history THREAD_ID
    python -m src.cli auth_status
"""

from __future__ import annotations

import asyncio
import json
import sys
from typing import Optional

import click

from .auth import AuthRequired, get_auth
from .langgraph import SessionExpired
from .ops import ask, get_thread, list_threads, whoami


def _run(coro):
    return asyncio.run(coro)


def _print(payload) -> None:
    click.echo(json.dumps(payload, indent=2, default=str, ensure_ascii=False))


def _die_auth(err: Exception) -> None:
    click.echo(click.style(str(err), fg="yellow"))
    sys.exit(2)


@click.group()
def cli():
    """Red Hat Shadowbot assistant (LangGraph via SSO Chrome session)."""


@cli.command("auth")
@click.option("--wait/--no-wait", default=True, help="Wait until Sales Assistant is visible after SSO/FreeOTP")
@click.option("--force", is_flag=True, help="Ignore saved session and re-harvest from Chrome")
def auth_cmd(wait: bool, force: bool):
    """Open Chrome and harvest a Keycloak session after SSO + FreeOTP."""
    auth = get_auth()
    try:
        session = _run(auth.authenticate(force_login=force, wait=wait))
    except AuthRequired as e:
        _die_auth(e)
    click.echo(click.style("Authenticated", fg="green", bold=True))
    _print(
        {
            "email": session.get("email"),
            "name": session.get("name"),
            "preferred_username": session.get("preferred_username"),
            "assistant_id": session.get("assistant_id"),
        }
    )


@cli.command("auth_status")
def auth_status():
    """Show saved session and whether Chrome CDP is alive."""
    _print(get_auth().status_dict())


@cli.command("whoami")
def whoami_cmd():
    """Show the signed-in associate."""
    try:
        _print(_run(whoami()))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("ask")
@click.argument("prompt")
@click.option("--thread", "thread_id", help="Continue this conversation thread")
@click.option("--new", "new_thread", is_flag=True, help="Start a new conversation")
def ask_cmd(prompt: str, thread_id: Optional[str], new_thread: bool):
    """Prompt Sales Assistant and print the reply."""
    try:
        _print(_run(ask(prompt, thread_id=thread_id, new_thread=new_thread)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("threads")
@click.option("--limit", default=20, show_default=True, type=int)
def threads_cmd(limit: int):
    """List recent Sales Assistant threads."""
    try:
        _print(_run(list_threads(limit=limit)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


@cli.command("history")
@click.argument("thread_id")
@click.option("--limit", default=50, show_default=True, type=int)
def history_cmd(thread_id: str, limit: int):
    """Show messages in a thread."""
    try:
        _print(_run(get_thread(thread_id, limit=limit)))
    except (AuthRequired, SessionExpired) as e:
        _die_auth(e)


if __name__ == "__main__":
    cli()
