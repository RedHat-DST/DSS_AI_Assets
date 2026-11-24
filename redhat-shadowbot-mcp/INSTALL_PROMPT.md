# Drag-to-install — Red Hat Shadowbot MCP

**Associates only drag `redhat-shadowbot-mcp.zip` into a Cursor Agent chat and send.** No paste prompt. `AGENTS.md` inside the zip is the install instruction.

Auth is associate SSO + FreeOTP in Chrome. Never paste a password or OTP into chat.

Do not send an open-ended “create a Shadowbot MCP” chat.

---

## What they do

1. Drag `redhat-shadowbot-mcp.zip` into **Cursor Agent** chat (or the unpacked `redhat-shadowbot-mcp` folder).
2. Send. Empty message is fine; “install” is fine too.
3. Reload **Cursor Settings → MCP** until `shadowbot-assistant` is green.
4. New chat: first-login line below.

---

## First login (new chat, after MCP is green)

```
Log me into Shadowbot. Call shadowbot_auth with wait=true. I will complete Red Hat SSO + FreeOTP in Chrome. Do not ask for my password or OTP. When auth returns my email, stop.
```

## Everyday use

```
Ask Shadowbot: <your question>
```

One `shadowbot_ask` call.

---

## Fallback (only if the agent ignores the zip)

Paste the contents of `AGENTS.md` with the zip attached.
