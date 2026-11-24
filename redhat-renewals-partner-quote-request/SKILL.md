---
name: redhat-renewals-partner-quote-request
description: >-
  Filters a Red Hat AM renewals Sales Cloud report for open renewals without a
  partner/customer quote, enriches with ERP Service contract / SKU / expiration,
  exports a Google Sheet, and creates Gmail draft "demande de devis" emails to
  the distributor (TD Synnex UGAP or Arrow) with SCC/Orange as reseller and the
  AM Gmail signature. Use when the associate asks for Q4 renewals without quote,
  demande de devis UGAP/TD Synnex/Arrow, partner quote drafts from a renewals
  report, or to re-run the partner devis workflow.
---

# Red Hat Renewals — Partner Quote Request (Demande de devis)

**Drafts only — never send** unless the associate explicitly asks.

Related skills: `redhat-salescloud` (CRM), Gmail/Drive MCPs. Customer renewals outreach (not partner devis) → `redhat-renewals-email-drafter`.

## When to run

Associate asks to:
- List renewals **without quote/proposal sent** from a territory renewals report
- Build a **Google Sheet** of those opps (ERP + SKU + expiration)
- Create **Gmail drafts** “demande de devis” to distributor/partner

## Defaults (Adrien territory)

See [defaults.md](defaults.md) for report URL, TD Synnex / Arrow / SCC contacts, CC, and signature path.

## Workflow checklist

```
- [ ] 1. Auth Sales Cloud + load report
- [ ] 2. Filter “no quote yet” (+ optional exclusions)
- [ ] 3. Enrich: ERP Service #, SKU, expiration, contacts
- [ ] 4. Google Sheet
- [ ] 5. Confirm routing (UGAP/TD vs Arrow) with associate if unclear
- [ ] 6. Gmail drafts (HTML + signature)
- [ ] 7. Recap + remind to delete obsolete drafts
```

### 1. Sales Cloud — report

1. Follow `redhat-salescloud` auth (`salescloud_auth` / `salescloud_whoami`).
2. Run `salescloud_get_report` with the report Id/URL (default in [defaults.md](defaults.md)).
3. Prefer report rows over bulk SOQL — org often returns `TXN_SECURITY_NO_ACCESS` on Opportunity line items / Subscriptions / list queries.

### 2. Filter — no quote / proposal yet

From **Next Steps** (and any quote status if available):

**Exclude** if Next Steps clearly show quote/proposal/offer/devis **sent** to customer or partner/disti, or advanced PO path, e.g.:
- `Quote sent`, `Quote quantities sent`, `devis`, `UGAP quote received`, `customer receive offer`, `signing the offer`, `working on PO` / `PO At`

**Keep** if only outreach/relance/meeting, or “proposal **to be** sent”.

**Optional exclusions** (ask or apply when associate requests):
- Next Steps containing owner tag `AT` (Adrien’s notes) — keep VV-only / empty
- Named accounts the associate removes (e.g. Lyon, Nord, Solocal, Vendée, …)

Confirm the filtered list with the associate before Sheet/drafts.

### 3. Enrich

Per remaining opportunity:

| Field | Source |
|-------|--------|
| Opp #, Account, Close, ACV, Qty | Report / `salescloud_get_opportunity` |
| SF Contract # | Opp name suffix / `SBQQ__RenewedContract__c` → Contract |
| **ERP Service contract #** | Lightning **ERP Service** (not SF `ContractNumber`). Prefer associate-provided numbers or Source Opp name `(########)`. API field `ERP_Service_Contract_Number__c` is often empty. |
| Expiration | Contract `EndDate` / `SBQQ__ExpirationDate__c` |
| SKU / Product | Associate-provided SKUs if line items blocked (`RH000xx`) |
| Client contact | Opp `ContactId` → `salescloud_get_contact`, else Next Steps emails |
| RHN | Opp `Ship_To_Account__c` |
| Distributor / reseller | Contract `Distributor__c`, `Partner__c`, `Bill_To_Account_Name__c` |

**Contract number in emails/Sheet = ERP Service #**, not SF `005xxxxx` / `006xxxxx`.

### 4. Google Sheet

Create via Drive MCP (`gsheets_create` + `gsheets_write`). Suggested columns:

`Opp Number | Account | Opportunity Name | Stage | Close Date | ACV | Amount | ERP Service Contract # | Contract Start | Contract Expiration | Qty | Product/SKU | Contact partenaire | Distributor | Opportunity URL | Contract URL`

Return the Sheet URL.

### 5. Routing — who receives the draft

| Path | When | To | Contact partenaire in body |
|------|------|-----|----------------------------|
| **UGAP / TD Synnex** | Default for public/UGAP renewals | Jesse Lecomte + RedhatTDfr (see defaults) | **SCC** |
| **Arrow** | Disti on opp/contract is Arrow (e.g. CNFPT) | Arrow contacts from recent threads / CRM | Reseller on opp (e.g. **Orange**) |

CC: `vvaratha@redhat.com` (unless associate says otherwise).

If Bill To / Distributor ≠ TD Synnex, **do not** silently send UGAP mail to TD — create the correct disti draft (or ask).

### 6. Gmail drafts

1. Load body template: [email-template.md](email-template.md) (or associate’s Google Doc if provided).
2. One draft per opportunity (or per account if associate prefers coterm bundling — ask).
3. `gmail_create_draft` with `content_type: html`.
4. **Always append** Gmail signature from `signature.html` in this skill  
   (fallback: `~/.cursor/skills/_shared/adrien-toussaint-gmail-signature.html`).  
   Never leave a draft without signature.
5. Subject pattern:
   - UGAP: `Demande de devis UGAP - {ACCOUNT} - Contrat ERP {ERP} - Opp {OPP}`
   - Arrow/other: `Demande de devis - {ACCOUNT} - Contrat ERP {ERP} - Opp {OPP}`

Fill placeholders: client name, ERP #, SKU, qty, expiration, opp #, client contact, partenaire (SCC/Orange/…), RHN, distributor note if useful.

### 7. Recap

Reply with:
- Count of opps / Sheet URL
- Draft count and routing summary (TD vs Arrow)
- Fields still “à confirmer”
- Reminder to **delete obsolete drafts** (Gmail MCP cannot trash drafts)

## Guardrails

- Never send mail; drafts only
- Never invent ERP numbers — mark `à confirmer` if unknown
- Do not claim to bypass Salesforce `TXN_SECURITY_NO_ACCESS`; ask associate for SKUs/ERP from Lightning
- Prefer French body matching [email-template.md](email-template.md)
- On re-runs, create new drafts; tell associate to remove prior versions

## Example trigger

> List my Q4 renewals without quote from report … then Sheet + demande de devis to TD Synnex / Arrow
