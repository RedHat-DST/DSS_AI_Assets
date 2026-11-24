# LinkedIn Sales Navigator MCP + territory harvest — Mac install

For **CEE / TCC** (or any) RHSC territory contact harvest in Cursor.

**Package contents**

| Path | What |
|------|------|
| `linkedin-sales-navigator/` | MCP server (Sales Nav tools) |
| `mcp-chrome/` | Shared CDP Chrome helper (`shared.py`) |
| `skills/salesnav-territory-harvest/` | Territory harvest skill + LaunchAgent loop |
| `skills/linkedin-sales-navigator/` | Cursor skill for `salesnav_*` tools |
| `skills/browser-tab-login/` | Reuse one MCP Chrome tab for SSO |

No cookies, sessions, or account data are included. You sign in with **your** Sales Nav.

---

## 1. Unpack

```bash
cd ~/Downloads   # or wherever you saved the zip
unzip linkedin-salesnav-mcp-territory-harvest.zip -d /tmp/sn-pack
mkdir -p ~/mcps ~/.cursor/skills

# MCP + Chrome helper
rsync -a /tmp/sn-pack/linkedin-salesnav-mcp-territory-harvest/linkedin-sales-navigator/ \
  ~/mcps/linkedin-sales-navigator/
rsync -a /tmp/sn-pack/linkedin-salesnav-mcp-territory-harvest/mcp-chrome/ \
  ~/mcps/mcp-chrome/

# Skills
rsync -a /tmp/sn-pack/linkedin-salesnav-mcp-territory-harvest/skills/ \
  ~/.cursor/skills/
```

## 2. Python venv (one time)

```bash
cd ~/mcps/linkedin-sales-navigator
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

## 3. Install skill wiring

```bash
chmod +x ~/.cursor/skills/salesnav-territory-harvest/install.sh
chmod +x ~/.cursor/skills/salesnav-territory-harvest/scripts/*.sh
~/.cursor/skills/salesnav-territory-harvest/install.sh
```

This wires `linkedin-sales-navigator` into `~/.cursor/mcp.json` (CDP **9222**).

**Reload MCP servers** in Cursor (or restart Cursor).

## 4. Auth (your Sales Nav)

In a Cursor chat:

1. Call `salesnav_auth` with `wait: true`
2. Sign in in the **MCP Chrome** window (not daily Chrome) → `linkedin.com/sales`
3. Call `salesnav_whoami` — expect authenticated

## 5. Harvest your CEE/TCC territory

Prepare accounts JSON (from RHSC / Sales Cloud), e.g.:

```json
{
  "territory_id": "YOUR_CEE_OR_TCC_TERR_ID",
  "accounts": [
    {"Id": "001…", "Name": "Example AS", "Website": "https://example.cz"}
  ]
}
```

Then:

```bash
mkdir -p ~/mcps/salesnav-territory-harvest/output

~/.cursor/skills/salesnav-territory-harvest/scripts/install_login_agent.sh \
  --accounts ~/path/to/your_cee_tcc_accounts.json \
  --output ~/mcps/salesnav-territory-harvest/output \
  --territory-id YOUR_CEE_OR_TCC_TERR_ID \
  --prefix cee_tcc
```

Or one-shot without LaunchAgent:

```bash
~/.cursor/skills/salesnav-territory-harvest/scripts/run_loop.sh \
  --accounts ~/path/to/your_cee_tcc_accounts.json \
  --output ~/mcps/salesnav-territory-harvest/output \
  --territory-id YOUR_CEE_OR_TCC_TERR_ID \
  --prefix cee_tcc
```

**Compliance:** Privacy Mode ON; run `scripts/check_compliance_gate.sh` / affirm before bulk harvest. Chat = counts + ≤5 sample names; full CSVs stay in `output/` / Downloads.

## 6. Cursor turnkey (optional)

Open a **new** Cursor chat, attach this zip, paste the prompt in:

`skills/salesnav-territory-harvest/TURNKEY-PROMPT.md`

---

## Troubleshooting

| Issue | Fix |
|-------|-----|
| 401 / not authenticated | `salesnav_auth` again in MCP Chrome |
| 429 rate limit | Leave LaunchAgent; it resumes later — do not hammer retries |
| Wrong Chrome | CDP must be **9222** shared MCP Chrome |
| MCP not listed | Check `~/.cursor/mcp.json` paths; reload MCP |

## Support

Ask the AE who shared this pack (Alexandru Marcov) if install fails on path/MCP wiring.
