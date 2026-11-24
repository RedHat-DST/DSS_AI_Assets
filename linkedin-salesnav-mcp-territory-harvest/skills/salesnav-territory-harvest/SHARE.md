# Share this skill (turnkey) — Sales Navigator only

## What to send the recipient

1. **File:** `salesnav-territory-harvest-skill.tar.gz`
2. **Message:** paste the block from `TURNKEY-PROMPT.md` (PROMPT START → PROMPT END)

They open a **new Cursor chat**, attach the tarball, paste the prompt, and let the agent run `install.sh`.

**Do not** combine with ZoomInfo in the same prompt — send `zoominfo-territory-harvest-skill.tar.gz` separately.

## Rebuild the tarball (after edits)

```bash
cd ~/.cursor/skills
tar -czf ~/Desktop/salesnav-territory-harvest-skill.tar.gz salesnav-territory-harvest
cp ~/Desktop/salesnav-territory-harvest-skill.tar.gz ~/Downloads/ 2>/dev/null || true
```

## What the recipient gets

| Step | Handled by |
|------|------------|
| Extract skill | Prompt |
| Skill files + scripts | `install.sh` |
| Sales Nav MCP check / venv | `install.sh` |
| mcp.json wiring | `install.sh` |
| Chrome SSO | User once via `salesnav_auth` |
| Territory harvest + login resume | `install_login_agent.sh` |

## Optional Slack/email blurb

> Attached: Sales Navigator territory harvest skill (turnkey).
> 1. Open a new Cursor chat
> 2. Attach the `.tar.gz`
> 3. Paste the prompt from TURNKEY-PROMPT.md
> 4. Let the agent install; sign into Sales Nav in MCP Chrome when asked
> 5. Give it your territory accounts file to start a harvest
>
> ZoomInfo is a **separate** package — do not mix.
