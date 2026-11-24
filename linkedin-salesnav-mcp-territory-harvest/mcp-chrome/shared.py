"""Shared MCP Chrome — one window, reuse service tabs for RH SSO / Sales Nav / etc.

Policy (QoL):
  1. One Chrome window (CDP 9222, profile ~/mcps/mcp-chrome/profile) — not daily Chrome.
  2. Auth NEVER opens a second window.
  3. Prefer REUSE of an existing tab that already matches the service URL.
  4. Open a NEW tab only when no matching tab exists (first auth for that service).
  5. Do not restore the previous session of many tabs on restart.
  6. ClosePlan Lightning Aura may use CDP 9223 separately — do not conflate.

Override:
  MCP_CHROME_CDP_PORT=9222
  MCP_CHROME_PROFILE=~/mcps/mcp-chrome/profile
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

MCP_CHROME_ROOT = Path.home() / "mcps" / "mcp-chrome"
DEFAULT_CDP_PORT = 9222
DEFAULT_PROFILE = MCP_CHROME_ROOT / "profile"

_LEGACY_PROFILES = (
    Path.home() / "mcps" / "linkedin-sales-navigator" / "profiles" / "default",
    Path.home() / "mcps" / "salescloud-assistant" / "profiles" / "default",
    Path.home() / "mcps" / "supportable-assistant" / "profiles" / "default",
    Path.home() / "mcps" / "shadowbot-assistant" / "profiles" / "default",
    Path.home() / "mcps" / "slack-assistant" / "profiles" / "default",
)

# Common URL fragments for matching an existing service tab
SERVICE_URL_HINTS: dict[str, tuple[str, ...]] = {
    "salesnav": ("linkedin.com/sales", "linkedin.com/feed", "linkedin.com/in/"),
    "salescloud": (
        "redhatcrm.lightning.force.com",
        ".lightning.force.com",
        "login.salesforce.com",
        "auth.redhat.com",
    ),
    "supportable": ("supportable.corp.redhat.com", "redhat.ssogen.com", "auth.redhat.com"),
    "shadowbot": ("shadowbot.io.redhat.com", "auth.redhat.com"),
    "slack": ("enterprise.slack.com", "app.slack.com", "slack.com", "auth.redhat.com"),
    "notebooklm": ("notebooklm.google.com", "notebook.google.com"),
    "zoominfo": ("zoominfo.com",),
}


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def resolve_cdp_port(service_env: str | None, config_port: int | None = None) -> int:
    if v := os.environ.get("MCP_CHROME_CDP_PORT"):
        return int(v)
    if service_env and (v := os.environ.get(service_env)):
        return int(v)
    if config_port is not None:
        return int(config_port)
    return DEFAULT_CDP_PORT


def resolve_profile(
    service_env: str | None,
    config_profile: Path | str | None = None,
) -> Path:
    if v := os.environ.get("MCP_CHROME_PROFILE"):
        return Path(v).expanduser().resolve()
    if service_env and (v := os.environ.get(service_env)):
        return Path(v).expanduser().resolve()
    if config_profile is not None:
        return Path(config_profile).expanduser().resolve()
    return DEFAULT_PROFILE.resolve()


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
    raise FileNotFoundError(
        "Google Chrome not found. Install Chrome, then retry the assistant auth tool."
    )


def _profile_mtime(profile: Path) -> float:
    cookies = profile / "Default" / "Cookies"
    local_state = profile / "Local State"
    best = 0.0
    for path in (cookies, local_state):
        try:
            best = max(best, path.stat().st_mtime)
        except OSError:
            pass
    return best


def seed_profile_if_empty(profile: Path) -> None:
    """Copy the newest legacy per-assistant profile into the shared profile once."""
    if (profile / "Default").exists():
        return
    candidates = [p for p in _LEGACY_PROFILES if (p / "Default").exists()]
    if not candidates:
        return
    source = max(candidates, key=_profile_mtime)
    log(f"Seeding shared MCP Chrome profile from {source}")
    shutil.copytree(source, profile, symlinks=True)


def ensure_no_session_restore(profile: Path) -> None:
    """Stop Chrome from reopening dozens of tabs on every MCP Chrome start.

    Sets Preferences session.restore_on_startup = 5 (Open New Tab page).
    Safe to call while Chrome is down; skipped if Preferences missing/unreadable.
    """
    prefs_path = profile / "Default" / "Preferences"
    if not prefs_path.exists():
        return
    try:
        data = json.loads(prefs_path.read_text(encoding="utf-8"))
    except Exception as e:
        log(f"Preferences read skipped: {e}")
        return

    session = data.setdefault("session", {})
    # 5 = Open the New Tab page (do NOT continue where you left off)
    changed = False
    if session.get("restore_on_startup") != 5:
        session["restore_on_startup"] = 5
        changed = True
    if "startup_urls" in session and session["startup_urls"]:
        session["startup_urls"] = []
        changed = True

    # Account-level override sometimes wins
    try:
        acct = data.setdefault("account_values", {}).setdefault("session", {})
        if acct.get("restore_on_startup") != 5:
            acct["restore_on_startup"] = 5
            changed = True
    except Exception:
        pass

    if not changed:
        return
    try:
        prefs_path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")
        log("MCP Chrome prefs: disable session restore (open New Tab only)")
    except Exception as e:
        log(f"Preferences write skipped: {e}")


def spawn_chrome_cdp(profile: Path, port: int) -> int | None:
    """Start Chrome with remote debugging. Return pid if spawned, else None if already up."""
    if cdp_alive(port):
        log(f"Reusing existing MCP Chrome CDP on port {port}")
        return None

    seed_profile_if_empty(profile)
    profile.mkdir(parents=True, exist_ok=True)
    ensure_no_session_restore(profile)

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
        # Fresh window: one blank tab — do not reload prior session
        "--new-window",
        "about:blank",
    ]
    log(f"Starting MCP Chrome for CDP (port={port}) profile={profile}")
    proc = subprocess.Popen(
        args,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    deadline = time.time() + 30
    while time.time() < deadline:
        if cdp_alive(port):
            log(f"MCP Chrome CDP ready (pid={proc.pid})")
            return proc.pid
        if proc.poll() is not None:
            raise RuntimeError(f"Chrome exited early with code {proc.returncode}")
        time.sleep(0.4)
    raise RuntimeError(f"Timed out waiting for Chrome CDP on port {port}")


def page_url(page: Any) -> str:
    try:
        return page.url or ""
    except Exception:
        return ""


def find_matching_page(pages: Sequence[Any], url_substrings: Sequence[str]) -> Any | None:
    """Return first page whose URL contains any of the substrings (case-insensitive)."""
    if not pages or not url_substrings:
        return None
    needles = [s.lower() for s in url_substrings if s]
    ranked: list[tuple[int, Any]] = []
    for p in pages:
        url = page_url(p).lower()
        if not url or url == "about:blank":
            continue
        hits = sum(1 for n in needles if n in url)
        if hits:
            ranked.append((hits, p))
    if not ranked:
        return None
    ranked.sort(key=lambda x: x[0], reverse=True)
    return ranked[0][1]


async def close_extra_blank_tabs(context: Any, keep: Any | None = None) -> int:
    """Close surplus about:blank tabs. Returns how many were closed."""
    closed = 0
    try:
        pages = list(context.pages)
    except Exception:
        return 0
    blanks = [p for p in pages if page_url(p) in ("", "about:blank")]
    # Keep at least one page alive; prefer keeping `keep` if it is blank
    for p in blanks:
        if keep is not None and p is keep:
            continue
        if len(list(context.pages)) <= 1:
            break
        try:
            await p.close()
            closed += 1
        except Exception:
            continue
    if closed:
        log(f"Closed {closed} surplus about:blank tab(s)")
    return closed


async def connect_over_cdp(
    playwright,
    port: int,
    *,
    new_tab: bool = False,
    match_url_substrings: Sequence[str] | None = None,
    pick_best: Optional[Callable[[list[Any]], Any]] = None,
    bring_to_front: bool = False,
):
    """Connect to MCP Chrome and pick a page with reuse-first QoL.

    - If a tab matches ``match_url_substrings`` → reuse it (never open a duplicate).
    - Else if ``new_tab`` → open one new tab (first login for that service).
    - Else → ``pick_best(pages)`` or first page or new page.

    ``bring_to_front`` defaults to False so background harvests / probes do not
    steal macOS focus from the AE's current window. Pass True only for
    interactive login when the AE needs to see the auth tab.
    """
    endpoint = cdp_endpoint(port)
    log(f"Connecting Playwright over CDP -> {endpoint}")
    browser = await playwright.chromium.connect_over_cdp(endpoint)
    if browser.contexts:
        context = browser.contexts[0]
    else:
        context = await browser.new_context()

    pages = list(context.pages)
    page = None
    reused = False

    if match_url_substrings:
        page = find_matching_page(pages, match_url_substrings)
        if page is not None:
            reused = True
            log(f"Reusing service tab -> {page_url(page)[:100]}")

    if page is None and new_tab:
        page = await context.new_page()
        log("Opened new tab (no matching service tab)")
    elif page is None:
        if pick_best is not None:
            page = pick_best(pages)
        if page is None and pages:
            page = pages[0]
        if page is None:
            page = await context.new_page()

    if bring_to_front:
        try:
            await page.bring_to_front()
        except Exception:
            pass

    # Tidying blanks only when we reused or just created — cheap QoL
    if reused or new_tab:
        try:
            await close_extra_blank_tabs(context, keep=page)
        except Exception:
            pass

    return browser, context, page
