---
name: relance-new-pipe
description: >-
  End-to-end AM workflow to relaunch Red Hat Sales Cloud "New Pipe" Pipeline
  opportunities: Python-filter report opps (masked), find Gmail threads, create
  reply drafts (never send) via mask→rehydrate, validation recap, then update
  Next_Steps__c after manual send. Use when the user says relance new pipe,
  pipeline Q4 follow-up, relancer les opps Pipeline, New Pipe report, or similar.
---

# Relance New Pipe

AM: **Adrien Toussaint** (`atoussai@redhat.com`).  
Never send emails. Confirm before writes (Gmail drafts, then SF Next Steps).

Also read: [redhat-salescloud](../redhat-salescloud/SKILL.md) for auth/MCP quirks.  
**Default:** [FAST-PATH.md](FAST-PATH.md) — Python filter + Mask/Rehydrate before any LLM drafting.

## Privacy & cost (mandatory)

1. **Python first** — filter Pipeline scope with `scripts/filter_pipeline_opps.py`; do not ask the LLM to filter large report dumps.
2. **Collect → Mask → Rehydrate** — real emails/ACV/names stay in local vault JSON; chat and LLM see tokens only (`[EMAIL_1]`, `[ACCT_2]`, `[ACV_3]`).
3. **Chat minimization** — paste masked tables only. Never paste cleartext `*.clear.json`, vault files, email bodies, or `sid`.
4. **Token budget** — load this SKILL + FAST-PATH; do not dump full Gmail HTML into chat. Summarize threads in ≤3 masked bullets per opp.

## Sources

| Source | Use |
|--------|-----|
| Sales Cloud MCP | Report / opp export → **save JSON locally**, then Python filter |
| Gmail MCP | History + drafts only; rehydrate recipients at draft-create time |
| People.ai | Via SF `LastActivityDate` / activities when available |

Do not invent contacts, internal `@redhat.com` CCs, or ignore marketing opt-out.

## Step 1 — Scope opportunities (Python)

Default report: **Adrien Territory New Pipe Report 202** (`00OPe00000gUKxCMAW`), or URL/report the user gives.

**Filters (strict — enforced in script):**
- `ForecastCategoryName` = **Pipeline** only
- Close date in requested window (default: Sep–Dec current year)
- Exclude Next Steps that say “not this year” / hors année
- Keep territory opps even if Owner = Victor / Ines

**Agent actions:**
1. Pull report/opps via MCP (or user file).
2. Write raw JSON to `output/report_raw.json` (local only).
3. Run:

```bash
python ~/.cursor/skills/relance-new-pipe/scripts/filter_pipeline_opps.py \
  --in ~/.cursor/skills/relance-new-pipe/output/report_raw.json \
  --out-dir ~/.cursor/skills/relance-new-pipe/output \
  --close-from YYYY-09-01 --close-to YYYY-12-31
```

4. Paste **only** the masked chat table from stdout / `pipeline_opps.chat.md`.

**If list/SOQL → 403 TXN_SECURITY:** `get_report` + SOSL + `get_opportunity` by Id.  
**Auth:** `salescloud_auth` `wait=true`; `force=true` if session dead. Never ask for password/OTP in chat.

**STOP** — confirm masked scope with user before Step 2.

## Step 2 — Gmail + contacts (masked)

For each kept opp (use tokens from masked table; resolve via vault only when calling tools):
1. Find the most relevant recent thread (CR, quote, RFP, product follow-up)
2. Read enough to draft — **do not** paste full bodies in chat; note 1–3 masked bullets
3. Propose To/Cc as tokens (`[EMAIL_n]`); keep mapping only in vault / tool args after rehydrate
4. If SF contact opted out of marketing → do **not** mail customer; use partner or flag blocker
5. Flag annex discussions already active

**Deliverable (chat-safe):**  
`Opp token | Thread yes/no | Recipient tokens | Opt-out risk | Annex note`

## Step 3 — Gmail drafts (never send; rehydrate at tool edge)

1. Compose draft **reasoning** with tokens in To/Cc/body placeholders where needed.
2. Write masked payload JSON → run:

```bash
python ~/.cursor/skills/relance-new-pipe/scripts/rehydrate_draft_payload.py \
  --vault ~/.cursor/skills/relance-new-pipe/output/pipeline_opps.vault.json \
  --in  ~/.cursor/skills/relance-new-pipe/output/draft_masked.json \
  --out ~/.cursor/skills/relance-new-pipe/output/draft_clear.json
```

3. Create Gmail draft from **clear** payload via MCP (local tool step). Delete or avoid echoing clear JSON in chat.
4. Reply on existing thread when relevant (`reply_to_message_id` + `thread_id`).
5. FR, concise, personalized; CC only confirmed addresses — never invent.
6. **Gmail signature (mandatory):** append HTML from [signature.html](signature.html) (or `~/.cursor/skills/_shared/adrien-toussaint-gmail-signature.html`) after the closing — never leave a draft without Adrien’s signature.

**Deliverable (chat-safe):**  
`# | Opp token | Recipient tokens | Base historique | Draft link | Notes`

**STOP** — wait for manual validation / send.

## Step 4 — Post-send Next Steps

When user says sends are done:

1. Classify **SENT** vs **NOT SENT** via Gmail `in:sent` + user statements
2. Typical NOT SENT: owned by Victor/Ines; annex already active
3. Opps user **omitted** from NOT SENT comments → **do not** update Next Steps
4. Update `Next_Steps__c` only for opps in scope (rehydrate account/opp ids from vault if needed)

### Next Steps format (mandatory)

- Style: `AT MM.DD …`
- Max **4 lines**, newest first; keep 2–3 useful history lines
- Next check horizon ≥ **2 weeks**
- Short factual English

**First-line patterns:**
- SENT: `AT MM.DD Follow up mail sent [customer/partner]. Waiting reply. Next check MM.DD`
- NOT SENT annex: `AT MM.DD No dedicated mail - annex [topic] ongoing. Next check MM.DD`
- NOT SENT owner: `AT MM.DD No AT follow-up mail - owned by [VV/ID]. Sync before next push. Next check MM.DD`

### Writing to Sales Cloud

- MCP is **read-only** → authenticated Sales Cloud Chrome session to PATCH `Next_Steps__c`
- Never log/print `sid`
- Spot-check 1–2 opps; confirm skipped opps unchanged

**Final deliverable (chat-safe):**  
`Opp token | Status | Motif | Next Steps updated (yes/no)`

## Hard rules

- Drafts only — never send
- Masked chat only — no clear emails, ACV figures, or full bodies in the transcript
- Do not change SF fields other than `Next_Steps__c` unless explicitly asked
- If wrong thread/contact/opt-out/owner → ask before acting
- Prefer scripts under `scripts/` over LLM for filtering, masking, rehydrating

## Triggers

`relance new pipe` · `pipeline Q4 follow-up` · `relancer les opps Pipeline` · New Pipe report / list of Pipeline opps to relaunch
