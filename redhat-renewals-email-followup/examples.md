# Renewals Follow-up — Examples

## Standard run (Gmail only)

**User:**

> /redhat-renewals-email-followup

**Agent:**

1. Search `in:sent subject:" — subscription renewals expiring " -subject:reminder`
2. Parse each thread (account, contacts, subscription table from sent body)
3. Replied → skip. No reply + 7+ business days → follow-up draft in thread
4. Seller digest. **No CSV loaded.** Paste **masked** CLI summary only (no clear To/Cc).

## With CSV fallback (parse failure)

**User:**

> /redhat-renewals-email-followup  
> Use: ~/Downloads/renewals_backup.csv

**Agent:**

1. Gmail-first for all threads
2. One account missing table in sent body → merge rows from CSV for that
   `account_key`
3. Reply/timing still from Gmail thread
4. Digest notes **CSV fallback used** for that account

## Replied — no draft

**Gmail:** Deutsche Nationalbibliothek thread shows reply from `p.ratuschni@dnb.de`
after initial send.

**Agent:** Listed under **Skipped — replied**; no follow-up draft.

## Parse failed, no CSV

**Gmail:** Old manual email, no subscriptions table.

**User:** `/redhat-renewals-email-followup` (no `Use:`)

**Agent:** **Skipped — parse failed (no CSV)**; suggest re-send via email drafter
or re-run with `Use: <csv>`.

## Optional automation

See [AUTOMATION.md](AUTOMATION.md) — prompt uses Gmail only, no CSV path.
