---
name: salesnav-territory-harvest
description: >-
  Harvest LinkedIn Sales Navigator contacts for RHSC territory accounts.
  Default standalone mode: Cloud/CCSP personas. When used via AE GTM Superpack /
  NotebookLM Account OS, prefer opportunity-driven title/role targets from
  opportunity_contact_targets.json (not Cloud/CCSP) unless the user explicitly
  asks for territory Cloud/CCSP harvest.
---

# Sales Nav territory harvest

RHSC accounts → SN company-filtered search → revenue CSVs. **Sales Nav only** (phones via `zoominfo-territory-harvest`).

## Mode

| Context | Behavior |
|---------|----------|
| Superpack / Account OS (hub D/E) | Opp-driven: `opportunity_contact_targets.json` → `salesnav_search_leads` per motion; respect `exclude`; CSVs → hub. See `OPPORTUNITY_DRIVEN_HARVEST.md`. |
| User says `Harvest Cloud/CCSP` / `territory cloud personas` | Cloud/CCSP territory pipeline below |

## Compliance (save chat tokens)

Follow `ae-gtm-compliance-mitigations`:

- `scripts/check_compliance_gate.sh` runs before harvest (Privacy Mode + AE affirmation). Hard-stop if off.
- Full CSVs → **output/Downloads only**. Chat = **counts + ≤5 sample names**.
- Associate MCP Chrome SSO only. Status: `scripts/status_brief.sh` one-liners.
- Combined SN+ZI roles: `scripts/export_combined_persona_roles.py` (no mobile in chat).
- SN has no phones — after ZI harvest: `zoominfo-territory-harvest` `enrich_until_budget.sh --max-credits 1000`.

## Start (Cloud/CCSP territory)

```bash
chmod +x ~/.cursor/skills/salesnav-territory-harvest/scripts/*.sh
~/.cursor/skills/salesnav-territory-harvest/scripts/install_login_agent.sh \
  --accounts <accounts.json> \
  --output ~/mcps/salesnav-territory-harvest/output \
  --territory-id <TERR_ID> \
  --prefix <prefix>
```

Pipeline: **session check → paced harvest → revenue buckets → DONE**. LaunchAgent resumes after logout/429.

One-shot: `scripts/run_loop.sh` with same flags. Before first slot: `salesnav_auth` (wait) → `salesnav_whoami` (authenticated + cookie).

## Hard rules

- Run without confirmation; Auto-review → retry once smart-mode, continue.
- Never `--fresh` unless asked. Prefer `run_loop` / LaunchAgent — **not** legacy `run_paced_harvest.sh`.
- On **429**: defer (no end-of-run retry). On **401**: stop batch; re-auth; next slot resumes.
- Completion = **unique** account names in `done[]`.

## Done when

Unique accounts in `done[]`; both revenue bucket CSVs in Downloads; `{slug}_salesnav_DONE` / agent unloaded.

## Detail (read only if needed)

[reference.md](reference.md) — stall-proof defaults, LaunchAgent ops, outputs, failure modes, checklist.
