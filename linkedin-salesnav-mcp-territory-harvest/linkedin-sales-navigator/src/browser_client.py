"""LinkedIn API client that runs fetch() inside MCP Chrome.

Copied cookies over httpx expire quickly (401). Keeping requests in the
browser context uses the live session and avoids repeated disconnects.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from .chrome import connect_over_cdp, disconnect_leave_chrome, log, spawn_chrome_cdp
from .config import SalesNavConfig, load_config
from .linkedin import LinkedInClient, RateLimited, SessionExpired

_BROWSER_FETCH = """
async ({ method, url, extraHeaders }) => {
  function csrfToken() {
    const match = document.cookie.match(/JSESSIONID="?(ajax:[^";]+)"?/);
    return match ? match[1] : "";
  }
  const headers = {
    "csrf-token": csrfToken(),
    "x-restli-protocol-version": "2.0.0",
    "x-li-lang": "en_US",
    "accept": "application/vnd.linkedin.normalized+json+2.1",
    "accept-language": "en-US,en;q=0.9",
    "referer": "https://www.linkedin.com/sales/search/people",
    ...extraHeaders,
  };
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 25000);
  try {
    const response = await fetch(url, {
      method,
      headers,
      credentials: "include",
      signal: controller.signal,
    });
    const body = await response.text();
    return { status: response.status, body };
  } catch (err) {
    const message = err && err.name === "AbortError"
      ? "fetch timed out after 25s"
      : String(err);
    return { status: 0, body: "", error: message };
  } finally {
    clearTimeout(timer);
  }
}
"""

REQUEST_TIMEOUT_SECONDS = 30


class BrowserLinkedInClient(LinkedInClient):
    """Sales Navigator client backed by in-browser fetch (CDP)."""

    def __init__(self, config: SalesNavConfig | None = None):
        self.config = config or load_config()
        self.cookies: dict[str, str] = {}
        self.csrf_token = ""
        self._client = None
        self._playwright = None
        self._browser = None
        self._page = None

    async def _ensure_page(self):
        from playwright.async_api import async_playwright

        spawn_chrome_cdp(self.config.profile, self.config.cdp_port)
        if self._page is not None:
            try:
                if not self._page.is_closed():
                    return self._page
            except Exception:
                self._page = None

        if self._playwright is None:
            self._playwright = await async_playwright().start()

        self._browser, _context, page = await connect_over_cdp(
            self._playwright, self.config.cdp_port
        )
        self._page = page
        url = (page.url or "").lower()
        if "/sales/" not in url or "/sales/login" in url:
            log(f"Navigating MCP Chrome to Sales Navigator -> {self.config.sales_url}")
            try:
                await page.goto(
                    self.config.sales_url,
                    wait_until="domcontentloaded",
                    timeout=90_000,
                )
                await page.wait_for_timeout(2000)
            except Exception as e:
                log(f"Sales Navigator navigation warning: {e}")
        return self._page

    async def reset_page(self) -> None:
        self._page = None
        if self._browser is not None:
            await disconnect_leave_chrome(self._browser)
            self._browser = None

    async def request(self, method: str, url: str, **kwargs) -> Any:
        extra_headers = dict(kwargs.pop("headers", {}) or {})
        last_error: Exception | None = None
        for attempt in range(2):
            page = await self._ensure_page()
            try:
                result = await asyncio.wait_for(
                    page.evaluate(
                        _BROWSER_FETCH,
                        {"method": method, "url": url, "extraHeaders": extra_headers},
                    ),
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except asyncio.TimeoutError as e:
                last_error = e
                log(f"Browser fetch timed out (attempt {attempt + 1})")
                await self.reset_page()
                continue
            except Exception as e:
                last_error = e
                log(f"Browser fetch failed: {e}")
                await self.reset_page()
                continue

            if result.get("error"):
                last_error = RuntimeError(str(result.get("error")))
                log(f"Browser fetch error: {result.get('error')}")
                await self.reset_page()
                continue

            status = int(result.get("status") or 0)
            raw_body = result.get("body") or ""
            break
        else:
            raise RuntimeError(f"Browser fetch failed after retries: {last_error}")

        if status in {401, 403, 999}:
            raise SessionExpired(f"LinkedIn session expired (HTTP {status})")
        if status == 429:
            raise RateLimited("LinkedIn rate limit hit. Wait a few minutes and retry.")
        try:
            body = json.loads(raw_body) if raw_body else {}
        except Exception:
            body = raw_body
        if status >= 400:
            raise RuntimeError(f"LinkedIn API error {status}: {str(body)[:500]}")
        return body

    async def close(self) -> None:
        if self._browser is not None:
            await disconnect_leave_chrome(self._browser)
            self._browser = None
        self._page = None
        if self._playwright is not None:
            await self._playwright.stop()
            self._playwright = None


_browser_client: BrowserLinkedInClient | None = None


async def get_browser_client(config: SalesNavConfig | None = None) -> BrowserLinkedInClient:
    global _browser_client
    if _browser_client is None:
        _browser_client = BrowserLinkedInClient(config)
    return _browser_client


def clear_browser_client() -> None:
    global _browser_client
    _browser_client = None
