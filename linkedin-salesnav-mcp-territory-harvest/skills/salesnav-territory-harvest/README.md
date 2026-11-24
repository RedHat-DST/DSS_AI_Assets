# Sales Navigator Territory Harvest

Turnkey skill for Cloud/CCSP persona harvest from **LinkedIn Sales Navigator** for a Red Hat Sales Cloud territory.

**Separate from ZoomInfo.** Use `zoominfo-territory-harvest` for ZoomInfo-only runs.

## Quick start

```bash
chmod +x ~/.cursor/skills/salesnav-territory-harvest/install.sh
~/.cursor/skills/salesnav-territory-harvest/install.sh

# Sign in: salesnav_auth → linkedin.com/sales in MCP Chrome

~/.cursor/skills/salesnav-territory-harvest/scripts/preflight.sh \
  --accounts /path/to/accounts.json \
  --output ~/mcps/salesnav-territory-harvest/output \
  --require-session

~/.cursor/skills/salesnav-territory-harvest/scripts/install_login_agent.sh \
  --accounts /path/to/accounts.json \
  --output ~/mcps/salesnav-territory-harvest/output \
  --territory-id NL_COMM_TERR_CORE_POD01_TERR02 \
  --prefix nl_core_territory2
```

## Anti-stall design

- Short batches (25 accounts)
- No end-of-run 429 retry burst
- Stop after 3 consecutive rate limits
- Exit cleanly if not signed in (LaunchAgent resumes later)
- Unique account-name completion
- Preflight before start

See `SKILL.md` and `TURNKEY-PROMPT.md`.
