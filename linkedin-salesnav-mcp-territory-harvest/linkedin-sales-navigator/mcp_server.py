#!/usr/bin/env python3
"""
LinkedIn Sales Navigator MCP Server.

Exposes LinkedIn Sales Navigator to Cursor via the Model Context Protocol,
matching the Gmail / Drive / Calendar / Sales Cloud assistants.

Authentication uses a persistent Chrome window. The user signs in to LinkedIn
and Sales Navigator; the MCP harvests session cookies for API calls.
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
from src.linkedin import RateLimited, SessionExpired
from src.ops import (
    get_company,
    get_profile,
    get_saved_list,
    list_saved_lists,
    search_companies,
    search_from_url,
    search_leads,
    to_text,
    whoami,
)

server = Server("linkedin-sales-navigator")


def _ok(payload: Any) -> list[TextContent]:
    return [TextContent(type="text", text=to_text(payload) if not isinstance(payload, str) else payload)]


def _err(message: str) -> list[TextContent]:
    return [TextContent(type="text", text=message)]


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="salesnav_auth",
            description=(
                "Open or reconnect the persistent Chrome window for LinkedIn Sales Navigator. "
                "Use this whenever LinkedIn returns a session error, or before the first "
                "request. The user signs in to LinkedIn and navigates to Sales Navigator. "
                "Chrome stays open so later logins are faster. Set wait=true to block until "
                "Sales Navigator loads."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "wait": {
                        "type": "boolean",
                        "description": "Wait until Sales Navigator is visible after login (default: true)",
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
            name="salesnav_whoami",
            description="Show the authenticated LinkedIn user and whether the Chrome session is alive.",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="salesnav_import_cookies",
            description=(
                "Import LinkedIn cookies from Cookie-Editor JSON exported while logged into "
                "linkedin.com/sales in your regular browser. Use this when the MCP Chrome "
                "login keeps failing. Requires li_at, JSESSIONID, and li_a cookies."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "cookies_json": {
                        "type": "string",
                        "description": "Cookie-Editor JSON export (array of cookie objects)",
                    }
                },
                "required": ["cookies_json"],
            },
        ),
        Tool(
            name="salesnav_search_leads",
            description=(
                "Search Sales Navigator leads by keywords (name, title, company, etc.). "
                "Requires an active Sales Navigator subscription."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "Search keywords, e.g. 'VP Engineering Red Hat'",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Result offset for pagination (default: 0)",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results per page (default: 25, max: 100)",
                        "default": 25,
                    },
                },
                "required": ["keywords"],
            },
        ),
        Tool(
            name="salesnav_search_companies",
            description="Search Sales Navigator accounts/companies by keywords.",
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "string",
                        "description": "Company search keywords, e.g. 'Red Hat software'",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Result offset for pagination (default: 0)",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results per page (default: 25, max: 100)",
                        "default": 25,
                    },
                },
                "required": ["keywords"],
            },
        ),
        Tool(
            name="salesnav_get_profile",
            description=(
                "Get a Sales Navigator lead profile by profile id, Sales Navigator URL, "
                "or LinkedIn /in/ vanity URL."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "profile_ref": {
                        "type": "string",
                        "description": "Profile id, /sales/lead/ URL, or /in/ vanity URL",
                    },
                },
                "required": ["profile_ref"],
            },
        ),
        Tool(
            name="salesnav_get_company",
            description="Get a Sales Navigator company by id or URL.",
            inputSchema={
                "type": "object",
                "properties": {
                    "company_ref": {
                        "type": "string",
                        "description": "Company id or /sales/company/ URL",
                    },
                },
                "required": ["company_ref"],
            },
        ),
        Tool(
            name="salesnav_list_saved_lists",
            description="List saved lead or account lists in Sales Navigator.",
            inputSchema={
                "type": "object",
                "properties": {
                    "list_type": {
                        "type": "string",
                        "enum": ["people", "company"],
                        "description": "List type: people (leads) or company (accounts)",
                        "default": "people",
                    },
                },
                "required": [],
            },
        ),
        Tool(
            name="salesnav_get_saved_list",
            description="Get leads or accounts from a saved Sales Navigator list.",
            inputSchema={
                "type": "object",
                "properties": {
                    "list_id": {"type": "string", "description": "Saved list id"},
                    "list_type": {
                        "type": "string",
                        "enum": ["people", "company"],
                        "description": "List type (default: people)",
                        "default": "people",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Result offset (default: 0)",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 25)",
                        "default": 25,
                    },
                },
                "required": ["list_id"],
            },
        ),
        Tool(
            name="salesnav_search_from_url",
            description=(
                "Run a Sales Navigator search from a browser URL. Paste a people search, "
                "company search, or saved list URL copied from Sales Navigator."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "search_url": {
                        "type": "string",
                        "description": "Sales Navigator search or saved list URL from the browser",
                    },
                    "start": {
                        "type": "integer",
                        "description": "Result offset (default: 0)",
                        "default": 0,
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max results (default: 25)",
                        "default": 25,
                    },
                },
                "required": ["search_url"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    args = arguments or {}
    try:
        if name == "salesnav_auth":
            return await handle_auth(args)
        if name == "salesnav_whoami":
            return await handle_whoami()
        if name == "salesnav_import_cookies":
            return await handle_import_cookies(args)
        if name == "salesnav_search_leads":
            limit = min(int(args.get("limit", 25)), 100)
            return _ok(
                await search_leads(
                    args["keywords"],
                    start=args.get("start", 0),
                    limit=limit,
                )
            )
        if name == "salesnav_search_companies":
            limit = min(int(args.get("limit", 25)), 100)
            return _ok(
                await search_companies(
                    args["keywords"],
                    start=args.get("start", 0),
                    limit=limit,
                )
            )
        if name == "salesnav_get_profile":
            return _ok(await get_profile(args["profile_ref"]))
        if name == "salesnav_get_company":
            return _ok(await get_company(args["company_ref"]))
        if name == "salesnav_list_saved_lists":
            return _ok(await list_saved_lists(args.get("list_type", "people")))
        if name == "salesnav_get_saved_list":
            return _ok(
                await get_saved_list(
                    args["list_id"],
                    args.get("list_type", "people"),
                    start=args.get("start", 0),
                    limit=args.get("limit", 25),
                )
            )
        if name == "salesnav_search_from_url":
            return _ok(
                await search_from_url(
                    args["search_url"],
                    start=args.get("start", 0),
                    limit=args.get("limit", 25),
                )
            )
        return _err(f"Unknown tool: {name}")
    except (AuthRequired, SessionExpired) as e:
        return _err(str(e) or AUTH_INSTRUCTIONS)
    except RateLimited as e:
        return _err(str(e))
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
            "message": "LinkedIn Sales Navigator session is ready.",
            "name": session.get("name"),
            "public_id": session.get("public_id"),
            "profile_url": session.get("profile_url"),
            "headline": session.get("headline"),
            "has_sales_nav_cookie": bool((session.get("cookies") or {}).get("li_a")),
            "captured_at": session.get("captured_at"),
        }
    )


async def handle_import_cookies(args: dict) -> list[TextContent]:
    auth = get_auth()
    try:
        session = await auth.import_cookies(args["cookies_json"])
    except Exception as e:
        return _err(f"Cookie import failed: {e}")
    return _ok(
        {
            "ok": True,
            "message": "LinkedIn Sales Navigator session imported from cookies.",
            "name": session.get("name"),
            "public_id": session.get("public_id"),
            "profile_url": session.get("profile_url"),
            "has_sales_nav_cookie": bool((session.get("cookies") or {}).get("li_a")),
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
        status["next_step"] = "Call salesnav_auth and sign in to LinkedIn Sales Navigator in Chrome."
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
