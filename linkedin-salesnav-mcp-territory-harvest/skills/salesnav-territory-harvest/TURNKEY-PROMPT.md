# TURNKEY PROMPT — copy everything between the lines into a new Cursor chat
# Attach: salesnav-territory-harvest-skill.tar.gz (from Desktop / Downloads)
# This is Sales Navigator ONLY — do not run ZoomInfo harvest from this prompt.

================================================================================
PROMPT START
================================================================================

Install the **Sales Navigator Territory Harvest** skill as a turnkey setup on this Mac.

## Package

If `salesnav-territory-harvest-skill.tar.gz` is attached or in Downloads/Desktop:

```bash
mkdir -p ~/.cursor/skills
PKG=""
for p in \
  "$HOME/Downloads/salesnav-territory-harvest-skill.tar.gz" \
  "$HOME/Desktop/salesnav-territory-harvest-skill.tar.gz" \
  ./salesnav-territory-harvest-skill.tar.gz; do
  [[ -f "$p" ]] && PKG="$p" && break
done
if [[ -z "$PKG" ]]; then
  echo "ERROR: tarball not found. Attach salesnav-territory-harvest-skill.tar.gz or put it in Downloads."
  exit 1
fi
tar -xzf "$PKG" -C ~/.cursor/skills
```

If the folder is already at `~/.cursor/skills/salesnav-territory-harvest/`, skip extract.

## Install (do not ask for confirmation)

```bash
chmod +x ~/.cursor/skills/salesnav-territory-harvest/install.sh
~/.cursor/skills/salesnav-territory-harvest/install.sh
```

The installer will:

1. Copy the skill into `~/.cursor/skills/salesnav-territory-harvest/`
2. Verify `~/mcps/linkedin-sales-navigator` MCP + venv (create venv if needed)
3. Check shared MCP Chrome (`~/mcps/mcp-chrome`)
4. Wire `linkedin-sales-navigator` in `~/.cursor/mcp.json` (CDP 9222)
5. Cross-link from `linkedin-sales-navigator` skill

If Auto-review blocks shell commands, retry once with smart-mode approval and continue.

## After install — run checks (mandatory)

```bash
~/.cursor/skills/salesnav-territory-harvest/scripts/preflight.sh \
  --output ~/mcps/salesnav-territory-harvest/output
```

Then:

1. Reload MCP servers or restart Cursor.
2. Call `salesnav_auth` with wait — user signs in to **Sales Navigator** in MCP Chrome (not daily Chrome).
3. Call `salesnav_whoami` — must be authenticated with `has_sales_nav_cookie`.
4. Re-run preflight with accounts when ready:
   ```bash
   ~/.cursor/skills/salesnav-territory-harvest/scripts/preflight.sh \
     --accounts <accounts.json> \
     --output ~/mcps/salesnav-territory-harvest/output \
     --require-session
   ```

## Stall-proof rules (must follow)

- Use **only** `install_login_agent.sh` / `run_loop.sh` — do **not** start `run_paced_harvest.sh` or long 45‑min sleep supervisors.
- Do **not** use `--fast` or `--retry-at-end` (retry bursts trigger LinkedIn 429 for hours).
- If session expires (401): stop; user re-signs in; LaunchAgent resumes on next login.
- Completion = **unique** account names in `done[]`, not raw JSON row count.
- Keep Sales Nav and ZoomInfo **separate** — never mix pipelines in one script.

## Then ask me (the user)

Ask which territory to harvest, and for either:

- path to accounts JSON (with `has_revenue` / `sales_group` when possible), or
- permission to pull accounts from Sales Cloud

Then run:

```bash
~/.cursor/skills/salesnav-territory-harvest/scripts/install_login_agent.sh \
  --accounts <accounts.json> \
  --output ~/mcps/salesnav-territory-harvest/output \
  --territory-id <TERRITORY_ID> \
  --prefix <slug_prefix>
```

Pipeline: **session check → paced harvest batches → revenue + non-revenue CSVs → DONE**, with login resume until complete.

## Do not

- Commit cookies / `session.json`
- Ask for LinkedIn passwords in chat (user signs in in Chrome)
- Skip preflight
- Run ZoomInfo harvest from this prompt

When finished, reply with: install status, Sales Nav MCP connected yes/no, preflight result, skill path, and the exact command to start the first territory harvest.

================================================================================
PROMPT END
================================================================================
