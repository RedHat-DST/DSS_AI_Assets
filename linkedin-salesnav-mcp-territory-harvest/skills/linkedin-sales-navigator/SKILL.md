---
name: linkedin-sales-navigator
description: >-
  Query LinkedIn Sales Navigator via the linkedin-sales-navigator MCP: lead search,
  company search, saved lists, profile lookups, and territory persona harvest.
  Use when the user asks about Sales Navigator, LinkedIn leads, prospecting, or
  account research on LinkedIn. Sessions use shared MCP Chrome (CDP 9222) — re-auth there.
---

# LinkedIn Sales Navigator MCP

Use `salesnav_*` tools. Setup: `~/mcps/linkedin-sales-navigator/SETUP.md`.

## Territory harvest

Prefer skill **salesnav-territory-harvest** (not ZoomInfo):

```bash
~/.cursor/skills/salesnav-territory-harvest/scripts/install_login_agent.sh \
  --accounts <accounts.json> \
  --output ~/mcps/salesnav-territory-harvest/output \
  --territory-id <TERR_ID> \
  --prefix <prefix>
```

Preflight (optional): `scripts/preflight.sh --accounts … --output … --require-session`.  
ZoomInfo: **zoominfo-territory-harvest** only.

## Hard rules

- Prefer `run_loop` / `install_login_agent` — **not** legacy `run_paced_harvest.sh`.
- On **429**: defer — no end-of-run retry. Auto-review → retry once smart-mode.
- Browser client via `auth.ensure_client()`. Never `/login` when already signed in.
- Tab UX: skill **browser-tab-login** (reuse matching tab; new tab only if missing).
- CDP **9222** = shared MCP Chrome. Do not conflate with ClosePlan Aura **9223**.

## Auth

1. `salesnav_auth` (`wait=true`) → sign in at `linkedin.com/sales`
2. `salesnav_whoami` to verify  
Cookie fallback: `salesnav_import_cookies`.

## Compliance

Legitimate B2B only. Read-only — no InMail / connection requests. Chat = counts + ≤5 names (full lists → files).

## Detail (read only if needed)

[reference.md](reference.md) — tool map, paths, cookie/re-auth notes.
