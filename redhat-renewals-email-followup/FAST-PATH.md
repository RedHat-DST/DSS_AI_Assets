# Fast path (token-efficient + PII-safe — use first)

**Default execution:** run the CLI. Do **not** use Gmail MCP, load drafter
`SKILL.md`, or compose follow-up HTML in chat unless the CLI fails.

## Commands

```bash
roc followup --dry-run
roc followup --since 7
roc followup --csv "<path>"    # only when user provides CSV or CLI reports parse failures
```

Or directly:

```bash
python3 ~/.cursor/R.O.C./skills/redhat-renewals-email-drafter/scripts/renewals_cli.py followup --since 7
```

## Agent workflow (minimal tokens + masked chat)

1. **Run** — `roc followup --since 7` (add `--csv` only if the user passed a file)
2. **Summarize** — paste CLI masked summary only (drafted / replied / skipped / parse failed)
3. **Do not** paste email bodies, clear To/Cc, vault JSON, or re-read Gmail via MCP unless CLI fails
4. **Outputs** (local under drafter `output/`):
   - `renewals_followup_results.masked.json` — safe for agent reference
   - `renewals_followup_vault.json` — local rehydrate map (**not for chat**)
   - `renewals_followup_results.clear.json` — contacts for audit (**not for chat**; TTL: delete after 7 days when practical)

**Prefs:** follow-up uses the same seller name/tone as drafter (`roc prefs show`).

## When to run

- User says follow-up, non-replies, or `/redhat-renewals-email-followup`
- Calendar reminder ~7 business days after initial renewals send
- After user **sent** initial renewal drafts (not while still drafts)

## Rules (CLI enforces these)

| Rule | Detail |
|------|--------|
| Gmail-first | No CSV required on invoke |
| Customer replied | No follow-up draft |
| Timing | 7 business days after last seller send |
| Max | 2 follow-ups per account |
| CSV | Only on `--csv` or parse failure recovery |
| PII | Draft create uses clear contacts inside CLI; chat sees masked summary |

## On CLI failure only

Read in this order (smallest first):

1. [reference.md](reference.md) — discovery, parsing, reply rules
2. French: [followup-template-fr.md](followup-template-fr.md) · else `../redhat-renewals-email-drafter/email-format.md`
3. [examples.md](examples.md)
4. Full [SKILL.md](SKILL.md) — last resort

If falling back to Gmail MCP: Collect → Mask contacts as `[EMAIL_n]` in chat → Rehydrate only in draft tool args.

## Optional automation

See [AUTOMATION.md](AUTOMATION.md) — prefer `roc followup` in the automation prompt.
