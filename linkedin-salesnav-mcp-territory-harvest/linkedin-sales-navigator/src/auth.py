"""LinkedIn Sales Navigator session via persistent Chrome or cookie import."""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any, Optional

from .cdp import chrome_status
from .chrome import (
    connect_over_cdp,
    cookies_from_context,
    csrf_from_cookies,
    disconnect_leave_chrome,
    has_sales_nav_session,
    log,
    spawn_chrome_cdp,
    cdp_alive,
)
from .config import SalesNavConfig, load_config
from .cookies_import import parse_cookie_editor_export
from .linkedin import SessionExpired, probe_session

AUTH_INSTRUCTIONS = (
    "LinkedIn Sales Navigator login required.\n\n"
    "This MCP uses a **separate Chrome window** (not your everyday Chrome). "
    "Look for the Chrome window that opened when you called salesnav_auth.\n\n"
    "Option A — sign in there:\n"
    "1. Sign in to LinkedIn in that Chrome window.\n"
    "2. Go to linkedin.com/sales and wait for the Sales Navigator homepage.\n"
    "3. Call salesnav_auth again.\n\n"
    "Option B — import cookies from your regular browser (recommended if login keeps failing):\n"
    "1. In your normal Chrome, open linkedin.com/sales while logged in.\n"
    "2. Install the Cookie-Editor extension, export cookies as JSON.\n"
    "3. Call salesnav_import_cookies with that JSON.\n\n"
    "You need an active Sales Navigator subscription."
)


class AuthRequired(RuntimeError):
    def __init__(self, message: str = AUTH_INSTRUCTIONS):
        super().__init__(message)


class SalesNavAuth:
    def __init__(self, config: Optional[SalesNavConfig] = None):
        self.config = config or load_config()
        self._session: dict | None = None
        self._client = None

    def session_path(self):
        return self.config.session_file

    def load_session(self) -> dict | None:
        path = self.session_path()
        if not path.exists():
            self._session = None
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            self._session = None
            return None
        cookies = (data or {}).get("cookies") or {}
        if not isinstance(data, dict) or not has_sales_nav_session(cookies):
            self._session = None
            return None
        self._session = data
        return data

    def save_session(self, session: dict) -> None:
        path = self.session_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(session, indent=2), encoding="utf-8")
        try:
            path.chmod(0o600)
        except Exception:
            pass
        self._session = session
        self._client = None

    def clear_client(self) -> None:
        from .browser_client import clear_browser_client

        self._client = None
        clear_browser_client()

    async def import_cookies(self, cookie_json: str | list[dict[str, Any]]) -> dict:
        cookies = parse_cookie_editor_export(cookie_json)
        csrf = csrf_from_cookies(cookies)
        if not csrf:
            raise ValueError("Could not derive csrf-token from JSESSIONID cookie")
        identity = await probe_session(cookies, csrf)
        session = {
            "cookies": cookies,
            "csrf_token": csrf,
            "source": "cookie_import",
            "captured_at": datetime.now(timezone.utc).isoformat(),
            **identity,
        }
        self.save_session(session)
        return session

    async def probe_saved_session(self) -> dict | None:
        """Validate session. Prefer live Chrome cookies over stale session.json."""
        if cdp_alive(self.config.cdp_port):
            try:
                return await self.harvest_from_chrome(navigate=False, wait=False)
            except AuthRequired:
                pass
            except Exception as e:
                log(f"Chrome session harvest failed: {e}")

        session = self.load_session()
        if not session:
            return None
        cookies = session.get("cookies") or {}
        csrf = session.get("csrf_token")
        if not cookies.get("li_at") or not csrf:
            return None
        try:
            identity = await probe_session(cookies, csrf)
        except SessionExpired:
            return None
        except Exception as e:
            log(f"Session probe failed: {e}")
            return None
        session.update(identity)
        session["checked_at"] = datetime.now(timezone.utc).isoformat()
        self.save_session(session)
        return session

    async def _harvest_cookies_playwright(self) -> tuple[dict[str, str], str]:
        from playwright.async_api import async_playwright

        browser = None
        async with async_playwright() as p:
            try:
                browser, context, _page = await connect_over_cdp(p, self.config.cdp_port)
                cookies_list = await context.cookies()
                cookies = cookies_from_context(cookies_list)
                csrf = csrf_from_cookies(cookies)
                return cookies, csrf or ""
            finally:
                if browser is not None:
                    await disconnect_leave_chrome(browser)

    async def _open_login_page(self) -> None:
        """Navigate the MCP Chrome window without keeping Playwright attached."""
        from playwright.async_api import async_playwright

        browser = None
        async with async_playwright() as p:
            try:
                # Reuse existing Sales Nav / LinkedIn tab; new tab only if none match
                browser, context, page = await connect_over_cdp(
                    p, self.config.cdp_port, new_tab=True
                )
                cookies = cookies_from_context(await context.cookies())
                # Regular login first — sales/login can loop with bot-check iframes.
                target = (
                    self.config.sales_url
                    if cookies.get("li_at")
                    else self.config.start_url
                )
                log(f"Opening LinkedIn -> {target}")
                try:
                    await page.goto(target, wait_until="domcontentloaded", timeout=60_000)
                except Exception as e:
                    log(f"Navigation warning: {e}")
            finally:
                if browser is not None:
                    await disconnect_leave_chrome(browser)

    async def harvest_from_chrome(self, *, navigate: bool, wait: bool) -> dict:
        try:
            from playwright.async_api import async_playwright  # noqa: F401
        except ImportError as e:
            raise RuntimeError(
                "playwright is not installed. From linkedin-sales-navigator run:\n"
                "  python3 -m venv .venv && .venv/bin/pip install -r requirements.txt\n"
                "  .venv/bin/playwright install chromium"
            ) from e

        spawn_chrome_cdp(self.config.profile, self.config.cdp_port)
        if navigate:
            await self._open_login_page()

        if wait:
            ready = await self._wait_for_login()
            if not ready:
                status = chrome_status(self.config.cdp_port)
                raise AuthRequired(self._login_help(status))

        cookies, csrf = await self._harvest_cookies_playwright()
        if not has_sales_nav_session(cookies):
            status = chrome_status(self.config.cdp_port)
            raise AuthRequired(self._login_help(status))

        if not csrf:
            raise AuthRequired(
                "Logged into LinkedIn but no JSESSIONID cookie was found. "
                "Refresh linkedin.com/sales, then call salesnav_auth again."
            )

        status = chrome_status(self.config.cdp_port)
        identity: dict[str, Any] = {}
        if cdp_alive(self.config.cdp_port) and status.get("on_sales_navigator"):
            try:
                from .browser_client import get_browser_client

                browser_client = await get_browser_client(self.config)
                identity = await browser_client.probe_identity()
            except Exception as e:
                log(f"Browser identity probe skipped: {e}")
        else:
            identity = await probe_session(cookies, csrf)

        session = {
            "cookies": cookies,
            "csrf_token": csrf,
            "page_url": status.get("chrome_url"),
            "captured_at": datetime.now(timezone.utc).isoformat(),
            **identity,
        }
        self.save_session(session)
        log(f"Harvested LinkedIn session for {session.get('name') or 'user'}")
        return session

    def _login_help(self, status: dict[str, Any]) -> str:
        lines = [AUTH_INSTRUCTIONS, "", "Current MCP Chrome status:"]
        url = status.get("chrome_url") or "(no LinkedIn tab open)"
        lines.append(f"- URL: {url}")
        if status.get("on_sales_login_page"):
            lines.append(
                "- Stuck on Sales Navigator login. Your LinkedIn account may not have "
                "Sales Navigator in this browser, or LinkedIn blocked the session."
            )
            lines.append("- Try salesnav_import_cookies from your regular browser instead.")
        elif status.get("on_linkedin_login_page"):
            lines.append("- Still on LinkedIn login. Complete sign-in in the MCP Chrome window.")
        elif status.get("on_sales_navigator"):
            lines.append("- Sales Navigator page detected but li_a cookie missing. Refresh the page.")
        return "\n".join(lines)

    async def _wait_for_login(self) -> bool:
        timeout = self.config.login_timeout_seconds
        ready_path = self.config.profile / "user_ready"
        log("=" * 60)
        log("ACTION REQUIRED — LINKEDIN SALES NAVIGATOR")
        log("Use the SEPARATE Chrome window opened by this MCP (not your daily Chrome).")
        log("1. Sign in to LinkedIn in that window.")
        log("2. Open linkedin.com/sales and wait for the homepage.")
        log(f"   Auto-detect timeout: {timeout}s")
        log(f"   Or create: {ready_path}")
        log("   Or use salesnav_import_cookies from your regular browser.")
        log("=" * 60)

        deadline = asyncio.get_event_loop().time() + timeout
        while asyncio.get_event_loop().time() < deadline:
            status = chrome_status(self.config.cdp_port)
            if status.get("on_sales_navigator"):
                cookies, csrf = await self._harvest_cookies_playwright()
                if has_sales_nav_session(cookies) and csrf:
                    log(f"Sales Navigator ready -> {status.get('chrome_url')}")
                    return True
            if ready_path.exists():
                try:
                    ready_path.unlink()
                except Exception:
                    pass
                log("Ready sentinel seen — harvesting session.")
                return True
            await asyncio.sleep(2)
        return False

    async def authenticate(self, *, force_login: bool = False, wait: bool = False) -> dict:
        if not force_login:
            try:
                return await self.harvest_from_chrome(navigate=False, wait=False)
            except AuthRequired:
                pass
            except Exception as e:
                log(f"Silent harvest failed: {e}")

            session = self.load_session()
            if session and has_sales_nav_session(session.get("cookies") or {}):
                return session

            if not wait:
                raise AuthRequired(self._login_help(chrome_status(self.config.cdp_port)))

        return await self.harvest_from_chrome(navigate=force_login or wait, wait=wait)

    async def ensure_client(self):
        from .browser_client import BrowserLinkedInClient, clear_browser_client, get_browser_client
        from .linkedin import LinkedInClient

        spawn_chrome_cdp(self.config.profile, self.config.cdp_port)
        if cdp_alive(self.config.cdp_port):
            status = chrome_status(self.config.cdp_port)
            if status.get("on_sales_navigator"):
                if self._client is None or not isinstance(self._client, BrowserLinkedInClient):
                    clear_browser_client()
                    self._client = await get_browser_client(self.config)
                return self._client

        session = await self.authenticate(wait=False)
        if self._client is None:
            self._client = LinkedInClient(
                cookies=session["cookies"],
                csrf_token=session["csrf_token"],
            )
        return self._client

    def status_dict(self) -> dict:
        session = self.load_session() or {}
        cookies = session.get("cookies") or {}
        status = {
            "authenticated": bool(cookies.get("li_at")),
            "has_sales_nav_cookie": bool(cookies.get("li_a")),
            "name": session.get("name"),
            "public_id": session.get("public_id"),
            "profile_url": session.get("profile_url"),
            "headline": session.get("headline"),
            "captured_at": session.get("captured_at"),
            "checked_at": session.get("checked_at"),
            "chrome_cdp_alive": cdp_alive(self.config.cdp_port),
            "cdp_port": self.config.cdp_port,
            "session_source": session.get("source") or ("chrome" if session else None),
        }
        if cdp_alive(self.config.cdp_port):
            status.update(chrome_status(self.config.cdp_port))
        return status


_default_auth: Optional[SalesNavAuth] = None


def get_auth() -> SalesNavAuth:
    global _default_auth
    if _default_auth is None:
        _default_auth = SalesNavAuth()
    return _default_auth
