"""Import LinkedIn cookies exported from a regular browser (Cookie-Editor JSON)."""

from __future__ import annotations

import json
from typing import Any


def parse_cookie_editor_export(raw: str | list[dict[str, Any]]) -> dict[str, str]:
    """Parse Cookie-Editor JSON (array or stringified array) into a name->value map."""
    if isinstance(raw, str):
        text = raw.strip()
        if not text:
            raise ValueError("Cookie JSON is empty")
        data = json.loads(text)
    else:
        data = raw

    if not isinstance(data, list):
        raise ValueError("Cookie export must be a JSON array")

    cookies: dict[str, str] = {}
    for item in data:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        value = item.get("value")
        domain = (item.get("domain") or "").lower()
        if not name or value is None:
            continue
        if "linkedin.com" not in domain and name not in {"li_at", "li_a", "JSESSIONID"}:
            continue
        cookies[str(name)] = str(value)

    if not cookies.get("li_at"):
        raise ValueError("Export is missing the li_at cookie. Export while logged into linkedin.com.")
    if not cookies.get("JSESSIONID"):
        raise ValueError("Export is missing JSESSIONID. Export while on linkedin.com/sales.")
    if not cookies.get("li_a"):
        raise ValueError(
            "Export is missing the li_a cookie (Sales Navigator). "
            "Open linkedin.com/sales in your browser, confirm Sales Navigator loads, then re-export."
        )
    return cookies
