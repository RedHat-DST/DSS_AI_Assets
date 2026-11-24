---
name: redhat-shadowbot
description: >-
  Prompt Red Hat Sales Assistant (Shadowbot) as a signed-in Red Hat associate
  via the shadowbot-assistant MCP: ask the agent, continue threads, list
  conversations. Use when the associate asks about Shadowbot, Sales Assistant,
  shadowbot.io.redhat.com, or to prompt the sales-assistant agent. Auth is
  associate SSO (auth.redhat.com) + FreeOTP; sessions expire.
---

# Red Hat Shadowbot MCP (Sales Assistant)

Use **shadowbot-assistant** (`shadowbot_*`). Do not browse or fetch `shadowbot.io.redhat.com`. Do not reverse-engineer the UI. The MCP already knows SSO + FreeOTP.

## Call budget (do not waste tokens)

| User intent | Calls |
|-------------|--------|
| A question for Sales Assistant | **One** `shadowbot_ask`. Stop. |
| First login / session expired | **One** `shadowbot_auth` (`wait=true`), then retry the original ask. |
| “Who am I logged in as?” | `shadowbot_whoami` |
| “Show my Shadowbot chats” | `shadowbot_list_threads` |

Never prepend `whoami`, `list_threads`, or `auth` to a normal question. Never poll. Never open Chrome yourself. Never ask for a password or OTP in chat.

`shadowbot_ask` can take a few minutes. Wait for the tool result.

Omit `thread_id` to continue the last chat. Set `new_thread=true` only for a new topic.

## Auth (only when a tool says the session expired)

1. Call `shadowbot_auth` with `wait=true`.
2. Tell the associate a **Chrome window is open**. They sign in at auth.redhat.com and enter **FreeOTP**.
3. When the tool returns their email, retry the original `shadowbot_ask`.

If Sales Assistant is already visible in Chrome but auth still fails: `shadowbot_auth` with `force=true`.

Chrome stays open (CDP port 9225). Later logouts are the same window, FreeOTP again.

## Tools

| Need | Tool |
|------|------|
| Login / re-login | `shadowbot_auth` |
| Who am I? | `shadowbot_whoami` |
| Ask Sales Assistant | `shadowbot_ask` |
| Recent chats | `shadowbot_list_threads` |
| Read a chat | `shadowbot_get_thread` |
