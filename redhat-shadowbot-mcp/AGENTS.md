# Install this Shadowbot MCP now

This package was dropped into a Cursor Agent chat so you would **install** it. Start immediately. Do not wait for a longer prompt. Do not browse the web, fetch shadowbot.io, reverse-engineer the UI, open Chrome, or start SSO.

You are installing for a **Red Hat associate**. Auth later is associate SSO (auth.redhat.com) + FreeOTP in Chrome. Never ask for a password or OTP in chat.

## Do this, in order

1. Unpack the zip if needed. This package contains `mcp/` (the server) and `skills/redhat-shadowbot/`.

2. Copy `mcp/` to `~/mcps/shadowbot-assistant` (create `~/mcps` if missing). Overwrite code files. Never copy `session.json`, `profiles/`, or `.venv` from this package.

3. Copy `skills/redhat-shadowbot` to `~/.cursor/skills/redhat-shadowbot`.

4. Create a Python 3.12 venv at `~/mcps/shadowbot-assistant/.venv` (prefer `python3.12` or `/opt/homebrew/bin/python3.12`; not macOS python3 3.9). Then:
   - `.venv/bin/pip install -r requirements.txt`
   - `.venv/bin/playwright install chromium`

5. Merge into `~/.cursor/mcp.json` without removing existing servers. Absolute paths:

   ```json
   "shadowbot-assistant": {
     "command": "<HOME>/mcps/shadowbot-assistant/.venv/bin/python",
     "args": ["<HOME>/mcps/shadowbot-assistant/mcp_server.py"]
   }
   ```

6. If `~/mcps/shadowbot-assistant` already exists, update the code and keep their `session.json` / Chrome profile.

7. Stop. Tell them:
   - Reload MCP in **Cursor Settings → MCP** until `shadowbot-assistant` is green
   - First login is a **new chat**: “Log me into Shadowbot” → you call `shadowbot_auth` (`wait=true`) → they sign in with associate SSO + FreeOTP in Chrome
   - Never ask for their password or OTP
   - This uses their existing Sales Assistant access; it does not grant it

When finished, print the `mcp.json` snippet you wrote and the skill path. Then stop.
