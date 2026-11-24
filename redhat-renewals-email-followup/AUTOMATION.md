# Renewals Follow-up — Cursor Automation (optional)

**Default:** `roc followup --since 7` (Gmail-first — no CSV unless parse fails).

## Schedule (if you have Automations access)

| Setting | Value |
|---------|-------|
| Trigger | Cron — **Mondays 09:00** |
| Cron | `0 9 * * 1` |

## Tools to enable

- **Terminal:** `roc` CLI (preferred — token-efficient)
- **MCP:** Gmail assistant (fallback only if CLI unavailable)

## Instructions (automation prompt)

```
Run renewals follow-up (Gmail-first, drafts only, PII-masked):

1. Read ~/.cursor/skills/redhat-renewals-email-followup/FAST-PATH.md
2. Run: roc followup --since 7
3. Paste the MASKED CLI summary only — no HTML bodies, no clear To/Cc, no vault JSON
4. If CLI fails, read reference.md and retry with Collect→Mask→Rehydrate; never send — drafts only
```

## Manual test

```
/redhat-renewals-email-followup
```

Requires sent initial renewal emails (email drafter template) in Gmail.
