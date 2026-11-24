"""Persistent Chrome via CDP — same idea as Slack / Sales Cloud.

Chrome is launched in its own process group and left running. Later MCP
calls reconnect. The Red Hat associate completes SSO (auth.redhat.com) +
FreeOTP in that window whenever Shadowbot logs them out.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

LOGIN_URL_HINTS = (
    "login.",
    "/login",
    "/signin",
    "/sign-in",
    "/sso",
    "idp.",
    "sso.",
    "okta.com",
    "auth.redhat.com",
    "sso.redhat.com",
    "auth.stage.redhat.com",
)

AUTH_FORM_SELECTORS = (
    "input[type='password']",
    "input[name='password']",
    "input[autocomplete='current-password']",
    "#password",
    "#username",
)

SHADOWBOT_SELECTORS = (
    "textarea",
    "[contenteditable='true']",
    "form textarea",
    "[data-placeholder]",
    "button[type='submit']",
    "[role='textbox']",
)


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def cdp_endpoint(port: int) -> str:
    return f"http://127.0.0.1:{port}"


def cdp_alive(port: int) -> bool:
    try:
        with urllib.request.urlopen(cdp_endpoint(port) + "/json/version", timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def chrome_executable() -> Path:
    chrome_app = Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome")
    if chrome_app.exists():
        return chrome_app
    for name in ("google-chrome", "chrome", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return Path(found)
    raise FileNotFoundError("Google Chrome not found. Install Chrome, then retry shadowbot_auth.")


def spawn_chrome_cdp(profile: Path, port: int) -> int | None:
    """Start Chrome with remote debugging. Return pid if spawned, else None if already up."""
    if cdp_alive(port):
        log(f"Reusing existing Chrome CDP on port {port}")
        return None

    profile.mkdir(parents=True, exist_ok=True)
    exe = chrome_executable()
    args = [
        str(exe),
        f"--remote-debugging-port={port}",
        f"--user-data-dir={profile}",
        "--no-first-run",
        "--no-default-browser-check",
        "--disable-blink-features=AutomationControlled",
        "--disable-session-crashed-bubble",
        "--hide-crash-restore-bubble",
        "about:blank",
    ]
    log(f"Starting Chrome for CDP (port={port}) profile={profile}")
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if cdp_alive(port):
            log(f"Chrome CDP ready (pid={proc.pid})")
            return proc.pid
        if proc.poll() is not None:
            raise RuntimeError(f"Chrome exited early with code {proc.returncode}")
        time.sleep(0.4)
    raise RuntimeError(f"Timed out waiting for Chrome CDP on port {port}")


def is_login_url(url: str) -> bool:
    low = (url or "").lower()
    if not low:
        return True
    return any(h in low for h in LOGIN_URL_HINTS)


def is_shadowbot_url(url: str) -> bool:
    low = (url or "").lower()
    return "shadowbot.io.redhat.com" in low or "shadowbot.dev.io.redhat.com" in low


async def page_has_auth_form(page) -> bool:
    for sel in AUTH_FORM_SELECTORS:
        try:
            loc = page.locator(sel).first
            if await loc.count() and await loc.is_visible(timeout=400):
                return True
        except Exception:
            continue
    return False


async def looks_logged_in(page) -> bool:
    try:
        url = page.url or ""
    except Exception:
        return False
    if not is_shadowbot_url(url):
        return False
    if is_login_url(url):
        return False
    if await page_has_auth_form(page):
        return False
    for sel in SHADOWBOT_SELECTORS:
        try:
            if await page.locator(sel).first.count() > 0:
                return True
        except Exception:
            continue
    # Next.js shell after SSO redirect, before AppShell hydrates
    if "/agents/sales-assistant" in url.lower():
        return True
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
        low = url.lower()
        if "shadowbot.io.redhat.com" in low:
            score += 50
        if "/agents/sales-assistant" in low:
            score += 30
        if "/chat/" in low:
            score += 20
        if is_login_url(url):
            score -= 100
        ranked.append((score, p))
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


async def connect_over_cdp(playwright, port: int):
    endpoint = cdp_endpoint(port)
    log(f"Connecting Playwright over CDP -> {endpoint}")
    browser = await playwright.chromium.connect_over_cdp(endpoint)
    if browser.contexts:
        context = browser.contexts[0]
    else:
        context = await browser.new_context()
    page = pick_best_page_sync(list(context.pages))
    if page is None:
        page = await context.new_page()
    else:
        try:
            await page.bring_to_front()
        except Exception:
            pass
    return browser, context, page


async def disconnect_leave_chrome(browser) -> None:
    """Do not call browser.close() — that can tear down the SSO window."""
    log("Leaving Chrome open for the next Shadowbot call.")


HARVEST_JS = """
() => {
  const tokens = [];
  const keys = [];
  const push = (source, obj) => {
    if (!obj || typeof obj !== 'object') return;
    const access = obj.access_token || obj.accessToken || obj.token;
    const refresh = obj.refresh_token || obj.refreshToken;
    if (access && typeof access === 'string') {
      tokens.push({
        source,
        access_token: access,
        refresh_token: typeof refresh === 'string' ? refresh : null,
        expires_at: obj.expires_at || obj.expiresAt || null,
        profile: obj.profile || obj.idTokenClaims || null,
      });
    }
  };
  try {
    for (let i = 0; i < localStorage.length; i++) {
      const key = localStorage.key(i);
      if (!key) continue;
      keys.push(key);
      if (!/oidc|keycloak|token|kc-|shadowbot|user:/i.test(key)) continue;
      let raw = localStorage.getItem(key);
      if (!raw) continue;
      try {
        push('localStorage:' + key, JSON.parse(raw));
      } catch (e) {
        if (typeof raw === 'string' && raw.split('.').length === 3) {
          tokens.push({ source: 'localStorage:' + key, access_token: raw, refresh_token: null });
        }
      }
    }
  } catch (e) {}
  try {
    for (let i = 0; i < sessionStorage.length; i++) {
      const key = sessionStorage.key(i);
      if (!key) continue;
      if (!/oidc|keycloak|token|kc-|shadowbot|user:/i.test(key)) continue;
      let raw = sessionStorage.getItem(key);
      if (!raw) continue;
      try {
        push('sessionStorage:' + key, JSON.parse(raw));
      } catch (e) {}
    }
  } catch (e) {}
  return { tokens, keys };
}
"""
