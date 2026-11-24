# LinkedIn Sales Navigator MCP — reference

Read when wiring tools, auth, or paths. Keep [SKILL.md](SKILL.md) lean.

## Tools

| Need | Tool |
|------|------|
| Login / refresh | `salesnav_auth` |
| Import cookies | `salesnav_import_cookies` |
| Who am I? | `salesnav_whoami` |
| Search leads | `salesnav_search_leads` |
| Search companies | `salesnav_search_companies` |
| Lead profile | `salesnav_get_profile` |
| Company | `salesnav_get_company` |
| Saved lists | `salesnav_list_saved_lists` / `salesnav_get_saved_list` |
| Browser URL | `salesnav_search_from_url` |

## Paths

- MCP config: `~/mcps/linkedin-sales-navigator/mcp.json`
- Setup: `~/mcps/linkedin-sales-navigator/SETUP.md`
- Shared Chrome profile: `~/mcps/mcp-chrome/profile` (CDP **9222**)
- Territory skill: `~/.cursor/skills/salesnav-territory-harvest/`
- ZoomInfo skill: `~/.cursor/skills/zoominfo-territory-harvest/`

## Auth / tabs

- One MCP Chrome window; reuse the Sales Nav tab on re-auth; new tab only if none exists.
- If already on `/sales/home` or `/sales/homepage`, harvest cookies with `navigate=False`.
- Do **not** open `linkedin.com/login` when `li_at` exists.
- Cookie-Editor JSON → `salesnav_import_cookies` as fallback.

## Territory accounts flow

1. RHSC list view → `output/*_accounts.csv` / accounts JSON
2. Run **salesnav-territory-harvest** `install_login_agent` / `run_loop`
3. Resume from `{prefix}_persona_harvest_progress.json`
4. Copy deliverables to `~/Downloads/` when user asks

## Do not

- Start legacy `run_paced_harvest.sh` long sleep supervisors
- End-of-run 429 retry bursts
- Mix ZoomInfo MCP calls into this skill’s harvest path
- Put full lead lists or mobiles into chat
