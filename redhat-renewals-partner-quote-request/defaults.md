# Defaults — Adrien Toussaint (Territory Core FR)

Override when the associate specifies otherwise.

## Sales Cloud report

- **Default report:** Adrien Territory Report 2026 Renewal  
  `https://redhatcrm.lightning.force.com/lightning/r/Report/00OPe00000gac8DMAQ/view`
- Report Id: `00OPe00000gac8DMAQ`

## Google Doc (wording source)

- Demande de devis template:  
  `https://docs.google.com/document/d/1p3-yzOxebbKJznXuB31aDCllcL-9xxHWA577EP7VZI4/edit`

## Gmail — UGAP / TD Synnex (default distributor)

| Role | Value |
|------|--------|
| To | `Jesse.Lecomte@tdsynnex.com`, `RedhatTDfr@tdsynnex.com` |
| Cc | `vvaratha@redhat.com` |
| Contact partenaire (body) | `SCC` |

## Gmail — Arrow (when Distributor = Arrow ECS France)

Known contacts from CNFPT / SBOF threads (refresh from Gmail if stale):

| Role | Value |
|------|--------|
| To | `Radouane.Mariam@arrow.com`, `FatimaZahra.Nafie@arrow.com` |
| Cc | `vvaratha@redhat.com` |
| Contact partenaire (body) | Reseller on opp (CNFPT → `Orange Business Services`) |

## Gmail signature

Append full HTML from (first match wins):

1. `signature.html` in this skill folder (bundled for sharing)
2. `~/.cursor/skills/_shared/adrien-toussaint-gmail-signature.html`

Prefs aligned with renewals drafter: `append_gmail_signature: true`, seller `Adrien Toussaint`.

## Filtering notes from first run (optional)

Typical interactive exclusions after “no quote yet”:
- Next Steps tag `AT` (keep VV-only / blank)
- Accounts associate removes (examples from Oct 2026 run: Solocal, Vendée, Commune de Lyon, Autorité de régulation des transports, Département du Nord, Air Tahiti, Aéroports Côte d’Azur, Biomérieux)

Do **not** hard-code these as permanent rules — ask each run.

## Field reminders

| Concept | Use |
|---------|-----|
| Contract # for partner | **ERP Service** number |
| SF Contract Number | Secondary only (opp name / CRM Contract) |
| SKU | Often associate-supplied when CPQ lines blocked |
| Product codes example | `RH00004`, `RH00005`, `RH00025`, `RH00032` |
