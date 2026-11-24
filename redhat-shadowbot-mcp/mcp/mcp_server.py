#!/usr/bin/env python3
"""
Red Hat Shadowbot MCP Server (Sales Assistant).

Exposes the internal Sales Assistant agent at
https://shadowbot.io.redhat.com/agents/sales-assistant to Cursor via the
Model Context Protocol, matching the Gmail / Drive / Calendar / Slack /
Sales Cloud assistants.

Authentication is not OAuth. The signed-in user is a Red Hat associate.
Shadowbot sits behind associate SSO (auth.redhat.com) and FreeOTP. Tools
harvest that associate's Keycloak token from a persistent Chrome window
and call the LangGraph API. When kicked out, call shadowbot_auth and
complete associate SSO + FreeOTP in that window.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).parent
sys.path.insert(0, str(PROJECT_ROOT))

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from src.auth import AUTH_INSTRUCTIONS, AuthRequired, get_auth
from src.langgraph import SessionExpired
from src.ops import ask, get_thread, list_threads, to_text, whoami

server = Server("shadowbot-assistant")


def _ok(payload: Any) -> list[TextContent]:
    return [TextContent(type="text", text=to_text(payload) if not isinstance(payload, str) else payload)]


def _err(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=message)]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="shadowbot_auth",
            description=(
                "Open or reconnect the persistent Chrome window so the Red Hat associate "
                "can sign into Shadowbot Sales Assistant (shadowbot.io.redhat.com). Use "
                "before the first request and whenever Shadowbot returns a session error. "
                "The associate completes Red Hat SSO (auth.redhat.com) and FreeOTP in "
                "Chrome — never collect a password or OTP in chat. Chrome stays open so "
                "later logins are faster. Set wait=true to block until Sales Assistant loads."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "wait": {
                        "type": "boolean",
                        "description": "Wait until Sales Assistant is visible after SSO/FreeOTP (default: true)",
                        "default": True,
                    },
                    "force": {
                        "type": "boolean",
                        "description": "Ignore the saved session and re-harvest from Chrome",
                        "default": False,
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="shadowbot_whoami",
            description="Show the signed-in Red Hat associate and whether the Chrome SSO session is alive.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="shadowbot_ask",
            description=(
                "Prompt Red Hat Sales Assistant (Shadowbot) and return its reply. "
                "Call this directly for the user's question — do not call whoami, "
                "list_threads, or auth first unless a previous tool said the session "
                "expired. Omit thread_id to continue the last conversation; set "
                "new_thread=true to start a fresh chat."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "prompt": {
                        "type": "string",
                        "description": "Message to send to Sales Assistant",
                    },
                    "thread_id": {
                        "type": "string",
                        "description": "Existing conversation thread to continue",
                    },
                    "new_thread": {
                        "type": "boolean",
                        "description": "Start a new conversation (default: false)",
                        "default": False,
                    },
                },
                "required": ["prompt"],
            },
        ),
        Tool(
            name="shadowbot_list_threads",
            description="List recent Sales Assistant conversation threads for the signed-in associate.",
            inputSchema={
                "type": "object",
                "properties": {
                    "limit": {
                        "type": "integer",
                        "description": "Max threads (default: 20)",
                        "default": 20,
                    }
                },
                "required": [],
            },
        ),
        Tool(
            name="shadowbot_get_thread",
            description="Read messages in a Sales Assistant thread (from shadowbot_ask or shadowbot_list_threads).",
            inputSchema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string", "description": "LangGraph thread id"},
                    "limit": {
                        "type": "integer",
                        "description": "Max messages (default: 50)",
                        "default": 50,
                    },
                },
                "required": ["thread_id"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "shadowbot_auth":
            return await handle_auth(args)
        if name == "shadowbot_whoami":
            return await handle_whoami()
        if name == "shadowbot_ask":
            return _ok(
                await ask(
                    args["prompt"],
                    thread_id=args.get("thread_id"),
                    new_thread=args.get("new_thread", False),
                )
            )
        if name == "shadowbot_list_threads":
            return _ok(await list_threads(limit=args.get("limit", 20)))
        if name == "shadowbot_get_thread":
            return _ok(await get_thread(args["thread_id"], limit=args.get("limit", 50)))
        return _err(f"Unknown tool: {name}")
    except (AuthRequired, SessionExpired) as e:
        return _err(str(e) or AUTH_INSTRUCTIONS)
    except Exception as e:
        return _err(f"Error: {e}")


async def handle_auth(args: dict) -> list[TextContent]:
    auth = get_auth()
    wait = bool(args.get("wait", True))
    force = bool(args.get("force", False))
    try:
        session = await auth.authenticate(force_login=force, wait=wait)
    except AuthRequired as e:
        return _err(str(e) or AUTH_INSTRUCTIONS)
    return _ok(
        {
            "ok": True,
            "message": "Shadowbot session is ready.",
            "email": session.get("email"),
            "name": session.get("name"),
            "preferred_username": session.get("preferred_username"),
            "assistant_id": session.get("assistant_id"),
            "captured_at": session.get("captured_at"),
        }
    )


async def handle_whoami() -> list[TextContent]:
    auth = get_auth()
    status = auth.status_dict()
    try:
        identity = await whoami()
        status.update(identity)
        status["authenticated"] = True
    except (AuthRequired, SessionExpired) as e:
        status["authenticated"] = False
        status["error"] = str(e)
        status["next_step"] = (
            "Call shadowbot_auth. The associate signs in with Red Hat SSO + FreeOTP in Chrome."
        )
    return _ok(status)


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
