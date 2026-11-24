"""Lightweight Chrome DevTools helpers — no Playwright during login wait."""

from __future__ import annotations

import json
import urllib.request
from typing import Any


def list_tabs(port: int) -> list[dict[str, Any]]:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=2) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data if isinstance(data, list) else []
    except Exception:
        return []


def best_linkedin_tab(port: int) -> dict[str, Any] | None:
    tabs = [t for t in list_tabs(port) if t.get("type") == "page"]
    if not tabs:
        return None

    def score(tab: dict[str, Any]) -> int:
        url = (tab.get("url") or "").lower()
        s = 0
        if "/sales/" in url and "/sales/login" not in url:
            s += 100
        if "/sales/homepage" in url:
            s += 20
        if "linkedin.com/feed" in url:
            s += 40
        if "/sales/login" in url or "linkedin.com/login" in url or "linkedin.com/uas/" in url:
            s -= 100
        return s

    tabs.sort(key=score, reverse=True)
    return tabs[0]


def chrome_status(port: int) -> dict[str, Any]:
    tab = best_linkedin_tab(port)
    url = (tab or {}).get("url") or ""
    low = url.lower()
    return {
        "chrome_url": url or None,
        "on_sales_login_page": "/sales/login" in low,
        "on_linkedin_login_page": "linkedin.com/login" in low or "linkedin.com/uas/" in low,
        "on_sales_navigator": "/sales/" in low and "/sales/login" not in low,
    }
