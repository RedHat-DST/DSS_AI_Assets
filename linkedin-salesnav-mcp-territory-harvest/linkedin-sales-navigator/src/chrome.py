"""Persistent Chrome via CDP for LinkedIn Sales Navigator login."""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

_MCP_CHROME = importlib.util.spec_from_file_location(
    "mcp_chrome_shared",
    Path.home() / "mcps" / "mcp-chrome" / "shared.py",
)
_mcp_chrome_mod = importlib.util.module_from_spec(_MCP_CHROME)
assert _MCP_CHROME.loader is not None
_MCP_CHROME.loader.exec_module(_mcp_chrome_mod)

cdp_alive = _mcp_chrome_mod.cdp_alive
cdp_endpoint = _mcp_chrome_mod.cdp_endpoint
log = _mcp_chrome_mod.log
spawn_chrome_cdp = _mcp_chrome_mod.spawn_chrome_cdp
_shared_connect = _mcp_chrome_mod.connect_over_cdp
SERVICE_URL_HINTS = _mcp_chrome_mod.SERVICE_URL_HINTS

LOGIN_URL_HINTS = (
    "/sales/login",
    "linkedin.com/login",
    "linkedin.com/uas/login",
    "linkedin.com/checkpoint",
    "linkedin.com/authwall",
    "linkedin.com/signup",
    "challenge",
)

SALES_NAV_SELECTORS = (
    "[data-test-global-nav-link='home']",
    ".global-nav__content",
    ".application-outlet",
    "[data-x--global-application-header]",
    ".scaffold-layout",
    "nav.global-nav",
)


def is_login_url(url: str) -> bool:
    low = (url or "").lower()
    if not low:
        return True
    if any(h in low for h in LOGIN_URL_HINTS):
        return True
    if "/sales/" in low and "/sales/login" not in low:
        return False
    if "linkedin.com/feed" in low:
        return False
    if "linkedin.com/in/" in low:
        return False
    return "linkedin.com" not in low


async def page_has_auth_form(page) -> bool:
    selectors = (
        "input#username",
        "input#password",
        "input[name='session_password']",
        "input[type='password']",
    )
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible(timeout=400):
                return True
        except Exception:
            continue
    return False


def has_sales_nav_session(cookies: list[dict[str, Any]] | dict[str, str] | None) -> bool:
    """Sales Navigator API requires li_at plus the li_a subscription cookie."""
    if not cookies:
        return False
    if isinstance(cookies, dict):
        names = set(cookies)
    else:
        names = {c.get("name") for c in cookies}
    return "li_at" in names and "li_a" in names


async def looks_logged_in(page, cookies: list[dict[str, Any]] | None = None) -> bool:
    """True when Sales Navigator is loaded with a valid subscription session."""
    if not has_sales_nav_session(cookies):
        return False

    try:
        url = page.url or ""
    except Exception:
        return False

    if is_login_url(url):
        return False
    if await page_has_auth_form(page):
        return False

    low = url.lower()
    if "/sales" in low:
        return True

    for sel in SALES_NAV_SELECTORS:
        try:
            if await page.locator(sel).first.count() > 0:
                return True
        except Exception:
            continue

    return False


def pick_best_page_sync(pages: list[Any]):
    if not pages:
        return None
    ranked: list[tuple[int, Any]] = []
    for p in pages:
        try:
            url = p.url or ""
        except Exception:
            url = ""
        score = 0
        if "/sales" in url:
            score += 60
        if "linkedin.com/feed" in url:
            score += 40
        if "linkedin.com/in/" in url:
            score += 20
        if is_login_url(url):
            score -= 100
        ranked.append((score, p))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


async def connect_over_cdp(
    playwright,
    port: int,
    *,
    new_tab: bool = False,
    match_url_substrings: tuple[str, ...] | None = None,
):
    """Reuse LinkedIn/Sales Nav tab when present; only open a new tab if needed."""
    hints = match_url_substrings or SERVICE_URL_HINTS["salesnav"]
    return await _shared_connect(
        playwright,
        port,
        new_tab=new_tab,
        match_url_substrings=hints,
        pick_best=pick_best_page_sync,
    )


async def disconnect_leave_chrome(browser) -> None:
    """Do not call browser.close() — that can tear down the login window."""
    log("Leaving Chrome open for the next Sales Navigator call.")


def cookies_from_context(cookies: list[dict[str, Any]]) -> dict[str, str]:
    """Extract key LinkedIn cookies from a Playwright cookie list."""
    result: dict[str, str] = {}
    for c in cookies:
        name = c.get("name")
        value = c.get("value")
        if name and value:
            result[name] = str(value)
    return result


def csrf_from_cookies(cookies: dict[str, str]) -> str | None:
    """Derive csrf-token from JSESSIONID cookie."""
    jsession = cookies.get("JSESSIONID", "")
    if not jsession:
        return None
    if jsession.startswith('"') and jsession.endswith('"'):
        jsession = jsession[1:-1]
    if jsession.startswith("ajax:"):
        return jsession
    return f"ajax:{jsession}"


def _cookie_value(name: str, value: str) -> str:
    if name == "JSESSIONID" and value.startswith('"') and value.endswith('"'):
        return value[1:-1]
    return value


def cookie_header(cookies: dict[str, str]) -> str:
    """Build a Cookie header string from harvested cookies."""
    parts = []
    for name in ("li_at", "JSESSIONID", "li_a", "bcookie", "bscookie", "lang", "liap"):
        if name in cookies:
            parts.append(f"{name}={_cookie_value(name, cookies[name])}")
    for name, value in cookies.items():
        if name not in {"li_at", "JSESSIONID", "li_a", "bcookie", "bscookie", "lang", "liap"}:
            parts.append(f"{name}={_cookie_value(name, value)}")
    return "; ".join(parts)
