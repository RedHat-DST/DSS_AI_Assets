# Red Hat Shadowbot MCP — associate package

Cursor MCP for **Red Hat associates** to prompt Sales Assistant (Shadowbot) as themselves. Auth is associate SSO (auth.redhat.com) + FreeOTP in a persistent Chrome window.

## What to send associates

Send **only** `redhat-shadowbot-mcp.zip` (`./pack.sh`).

They **drag the zip into a Cursor Agent chat and send.** That is the install. `AGENTS.md` in the zip tells the agent what to do. No extra prompt.

They must already have Sales Assistant access. This package does not grant it.

## Contents

```
redhat-shadowbot-mcp/
├── AGENTS.md              ← install-on-drop (agent reads this)
├── INSTALL_PROMPT.md
├── SHARE.md
├── SETUP.md
├── README.md
├── install.sh             ← optional non-agent install
├── mcp/                   ← MCP server (copy to ~/mcps/shadowbot-assistant)
└── skills/
    └── redhat-shadowbot/  ← copy to ~/.cursor/skills/
```

This zip does **not** include `session.json`, Chrome profiles, or a virtualenv.

## Requirements

- Red Hat associate with Sales Assistant access
- Cursor with Agent mode
- Google Chrome
- Python 3.12+
- FreeOTP (same token as other Red Hat apps)

## After they drag the zip

1. Reload MCP until `shadowbot-assistant` is green.
2. New chat: `Log me into Shadowbot` → SSO + FreeOTP in Chrome.
3. Later: `Ask Shadowbot: <question>` (one `shadowbot_ask`).
