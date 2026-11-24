"""High-level Shadowbot operations used by the MCP server and CLI."""

from __future__ import annotations

import json
from typing import Any

from .auth import get_auth
from .langgraph import last_ai_text, message_text

AUTH_HINT = (
    "Call shadowbot_auth so the associate can sign in with Red Hat SSO + FreeOTP "
    "in Chrome, then retry."
)


def to_text(payload: Any) -> str:
    return json.dumps(payload, indent=2, default=str, ensure_ascii=False)


def _trim(text: str | None, limit: int = 8000) -> str | None:
    if text is None:
        return None
    text = str(text)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def _format_message(msg: Any) -> dict[str, Any] | None:
    if not isinstance(msg, dict):
        return None
    text = message_text(msg).strip()
    kind = msg.get("type") or msg.get("role")
    if not text and kind not in {"ai", "human", "assistant", "user"}:
        return None
    return {
        "type": kind,
        "text": _trim(text, 4000),
        "id": msg.get("id"),
        "name": msg.get("name"),
    }


async def whoami() -> dict[str, Any]:
    auth = get_auth()
    client = await auth.ensure_client()
    session = auth.load_session() or {}
    probe = await client.probe()
    return {
        "email": session.get("email"),
        "name": session.get("name"),
        "preferred_username": session.get("preferred_username"),
        "assistant_id": client.assistant_id,
        "langgraph_api_url": client.api_url,
        "thread_id": session.get("thread_id"),
        "probe": probe,
    }


async def ask(
    prompt: str,
    *,
    thread_id: str | None = None,
    new_thread: bool = False,
) -> dict[str, Any]:
    text = (prompt or "").strip()
    if not text:
        raise ValueError("Prompt is empty.")
    auth = get_auth()
    client = await auth.ensure_client()
    session = auth.load_session() or {}
    tid = None if new_thread else (thread_id or session.get("thread_id"))
    result = await client.ask(text, thread_id=tid, new_thread=new_thread or not tid)
    session["thread_id"] = result["thread_id"]
    auth.save_session(session)
    answer = (result.get("answer") or "").strip()
    if not answer:
        return {
            **result,
            "answer": "",
            "hint": (
                "Shadowbot returned no assistant text. The run may still be in progress, "
                "or the graph used a different output shape. Try shadowbot_get_thread "
                f"with thread_id={result.get('thread_id')}."
            ),
        }
    return {
        "thread_id": result["thread_id"],
        "answer": answer,
        "ui_url": (
            "https://shadowbot.io.redhat.com/agents/sales-assistant/chat/"
            + result["thread_id"]
        ),
        "hint": "Pass the same thread_id (or omit it) to continue this conversation.",
    }


async def list_threads(*, limit: int = 20) -> dict[str, Any]:
    client = await get_auth().ensure_client()
    rows = await client.search_threads(limit=limit)
    threads = []
    for row in rows:
        threads.append(
            {
                "thread_id": row.get("thread_id"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
                "status": row.get("status"),
                "metadata": row.get("metadata") or {},
            }
        )
    return {
        "count": len(threads),
        "threads": threads,
        "hint": "Pass thread_id to shadowbot_ask or shadowbot_get_thread.",
    }


async def get_thread(thread_id: str, *, limit: int = 50) -> dict[str, Any]:
    tid = (thread_id or "").strip()
    if not tid:
        raise ValueError("thread_id is required.")
    client = await get_auth().ensure_client()
    messages = await client.get_history(tid, limit=limit)
    formatted = []
    for msg in messages:
        row = _format_message(msg)
        if row:
            formatted.append(row)
    return {
        "thread_id": tid,
        "messages": formatted,
        "answer": last_ai_text(messages) or None,
        "ui_url": f"https://shadowbot.io.redhat.com/agents/sales-assistant/chat/{tid}",
    }
