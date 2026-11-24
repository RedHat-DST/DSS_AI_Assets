# Fast path (token-efficient + PII-safe — use first)

**Default:** Python filter → masked table in chat → LLM only for short FR draft copy → rehydrate at Gmail tool edge.

Do **not** paste report dumps, clear JSON, vault files, or full email HTML into chat.

## 1) Export + filter (no LLM)

Save Sales Cloud report/opp rows to:

`~/.cursor/skills/relance-new-pipe/output/report_raw.json`

```bash
python ~/.cursor/skills/relance-new-pipe/scripts/filter_pipeline_opps.py \
  --in ~/.cursor/skills/relance-new-pipe/output/report_raw.json \
  --out-dir ~/.cursor/skills/relance-new-pipe/output \
  --close-from 2026-09-01 --close-to 2026-12-31
```

Paste **only** `pipeline_opps.chat.md` (masked). Confirm scope with user.

## 2) Thread match + draft (minimal LLM)

For each approved opp token:
- Gmail search/read via MCP
- Chat: ≤3 masked bullets + recipient tokens
- Write `draft_masked.json` (tokens in to/cc)
- Rehydrate → create draft from clear file (do not echo cleartext)

```bash
python ~/.cursor/skills/relance-new-pipe/scripts/rehydrate_draft_payload.py \
  --vault ~/.cursor/skills/relance-new-pipe/output/pipeline_opps.vault.json \
  --in  ~/.cursor/skills/relance-new-pipe/output/draft_masked.json \
  --out ~/.cursor/skills/relance-new-pipe/output/draft_clear.json
```

## 3) After manual send

Update `Next_Steps__c` only for confirmed SENT/NOT SENT; chat uses opp tokens.

## Outputs (local)

| File | Chat? |
|------|-------|
| `pipeline_opps.masked.json` / `.chat.md` | Yes |
| `pipeline_opps.clear.json` / `.vault.json` | **No** |
| `draft_clear.json` | **No** |

## On failure only

Read full [SKILL.md](SKILL.md). Sales Cloud auth: [redhat-salescloud](../redhat-salescloud/SKILL.md).
