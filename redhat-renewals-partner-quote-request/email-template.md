# Demande de devis — email body (FR)

Canonical wording from Adrien’s Google Doc template  
`https://docs.google.com/document/d/1p3-yzOxebbKJznXuB31aDCllcL-9xxHWA577EP7VZI4/edit`

Use HTML in Gmail (`content_type: html`). Replace placeholders. Append signature after the sign-off.

## UGAP / TD Synnex

```html
<div dir="ltr" style="font-family:RedHatText,sans-serif;font-size:small">
Bonjour la team,<br><br>
Pouvez-vous envoyer un devis UGAP pour le renouvellement du client {ACCOUNT_NAME} ci-dessous :<br><br>
Numéro de contrat (ERP Service) : {ERP_SERVICE_NUMBER}<br>
SKU : {SKU}<br>
Quantité : {QTY}<br>
Date d'expiration : {EXPIRATION_DD/MM/YYYY}<br>
Opp : {OPP_NUMBER}<br><br>
Contact client : {CLIENT_CONTACT}<br>
Contact partenaire : SCC<br>
RHN client : {RHN}<br><br>
Bonne journée.<br><br>
</div>
<!-- then append signature.html -->
```

## Arrow (or other distributor)

```html
<div dir="ltr" style="font-family:RedHatText,sans-serif;font-size:small">
Bonjour {ARROW_FIRST_NAMES},<br><br>
Pouvez-vous envoyer un devis pour le renouvellement du client {ACCOUNT_NAME} ci-dessous :<br><br>
Numéro de contrat (ERP Service) : {ERP_SERVICE_NUMBER}<br>
SKU : {SKU}<br>
Quantité : {QTY}<br>
Date d'expiration : {EXPIRATION_DD/MM/YYYY}<br>
Opp : {OPP_NUMBER}<br><br>
Contact client : {CLIENT_CONTACT}<br>
Contact partenaire : {RESELLER_NAME}<br>
Distributeur : Arrow ECS France<br>
RHN client : {RHN}<br><br>
Bonne journée.<br><br>
</div>
<!-- then append signature.html -->
```

## Subject lines

- UGAP: `Demande de devis UGAP - {ACCOUNT_NAME} - Contrat ERP {ERP_SERVICE_NUMBER} - Opp {OPP_NUMBER}`
- Arrow: `Demande de devis - {ACCOUNT_NAME} - Contrat ERP {ERP_SERVICE_NUMBER} - Opp {OPP_NUMBER}`

## Notes

- `{CLIENT_CONTACT}`: `Name <email@…>` or `à confirmer`
- `{RHN}`: Ship-To / entitled account number, or `à confirmer`
- Never put SF Contract Number (`005…` / `006…`) as the main “Numéro de contrat” — use ERP Service
