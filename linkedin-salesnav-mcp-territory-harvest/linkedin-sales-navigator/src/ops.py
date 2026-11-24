"""High-level Sales Navigator operations used by the MCP server and CLI."""

from __future__ import annotations

import json
from typing import Any

from .auth import AuthRequired, get_auth
from .linkedin import RateLimited, SessionExpired

AUTH_HINT = (
    "Call salesnav_auth so the user can sign in to LinkedIn Sales Navigator in Chrome, "
    "then retry."
)


def to_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload, indent=2, default=str)


async def with_client(coro_fn):
    auth = get_auth()
    try:
        client = await auth.ensure_client()
        return await coro_fn(client)
    except SessionExpired:
        auth.clear_client()
        try:
            client = await auth.ensure_client()
            return await coro_fn(client)
        except (SessionExpired, AuthRequired) as e:
            raise AuthRequired(str(e) if str(e) else AUTH_HINT) from e


async def whoami() -> dict[str, Any]:
    auth = get_auth()
    session = await auth.probe_saved_session()
    if not session:
        raise AuthRequired(
            "Not signed in to LinkedIn Sales Navigator. Call salesnav_auth, "
            "sign in via Chrome, then retry."
        )
    return {
        "name": session.get("name"),
        "public_id": session.get("public_id"),
        "profile_url": session.get("profile_url"),
        "headline": session.get("headline"),
        "has_sales_nav_cookie": bool((session.get("cookies") or {}).get("li_a")),
        "captured_at": session.get("captured_at"),
        "checked_at": session.get("checked_at"),
    }


async def search_leads(keywords: str, *, start: int = 0, limit: int = 25) -> dict[str, Any]:
    async def _run(client):
        return await client.search_leads(keywords, start=start, count=limit)

    return await with_client(_run)


async def search_companies(keywords: str, *, start: int = 0, limit: int = 25) -> dict[str, Any]:
    async def _run(client):
        return await client.search_companies(keywords, start=start, count=limit)

    return await with_client(_run)


async def get_profile(profile_ref: str) -> dict[str, Any]:
    async def _run(client):
        return await client.get_profile(profile_ref)

    return await with_client(_run)


async def get_company(company_ref: str) -> dict[str, Any]:
    async def _run(client):
        return await client.get_company(company_ref)

    return await with_client(_run)


async def list_saved_lists(list_type: str = "people") -> dict[str, Any]:
    async def _run(client):
        return await client.list_saved_lists(list_type)

    return await with_client(_run)


async def get_saved_list(
    list_id: str,
    list_type: str = "people",
    *,
    start: int = 0,
    limit: int = 25,
) -> dict[str, Any]:
    async def _run(client):
        return await client.get_saved_list(list_id, list_type, start=start, count=limit)

    return await with_client(_run)


async def search_from_url(search_url: str, *, start: int = 0, limit: int = 25) -> dict[str, Any]:
    async def _run(client):
        return await client.search_from_url(search_url, start=start, count=limit)

    return await with_client(_run)
