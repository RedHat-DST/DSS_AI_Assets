"""LangGraph client for Red Hat Sales Assistant (Shadowbot)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from .config import ShadowbotConfig, load_config


class SessionExpired(RuntimeError):
    """Keycloak / LangGraph rejected the harvested session."""


def decode_jwt_claims(token: str) -> dict[str, Any]:
    import base64

    parts = (token or "").split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    payload += "=" * (-len(payload) % 4)
    try:
        return json.loads(base64.urlsafe_b64decode(payload.encode("ascii")))
    except Exception:
        return {}


def _is_auth_status(status: int) -> bool:
    return status in (401, 403)


def _headers(token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


async def probe_identity(token: str, userinfo_url: str) -> dict[str, Any]:
    """Validate the access token against Keycloak userinfo."""
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.get(
            userinfo_url,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        )
    if _is_auth_status(resp.status_code):
        raise SessionExpired(f"Keycloak userinfo returned HTTP {resp.status_code}")
    if resp.status_code >= 400:
        claims = decode_jwt_claims(token)
        if claims.get("email") or claims.get("preferred_username"):
            return _identity_from_claims(claims)
        raise SessionExpired(f"Keycloak userinfo returned HTTP {resp.status_code}: {resp.text[:240]}")
    try:
        body = resp.json()
    except Exception:
        body = {}
    if not isinstance(body, dict):
        body = {}
    claims = decode_jwt_claims(token)
    return {
        "email": body.get("email") or claims.get("email"),
        "name": body.get("name") or claims.get("name"),
        "preferred_username": body.get("preferred_username") or claims.get("preferred_username"),
        "sub": body.get("sub") or claims.get("sub"),
        "given_name": body.get("given_name") or claims.get("given_name"),
        "family_name": body.get("family_name") or claims.get("family_name"),
    }


def _identity_from_claims(claims: dict[str, Any]) -> dict[str, Any]:
    return {
        "email": claims.get("email"),
        "name": claims.get("name"),
        "preferred_username": claims.get("preferred_username"),
        "sub": claims.get("sub"),
        "given_name": claims.get("given_name"),
        "family_name": claims.get("family_name"),
    }


async def refresh_access_token(
    refresh_token: str,
    token_url: str,
    client_id: str,
) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
        resp = await client.post(
            token_url,
            data={
                "grant_type": "refresh_token",
                "refresh_token": refresh_token,
                "client_id": client_id,
            },
            headers={"Accept": "application/json"},
        )
    if _is_auth_status(resp.status_code) or resp.status_code >= 400:
        raise SessionExpired(f"Token refresh failed HTTP {resp.status_code}")
    body = resp.json()
    if not isinstance(body, dict) or not body.get("access_token"):
        raise SessionExpired("Token refresh returned no access_token")
    return body


def message_text(msg: Any) -> str:
    if msg is None:
        return ""
    if isinstance(msg, str):
        return msg
    if not isinstance(msg, dict):
        return str(msg)
    content = msg.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if isinstance(part, str):
                parts.append(part)
            elif isinstance(part, dict):
                parts.append(str(part.get("text") or part.get("content") or ""))
        return "".join(parts)
    return str(msg.get("text") or "")


def is_ai_message(msg: Any) -> bool:
    if not isinstance(msg, dict):
        return False
    kind = str(msg.get("type") or msg.get("role") or "").lower()
    return kind in {"ai", "assistant", "aimessage", "ai_message"}


def last_ai_text(messages: list[Any]) -> str:
    texts: list[str] = []
    for msg in messages:
        if is_ai_message(msg):
            text = message_text(msg).strip()
            # Skip empty tool-call-only AI turns
            if text:
                texts.append(text)
    return texts[-1] if texts else ""


def extract_messages(payload: Any) -> list[Any]:
    if isinstance(payload, list):
        return payload
    if not isinstance(payload, dict):
        return []
    for key in ("messages", "values"):
        val = payload.get(key)
        if isinstance(val, list):
            return val
        if isinstance(val, dict) and isinstance(val.get("messages"), list):
            return val["messages"]
    return []


class LangGraphClient:
    def __init__(
        self,
        token: str,
        api_url: str,
        assistant_id: str,
        timeout: float = 300.0,
        config: ShadowbotConfig | None = None,
    ):
        self.token = token
        self.api_url = api_url.rstrip("/")
        self.assistant_id = assistant_id
        self.timeout = timeout
        self.config = config or load_config()

    def _url(self, path: str) -> str:
        return f"{self.api_url}{path}"

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Any = None,
        params: dict | None = None,
        timeout: float | None = None,
    ) -> Any:
        async with httpx.AsyncClient(timeout=timeout or 60.0, follow_redirects=True) as client:
            resp = await client.request(
                method,
                self._url(path),
                headers=_headers(self.token),
                json=json_body,
                params=params,
            )
        if _is_auth_status(resp.status_code):
            raise SessionExpired(f"LangGraph returned HTTP {resp.status_code} for {path}")
        if resp.status_code >= 400:
            raise RuntimeError(f"LangGraph HTTP {resp.status_code} {path}: {resp.text[:800]}")
        if not resp.content:
            return None
        try:
            return resp.json()
        except Exception:
            return {"raw": resp.text}

    async def probe(self) -> dict[str, Any]:
        for path in ("/ok", "/info", "/assistants/search"):
            try:
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    if path.endswith("/search"):
                        resp = await client.post(
                            self._url(path),
                            headers=_headers(self.token),
                            json={"limit": 1},
                        )
                    else:
                        resp = await client.get(self._url(path), headers=_headers(self.token))
                if _is_auth_status(resp.status_code):
                    raise SessionExpired(f"LangGraph returned HTTP {resp.status_code} for {path}")
                if resp.status_code < 400:
                    try:
                        body = resp.json()
                    except Exception:
                        body = {"ok": True, "status": resp.status_code}
                    return {"path": path, "status": resp.status_code, "body": body}
            except SessionExpired:
                raise
            except Exception:
                continue
        return {"ok": True, "note": "token accepted; no /ok or /info endpoint"}

    async def create_thread(self, metadata: dict | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {}
        if metadata:
            body["metadata"] = metadata
        result = await self._request("POST", "/threads", json_body=body or None)
        if not isinstance(result, dict) or not result.get("thread_id"):
            raise RuntimeError(f"Could not create thread: {result}")
        return result

    async def search_threads(self, *, limit: int = 20) -> list[dict[str, Any]]:
        result = await self._request(
            "POST",
            "/threads/search",
            json_body={
                "limit": max(1, min(int(limit), 100)),
                "sort_by": "updated_at",
                "sort_order": "desc",
            },
        )
        if isinstance(result, list):
            return [r for r in result if isinstance(r, dict)]
        if isinstance(result, dict) and isinstance(result.get("threads"), list):
            return [r for r in result["threads"] if isinstance(r, dict)]
        return []

    async def get_history(self, thread_id: str, *, limit: int = 50) -> list[Any]:
        result = await self._request(
            "GET",
            f"/threads/{thread_id}/history",
            params={"limit": max(1, min(int(limit), 200))},
        )
        if isinstance(result, list):
            # History is a list of state snapshots; take the latest messages
            if result and isinstance(result[0], dict):
                msgs = extract_messages(result[0])
                if msgs:
                    return msgs
            return result
        return extract_messages(result)

    async def get_state(self, thread_id: str) -> dict[str, Any]:
        result = await self._request("GET", f"/threads/{thread_id}/state")
        return result if isinstance(result, dict) else {"raw": result}

    async def ask(
        self,
        prompt: str,
        *,
        thread_id: str | None = None,
        new_thread: bool = False,
    ) -> dict[str, Any]:
        if new_thread or not thread_id:
            thread = await self.create_thread(metadata={"source": "cursor-mcp"})
            thread_id = thread["thread_id"]
        payload = {
            "assistant_id": self.assistant_id,
            "input": {
                "messages": [
                    {"type": "human", "content": prompt},
                ]
            },
            "stream_mode": ["values"],
        }
        try:
            events, last_values = await self._stream_run(thread_id, payload)
        except RuntimeError as e:
            if "HTTP 404" in str(e) or "HTTP 405" in str(e):
                wait_body = await self._request(
                    "POST",
                    f"/threads/{thread_id}/runs/wait",
                    json_body={
                        "assistant_id": self.assistant_id,
                        "input": payload["input"],
                    },
                    timeout=self.timeout,
                )
                last_values = wait_body
                events = [{"event": "wait", "data": wait_body}]
            else:
                raise
        messages = extract_messages(last_values)
        answer = last_ai_text(messages)
        if not answer and events:
            for ev in reversed(events):
                msgs = extract_messages(ev.get("data"))
                answer = last_ai_text(msgs)
                if answer:
                    messages = msgs
                    break
        if not answer:
            try:
                state = await self.get_state(thread_id)
                messages = extract_messages(state) or extract_messages(state.get("values"))
                answer = last_ai_text(messages)
            except Exception:
                pass
        return {
            "thread_id": thread_id,
            "answer": answer,
            "message_count": len(messages),
            "event_count": len(events),
        }

    async def _stream_run(self, thread_id: str, payload: dict[str, Any]) -> tuple[list[dict[str, Any]], Any]:
        events: list[dict[str, Any]] = []
        last_values: Any = None
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            async with client.stream(
                "POST",
                self._url(f"/threads/{thread_id}/runs/stream"),
                headers=_headers(self.token),
                json=payload,
            ) as resp:
                if _is_auth_status(resp.status_code):
                    raise SessionExpired(
                        f"LangGraph stream returned HTTP {resp.status_code}"
                    )
                if resp.status_code >= 400:
                    body = await resp.aread()
                    raise RuntimeError(
                        f"LangGraph stream HTTP {resp.status_code}: {body[:800]!r}"
                    )
                buffer = ""
                async for chunk in resp.aiter_text():
                    buffer += chunk
                    while "\n\n" in buffer:
                        block, buffer = buffer.split("\n\n", 1)
                        parsed = _parse_sse(block)
                        if not parsed:
                            continue
                        events.append(parsed)
                        if parsed.get("event") in {"values", "data", "updates"}:
                            last_values = parsed.get("data")
        return events, last_values


def _parse_sse(block: str) -> dict[str, Any] | None:
    event = "message"
    data_lines: list[str] = []
    for line in block.splitlines():
        if not line or line.startswith(":"):
            continue
        if line.startswith("event:"):
            event = line[6:].strip()
        elif line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if not data_lines:
        return None
    raw = "\n".join(data_lines)
    try:
        data = json.loads(raw)
    except Exception:
        data = raw
    return {"event": event, "data": data}
