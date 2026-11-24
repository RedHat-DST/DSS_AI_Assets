# LinkedIn Sales Navigator MCP — Setup

## 1. Install (one time)

```bash
cd ~/mcps/linkedin-sales-navigator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

## 2. Register in Cursor

Merge into `~/.cursor/mcp.json` (or copy the block from `mcp.json` in this folder):

```json
"linkedin-sales-navigator": {
  "command": "/Users/alexandrumarcov/mcps/linkedin-sales-navigator/.venv/bin/python",
  "args": ["/Users/alexandrumarcov/mcps/linkedin-sales-navigator/mcp_server.py"],
  "env": {
    "SALESNAV_CDP_PORT": "9224",
    "SALESNAV_SALES_URL": "https://www.linkedin.com/sales/homepage"
  }
}
```

Reload MCP servers in Cursor after saving.

## 3. First-time auth (one time per machine)

**Option A — MCP Chrome (recommended)**

1. In Cursor chat, run or ask: `salesnav_auth` with `wait: true`
2. Use the **separate Chrome window** that opens (not your daily Chrome)
3. Sign in to LinkedIn → open `linkedin.com/sales` → wait for Sales Navigator home
4. Call `salesnav_whoami` to confirm

**Option B — Cookie import**

1. In your regular Chrome, open `linkedin.com/sales` while logged in
2. Cookie-Editor extension → Export JSON
3. `salesnav_import_cookies` with that JSON

## 4. Initial prompt (paste into a new Cursor chat)

Use this once after MCP is registered and auth is done:

```
You have linkedin-sales-navigator and salescloud-assistant MCPs.

Territory workflow — run unconditionally, no pauses, no asking me to confirm shell commands:

1. Pull my territory accounts from RHSC (Sales Cloud list view "My Territory Accounts" or equivalent).
2. Export accounts to ~/mcps/linkedin-sales-navigator/output/ as JSON + CSV.
3. Harvest Cloud/CCSP personas per account via Sales Navigator using the browser client
   (scripts/territory_persona_harvest.py). Never sleep on rate limits — skip and retry at end.
4. Keep MCP Chrome on linkedin.com/sales. Do not open linkedin.com/login if already signed in.
5. Copy final CSVs to ~/Downloads when done.

If session expires, refresh from MCP Chrome only — do not destroy the session by navigating to login.
Complete the full list without stopping for approval.
```

## 5. Territory harvest (CLI)

Resumes from checkpoint automatically:

```bash
cd ~/mcps/linkedin-sales-navigator
.venv/bin/python scripts/territory_persona_harvest.py --delay 2.0
```

Outputs:

| File | Content |
|------|---------|
| `output/nl_core_territory2_accounts.csv` | RHSC territory accounts |
| `output/nl_core_territory2_cloud_ccsp_personas.csv` | Cloud/CCSP leads |
| `output/persona_harvest_progress.json` | Resume checkpoint |

## 6. MCP tools

| Tool | Purpose |
|------|---------|
| `salesnav_auth` | Sign in / refresh session |
| `salesnav_import_cookies` | Import cookies from regular Chrome |
| `salesnav_whoami` | Current user + Chrome status |
| `salesnav_search_leads` | Keyword lead search |
| `salesnav_search_companies` | Company search |
| `salesnav_get_profile` | Lead profile |
| `salesnav_get_company` | Company profile |
| `salesnav_list_saved_lists` | Saved lists |
| `salesnav_get_saved_list` | List members |
| `salesnav_search_from_url` | Run a browser search URL |

## Notes

- **MCP Chrome** = profile `profiles/default`, CDP port **9224**
- API calls use **in-browser fetch** (`src/browser_client.py`) — do not copy cookies to httpx for bulk jobs
- Requires active **Sales Navigator** subscription (`li_a` cookie)
