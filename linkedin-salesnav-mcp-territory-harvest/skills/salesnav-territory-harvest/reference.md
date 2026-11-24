# Sales Nav territory harvest — reference

Read when debugging, rate-limited, or checking DONE criteria. Keep [SKILL.md](SKILL.md) lean.

## Prerequisites

1. Sales Nav MCP at `~/mcps/linkedin-sales-navigator` (installer wires it).
2. Shared MCP Chrome (`~/mcps/mcp-chrome`, CDP **9222** by default).
3. Accounts JSON with RHSC enrichment when possible (`has_revenue`, `sales_group`, `global_arr_usd`).

## Pipeline phases

| Phase | What | Resume key |
|-------|------|------------|
| 1 Session | MCP Chrome signed in at `linkedin.com/sales` | `salesnav_whoami` / cookie harvest |
| 2 Harvest | Resolve companies + Cloud/CCSP leads | `{prefix}_persona_harvest_progress.json` `done[]` |
| 3 Export | Combined + revenue / non-revenue CSVs | `{slug}_salesnav_DONE` |

## Stall-proof defaults

| Setting | Value | Why |
|---------|-------|-----|
| Delay between accounts | 6s + 0–4s jitter | Avoid velocity 429 |
| Request delay | 2.5s + jitter | Resolve + search + refine |
| Max accounts / batch | 25 | Short cycles — close Chrome between slots |
| Batch pause inside run | 90s (not 10 min) | Turnkey loop shouldn't hang |
| Consecutive 429 stop | 3 | Circuit breaker — no retry burst |
| End-of-run retry | **off** | Retry burst caused full day of 429s |
| Completion metric | **unique** account names | Territory lists can have duplicate rows |
| No session | skip batch, exit 0 | LaunchAgent resumes next login — no Chrome flash loop |

## Login resume

1. LaunchAgent `com.redhat.salesnav-harvest.<slug>` with `RunAtLoad=true`
2. `run_loop.sh` resumes from progress JSON
3. On DONE → writes `{slug}_salesnav_DONE` and unloads agent

```bash
launchctl print gui/$(id -u)/com.redhat.salesnav-harvest.<slug> 2>/dev/null | head -8
tail -30 ~/mcps/salesnav-territory-harvest/output/<slug>_salesnav_loop.log
launchctl bootout gui/$(id -u)/com.redhat.salesnav-harvest.<slug>   # disable early
```

## Outputs (Downloads)

Folder: `~/Downloads/<TERRITORY_ID>_salesnav_revenue_buckets/`

- `<TERRITORY_ID>_revenue_generating_personas.csv`
- `<TERRITORY_ID>_non_revenue_generating_personas.csv`
- Matching `*_accounts.csv` / `*.json`

Also under `output/`: `{prefix}_cloud_ccsp_personas_*.csv`

## Phones (ZoomInfo)

Sales Nav does not return phones. After ZI Cloud/CCSP harvest:

```bash
~/.cursor/skills/zoominfo-territory-harvest/scripts/enrich_until_budget.sh \
  --output ~/mcps/linkedin-sales-navigator/output \
  --territory-id <TERRITORY_ID> \
  --max-credits 1000
```

Re-export ZI CSVs after enrich. See `zoominfo-territory-harvest` skill.

## Combined SN+ZI role export

```bash
~/.cursor/skills/salesnav-territory-harvest/scripts/export_combined_persona_roles.py
```

No mobile column in chat-facing exports.

## Failure modes

| Symptom | Cause | Fix |
|---------|-------|-----|
| Immediate 429 on every account | Velocity throttle from prior burst | Wait hours / next UTC midnight; keep paced defaults |
| HTTP 401 / session expired | MCP Chrome logged out | `salesnav_auth`, sign in at `/sales` |
| Black flashing Chrome | Script reconnecting while session invalid | Stop harvest; single navigate; re-auth |
| Stuck at 284/438 forever | Supervisor sleeping / hung | Use skill `run_loop` + LaunchAgent, not legacy `run_paced_harvest` |
| `done` count ≠ account_count | Duplicate names in territory list | Use **unique** names (run_loop does) |
| 0 personas but resolved=True | No Cloud/CCSP titles at company | Expected for many Draft accounts |
| `no_company_match` | Sales Nav org resolve failed | Name variants / sales_group enrichment |

## Yield expectations (NL Core Terr example)

- ~65–80% of accounts searchable
- ~25–35% of accounts yield ≥1 Cloud/CCSP persona without country filter
- Revenue accounts often denser than Draft/no-ARR

## Country filter

Off by default. Enable later with `postprocess_harvest_splits.py --country-filter` if needed.

## Quality checklist

- [ ] Accounts JSON has `has_revenue` / `global_arr_usd` (warn if missing)
- [ ] Unique account names all in `done[]`
- [ ] Both revenue bucket CSVs in Downloads
- [ ] DONE marker present / agent unloaded
- [ ] Spot-check 5 high-ARR accounts for relevant titles

## Policy

Legitimate B2B prospecting only. Read-only — no InMail or connection requests.
