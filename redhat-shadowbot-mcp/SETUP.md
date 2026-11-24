# Setup — Red Hat Shadowbot MCP (associates)

For **Red Hat associates** with existing Sales Assistant (Shadowbot) access. Cursor uses your associate browser session. You sign in with **associate SSO** (auth.redhat.com) and **FreeOTP** in Chrome.

**Easiest path for other associates:** send `redhat-shadowbot-mcp.zip` (`./pack.sh`). They drag it into a Cursor Agent chat and send. `AGENTS.md` in the zip is the install. Do not send an open-ended “create/figure out Shadowbot” prompt.

## Requirements

- You are a Red Hat associate with Sales Assistant access already (this MCP does not grant it)
- Cursor (Agent mode)
- Google Chrome
- Python 3.12+ (`python3.12` on PATH, or Homebrew `/opt/homebrew/bin/python3.12`)
- FreeOTP (same token as other Red Hat apps)

Never paste your associate password or OTP into chat.

This MCP uses a **dedicated** Chrome profile (port **9225**), separate from Sales Cloud (9223) and Slack (9224).

## 1. Install

Default location: `~/mcps/shadowbot-assistant`

```bash
cd ~/mcps/shadowbot-assistant
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
```

## 2. Optional config

```bash
cp config.example.json config.json
```

| Key | Default |
|-----|---------|
| `start_url` | `https://shadowbot.io.redhat.com/agents/sales-assistant` |
| `langgraph_api_url` | `https://api.enterprise.redhat.com/sales-assistant` |
| `assistant_id` | `sales_assistant_v2` |
| `sso_base_url` | `https://auth.redhat.com/auth` |
| `sso_realm` | `EmployeeIDP` |
| `sso_client_id` | `shadowbot-ui` |
| `cdp_port` | `9225` |
| `login_timeout_seconds` | `600` |
| `run_timeout_seconds` | `300` |

## 3. Register in Cursor

Merge this into `~/.cursor/mcp.json` (use your real home path):

```json
"shadowbot-assistant": {
  "command": "/<HOME>/mcps/shadowbot-assistant/.venv/bin/python",
  "args": ["/<HOME>/mcps/shadowbot-assistant/mcp_server.py"]
}
```

Copy the skill:

```bash
cp -R skills/redhat-shadowbot ~/.cursor/skills/
```

Reload MCP in **Cursor Settings → MCP**. You should see tools named `shadowbot_*`.

## 4. First login (associate SSO)

```bash
~/mcps/shadowbot-assistant/.venv/bin/python -m src.cli auth
```

Or in Cursor: ask the agent to call `shadowbot_auth`.

1. Chrome opens (profile under `profiles/default`).
2. Sign in with your **Red Hat associate** account.
3. Enter your **FreeOTP** code.
4. Wait until Sales Assistant is visible.

Chrome **stays open**. Leave it running so the next FreeOTP prompt is that same window.

## 5. When Shadowbot kicks you out

1. Ask the agent to call `shadowbot_auth`, or run `python -m src.cli auth`.
2. In Chrome, finish associate SSO + FreeOTP again.
3. Retry the original request.

## Troubleshooting

| Symptom | What to do |
|---------|------------|
| `Chrome not found` | Install Google Chrome |
| Python / `mcp` install fails | Use Python 3.12+, not macOS 3.9 |
| Keycloak login page instead of Sales Assistant | Finish associate SSO + FreeOTP |
| Tool says login required but Chrome is on Shadowbot | Call `shadowbot_auth` with `force=true` |
| Session expired | Associate SSO + FreeOTP, then `shadowbot_auth` |
| Empty answer | Call `shadowbot_get_thread` with the returned `thread_id` |
