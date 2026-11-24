# Red Hat Shadowbot Assistant (Sales Assistant)

A CLI and MCP server for **Red Hat associates** to prompt **Sales Assistant** at [shadowbot.io.redhat.com/agents/sales-assistant](https://shadowbot.io.redhat.com/agents/sales-assistant) as themselves. Same shape as the Slack and Sales Cloud assistants.

Auth is **associate SSO** (auth.redhat.com) + **FreeOTP**. Chrome stays open so you can FreeOTP in that same window. Prompts go to the LangGraph agent `sales_assistant_v2`.

## Features

- Named MCP tools (`shadowbot_ask`, `shadowbot_list_threads`, …)
- Persistent Chrome profile — Chrome stays open between calls
- Continues the last conversation unless you start a new thread
- CLI for the same operations (`python -m src.cli`)

## Share with other associates

They **drag the zip into a Cursor Agent chat**. No paste prompt — `AGENTS.md` in the zip is the install.

```bash
./pack.sh   # writes share/redhat-shadowbot-mcp.zip
```

See [SHARE.md](SHARE.md). After install: `Ask Shadowbot: <question>` (one `shadowbot_ask`).

## Quick start

See [SETUP.md](SETUP.md).

```bash
cd ~/mcps/shadowbot-assistant
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium
.venv/bin/python -m src.cli auth
```

A Chrome window opens. Sign in with your Red Hat associate account and FreeOTP. When Sales Assistant loads, the CLI harvests your Keycloak token.

## MCP tools

| Tool | Description |
|------|-------------|
| `shadowbot_auth` | Open Chrome; complete SSO + FreeOTP; harvest session |
| `shadowbot_whoami` | Current associate + session status |
| `shadowbot_ask` | Prompt Sales Assistant; returns the reply |
| `shadowbot_list_threads` | Recent conversations |
| `shadowbot_get_thread` | Messages in a thread |

## Auth when you get kicked out

1. Call `shadowbot_auth` (wait=true).
2. Complete Red Hat SSO and FreeOTP in the **already-open Chrome window**.
3. Retry the original tool.

Do not paste passwords or OTP codes into chat.

## CLI

```bash
.venv/bin/python -m src.cli auth
.venv/bin/python -m src.cli whoami
.venv/bin/python -m src.cli ask "What can Sales Assistant do for me?"
.venv/bin/python -m src.cli ask "Catch me up on account Microsoft" --new
.venv/bin/python -m src.cli threads
```

## Layout

```
mcp_server.py      # Cursor MCP entrypoint
src/auth.py        # Chrome SSO + Keycloak token harvest
src/langgraph.py   # LangGraph threads / runs
src/ops.py         # High-level tools
src/cli.py         # click CLI
profiles/default   # Persistent Chrome profile (gitignored)
session.json       # Harvested token (gitignored, chmod 600)
```
