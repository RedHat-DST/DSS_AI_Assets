# Renewals Follow-up — Reference (Gmail-first)

> Prefer `roc followup` (FAST-PATH). This file is for CLI failure / MCP fallback.
> On MCP fallback: mask emails as `[EMAIL_n]` in chat; rehydrate only in draft tool args.
> Never paste vault or `*.clear.json` into the transcript.

## Discover initial sent threads

```
in:sent subject:" — subscription renewals expiring " -subject:reminder
```

- One thread per account outreach batch.
- Exclude `reminder:` / `final reminder:` subjects (those are follow-ups, not initial).
- Sort by date; process each unique thread.

### Parse subject → account

Pattern:

```
{account_key} — subscription renewals expiring {Mon YYYY}
```

Example: `Avaya GmbH & Co. KG — subscription renewals expiring Aug 2026`

Follow-up subjects (do not use for discovery):

- `{Account} — reminder: subscription renewals expiring …`
- `{Account} — final reminder: subscription renewals`

## Parse sent email body

Read the **first seller message** in the thread (initial renewal send). The
email drafter produces this structure per `email-format.md` — parse it back:

### Required for `parse_ok`

- Valid subject → `account_key`
- At least one **To** address (CC optional)
- Section **Subscriptions to renew** with a table:

| Product | Expiration Date |

(Legacy emails may use `Product (SKU)` — accept either header. Opp # and Amount
are **not** in customer emails.)

Extract each row. HTML tables: map `<td>` columns to the same fields.

### Optional (reuse if present)

- **Renewal timeline** — bullets under `### Renewal timeline`
- **Co-terming** — paragraph starting with e.g. "You have several Red Hat
  subscriptions expiring" or containing "Co-terming your Red Hat subscriptions"

### `parse_failed` reasons

| Reason | CSV fallback? |
|--------|----------------|
| Subject doesn't match pattern | Yes, if user passed `Use:` |
| No subscriptions table in body | Yes, if user passed `Use:` |
| No To addresses | Yes, if user passed `Use:` |
| Empty thread / read error | Yes, if user passed `Use:` |

If parse failed and **no** user CSV → skip; do not guess.

## Contacts and reply detection

**Contacts (primary):** To + CC on the initial sent message.

**Customer reply:** after the seller's last outbound message, any message where
`From` is:

- An address in To/CC, or
- Any participant that is **not** the seller's address

Treat ambiguous cases (auto-reply clearly labeled OOO) as reply when unsure —
better to skip follow-up than nudge someone who responded.

**Seller address:** infer from `From` on `in:sent` messages in the thread.

## CSV fallback (explicit path only)

Load CSV **only** when:

1. User invoked with `Use: /path/to/file.csv`, **and**
2. Gmail parse failed for that `account_key`

Match rows: same `account_key` rules as email drafter (`Customer / Opportunity
Name` → split on `  Renewal - `).

Use CSV rows to build subscriptions table, contacts, timeline. Still use Gmail
for reply detection and timing on the **same thread** (search by account subject
+ contacts).

Never load CSV from `~/Downloads/` automatically.

## Business days

Count weekdays (Mon–Fri) strictly after last seller message date through today.

Example: sent Monday week 1 → follow-up #1 eligible Tuesday week 2 (7 business days).

## Follow-up email examples

**French territory:** use [followup-template-fr.md](followup-template-fr.md) verbatim.
Personalise the greeting only (`Bonjour {Prénom},`). Do not add a subscriptions table.

Other languages: follow `~/.cursor/skills/redhat-renewals-email-drafter/email-format.md`.
Body content must **mirror parsed Gmail** from the initial send, not fresh CSV data.

### Follow-up #1 example

```markdown
Hi Stefan,

I wanted to follow up on my earlier note regarding Red Hat subscription renewals for **Avaya GmbH & Co. KG**.

### Subscriptions to renew

| Product | Expiration Date |
|---------|-----------------|
| RHEL Server, Standard (RH00004) | 2026-08-10 |
| RHEL Server, Premium (RH00003) | 2026-10-19 |

### Renewal timeline

- **2026-08-10** — RHEL Server, Standard — *urgent*
- **2026-10-19** — RHEL Server, Premium

When you have a moment, please let us know how you would like to proceed with these renewals.

Best regards,

{Seller first name}
Red Hat
```

## Seller digest sections

| Section | Meaning |
|---------|---------|
| Follow-ups drafted | Non-reply, eligible, draft created |
| Skipped — replied | Gmail shows customer reply |
| Skipped — too early | < 7 business days |
| Skipped — max follow-ups | 2 follow-ups already sent |
| Skipped — parse failed (no CSV) | Could not parse sent email; no user CSV |
| CSV fallback used | Parse failed but recovered from user CSV |
