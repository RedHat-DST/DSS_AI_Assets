---
name: browser-tab-login
description: >-
  Shared MCP Chrome login UX: one window (CDP 9222), reuse the matching service
  tab on re-auth, open a new tab only when that service has no tab yet. Use for
  Sales Nav, Sales Cloud, Supportable, Shadowbot, Slack, NotebookLM auth, or
  when Chrome opens duplicate login tabs / restores many tabs on restart.
---

# Browser tab login behaviour

**Code:** `~/mcps/mcp-chrome/shared.py`  
**Origin:** shared MCP Chrome (one window) — optimized to stop duplicate tabs.

## Rules (agents)

1. **One window** — MCP Chrome CDP **9222**, profile `~/mcps/mcp-chrome/profile`. Never spawn a second Chrome for SSO / Sales Nav / Supportable / Shadowbot / Slack / NotebookLM.
2. **Reuse first** — on `*_auth` with navigate, **reuse** an existing tab whose URL matches that service. Do **not** open another login tab for the same service.
3. **New tab only if needed** — open a new tab only when no matching service tab exists (first auth for that app).
4. **Do not hijack unrelated tabs** — never navigate a Sales Nav tab into Sales Cloud (or similar). Matching is by URL hints in `SERVICE_URL_HINTS`.
5. **No `/login` when already signed in** — if cookies/`whoami` show a valid session, harvest with `navigate=False`.
6. **No session restore flood** — MCP Chrome must start with New Tab only (prefs `restore_on_startup=5`), not “continue where you left off”.
7. **ClosePlan Aura ≠ login Chrome** — Lightning Aura/Playwright for ClosePlan MEDDPICC often uses CDP **9223**. Do not conflate with shared login **9222**.
8. **Daily Chrome is separate** — user signs in in the MCP Chrome window that auth opened, not everyday Chrome (unless cookie import).

## What the AE sees

| Action | Expected |
|--------|----------|
| First `salesnav_auth` / `salescloud_auth` / … | One MCP Chrome window; one tab for that service |
| Later re-auth for the **same** service | Same tab reused — **no** extra tab |
| Auth for a **different** service | New tab in the **same** window |
| MCP Chrome restarted | Starts clean (blank/new tab), not 20 old tabs |

## Agent checklist when auth fails or tabs explode

1. Confirm CDP: `curl -sf http://127.0.0.1:9222/json/version`
2. Call the service `*_auth` once with `wait=true` — tell the AE which window/tab to use
3. If many blank/duplicate tabs: stop looping auth; reuse is automatic after this skill’s code path
4. If Auto-review blocks shell/auth scripts: retry once with smart-mode approval
5. Cookie import fallback only when browser login keeps failing (Sales Nav: `salesnav_import_cookies`)

## Code entry points

| Piece | Path |
|-------|------|
| Shared spawn + reuse | `~/mcps/mcp-chrome/shared.py` → `spawn_chrome_cdp`, `connect_over_cdp` |
| Sales Nav | `~/mcps/linkedin-sales-navigator/src/chrome.py` |
| Sales Cloud | `~/mcps/salescloud-assistant/src/chrome.py` |
| Supportable | `~/mcps/supportable-assistant/src/chrome.py` |
| Shadowbot | `~/mcps/shadowbot-assistant/src/chrome.py` |
| Slack | `~/mcps/slack-assistant/src/chrome.py` |

`connect_over_cdp(..., new_tab=True, match_url_substrings=…)` means: **reuse match if any, else new tab**.

**Focus:** `bring_to_front` defaults to **False** so harvest/session probes do not steal the AE's current window. Only pass `bring_to_front=True` for interactive login when the AE must see the auth tab.
