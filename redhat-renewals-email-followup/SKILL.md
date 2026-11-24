---
name: redhat-renewals-email-followup
description: >-
  Gmail-first renewals follow-up: Python CLI discovers sent renewal threads,
  detects replies, creates follow-up drafts for non-replies (7 business days),
  and emits masked chat summaries (Collect/Mask/Rehydrate). CSV is optional
  fallback only when parsing fails or the user passes a file. Read FAST-PATH.md
  first, then roc followup CLI.
---

# Red Hat Renewals Email Follow-up

> **Default:** read [FAST-PATH.md](FAST-PATH.md) and run `roc followup`.
> Do not use Gmail MCP or load full docs unless the CLI fails.

**Gmail-first.** No CSV required for a normal run. **Drafts only** — never send unless asked.

## Privacy & cost (mandatory)

1. **Python CLI owns the workflow** — discovery, parse, reply detection, draft HTML, Gmail create.
2. **Mask before chat** — paste CLI **masked** summary only. No HTML bodies, no clear To/Cc in the transcript.
3. **Vault locally** — CLI writes `renewals_followup_vault.json` + masked results; clear contacts stay out of agent chat.
4. **Token budget** — do not load drafter `SKILL.md`, CSV, or `reference.md` unless CLI reports failure.

## CLI

```bash
roc followup --dry-run
roc followup --since 7
roc followup --csv "<path>"
```

Install: `~/.cursor/R.O.C./bin/roc` (see `roc-setup` or `/roc-install`).

## Agent workflow

1. `roc followup --since 7` (add `--csv` only if user supplied a file)
2. Paste **masked** CLI summary only — counts + account keys + draft stage; never HTML bodies or raw emails
3. Do not load drafter `SKILL.md` or CSV unless CLI reports parse failures
4. If user asks to inspect a draft recipient, rehydrate from vault via local script — do not dump vault into chat

## When CLI fails

| Issue | Read |
|-------|------|
| Gmail discovery / parsing | [reference.md](reference.md) |
| Follow-up body format | French territory: [followup-template-fr.md](followup-template-fr.md). Other languages: `../redhat-renewals-email-drafter/email-format.md` |
| CSV fallback | [reference.md](reference.md) + drafter `config/csv_schemas.json` |
| Examples | [examples.md](examples.md) |

On MCP fallback: treat contacts as tokens in chat; rehydrate only in tool arguments.

## Guardrails

- Gmail-first — never require CSV on invoke
- Never draft follow-up when customer replied
- Max 2 follow-ups per account; 7 business days between touches
- Do not invent SKUs, dates, contacts, or amounts
- French follow-ups must use [followup-template-fr.md](followup-template-fr.md) verbatim (greeting name only)
- **Gmail signature (mandatory):** append [signature.html](signature.html) after `Cordialement,` on every follow-up draft (same asset as drafter / `_shared`). Never leave a draft without Adrien’s signature.
- Never paste `renewals_followup_results.clear.json` or vault contents into chat

## Related

| Skill | Role |
|-------|------|
| `redhat-renewals-email-drafter` | Initial outreach (run first) |
| Cross-sell on follow-up #1 | Handled by CLI rules — do not load cross-sell skill |

Optional weekly automation: [AUTOMATION.md](AUTOMATION.md).
