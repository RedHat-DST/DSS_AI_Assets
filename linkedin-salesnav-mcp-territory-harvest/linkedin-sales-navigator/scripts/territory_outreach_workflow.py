#!/usr/bin/env python3
"""Territory outreach workflow: enrich consolidated report, HTML, email payloads."""

from __future__ import annotations

import asyncio
import csv
import html
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "output"
CONSOLIDATED = OUT / "nl_comm_terr02_top10_consolidated.json"

RENEWALS = {
    "Stichting Catharina Ziekenhuis": ["00652826", "00558462"],
    "VANBOXTEL B.V.": ["00678051", "00624785", "00664872", "00597512", "00569269", "00597513"],
    "Open Line Holding II B.V.": ["00605316", "12837264", "00126927"],
    "Capgemini Nederland B.V.": ["00542183", "00684395", "00556367", "17098322"],
    "Simac Beleggingen B.V.": ["00601096", "00613947", "00635625", "00509230", "00509229"],
    "Tata Steel Nederland B.V.": ["00607570", "17198694"],
    "Anoigo Services B.V.": ["00659570", "00608842", "00585210", "00585211", "00585122"],
    "Stichting Internet Domeinregistratie Nederland": ["00653922", "00653923", "00539364", "00565726", "11846482"],
    "Keylane B.V.": ["00602716", "00584231", "00621113", "00636949", "00665125", "00682352", "00703649"],
    "Vanderlande": ["00530441", "00670130", "00663317", "00663176", "00675980", "00530442", "00570095"],
}

USE_CASE_LINKS = {
    "satellite": "https://www.redhat.com/en/technologies/management/satellite",
    "rhel": "https://www.redhat.com/en/technologies/linux-platforms/enterprise-linux",
    "rhel7": "https://access.redhat.com/support/policy/updates/errata",
    "rhel8": "https://www.redhat.com/en/technologies/linux-platforms/enterprise-linux",
    "openshift": "https://www.redhat.com/en/technologies/cloud-computing/openshift",
    "eus": "https://access.redhat.com/support/policy/updates/openshift",
    "ansible": "https://www.redhat.com/en/technologies/management/ansible",
    "over-deploy": "https://www.redhat.com/en/about/subscription-model",
}

EMAIL_TEMPLATES = {
    "satellite": {
        "subject": "Strengthening lifecycle management at {account}",
        "play": "Satellite upsell / lifecycle management",
        "links": [USE_CASE_LINKS["satellite"], "https://www.redhat.com/en/resources/satellite-overview"],
    },
    "rhel": {
        "subject": "Aligning your RHEL estate with current support lifecycles",
        "play": "RHEL lifecycle & compliance",
        "links": [USE_CASE_LINKS["rhel"], USE_CASE_LINKS["rhel7"]],
    },
    "openshift": {
        "subject": "OpenShift platform alignment and support runway",
        "play": "OpenShift EUS / platform engineering",
        "links": [USE_CASE_LINKS["openshift"], USE_CASE_LINKS["eus"], "https://www.redhat.com/en/resources/openshift-container-platform-datasheet"],
    },
    "over-deploy": {
        "subject": "Subscription alignment review for {account}",
        "play": "Subscription compliance & governance",
        "links": [USE_CASE_LINKS["over-deploy"], USE_CASE_LINKS["rhel"]],
    },
}


def infer_theme(use_cases: str) -> str:
    u = use_cases.lower()
    if "openshift" in u or "ocp" in u or "eus" in u:
        return "openshift"
    if "satellite" in u:
        return "satellite"
    if "over-deploy" in u or "rhel 7" in u or "rhel 8" in u or "rhel" in u:
        return "rhel" if "over-deploy" not in u else "over-deploy"
    return "rhel"


def build_email(account: str, use_cases: str, contacts: list[dict]) -> dict:
    theme = infer_theme(use_cases)
    tmpl = EMAIL_TEMPLATES[theme]
    to_emails = [c["email"] for c in contacts if c.get("email") and "@" in c["email"]][:5]
    if not to_emails:
        to_emails = ["review@example.invalid"]
    links_md = "\n".join(f"- [{link.split('/')[-1] or 'resource'}]({link})" for link in tmpl["links"])
    body = f"""Dear colleagues,

I hope this message finds you well. As your Red Hat account team for **{account}**, I wanted to share a short, practical note tied to what we are seeing in your environment.

**Focus areas from our recent review**
{use_cases}

**Why reach out now**
Based on telemetry and subscription data, there is an opportunity to reduce operational risk, stay within supported lifecycles, and simplify platform operations — without disrupting running workloads.

**Recommended next step**
A 30-minute working session with your infrastructure/platform leads to walk through options, reference architectures, and customer-proven patterns.

**Helpful resources**
{links_md}

**Sales play:** {tmpl['play']}

I would welcome the chance to coordinate a brief call with the right stakeholders on your side. Please let me know what works for your calendar in the coming weeks.

Kind regards,
Alexandru Marcov
Red Hat Territory Manager — NL Commercial Core
"""
    followup = f"""Dear colleagues,

Following up on my note last week regarding platform lifecycle and subscription alignment at **{account}**.

If helpful, I can share a concise briefing tailored to your teams covering:
- Current support posture for the workloads we discussed
- Practical migration or extension paths (where relevant)
- A short demo or architecture review with our specialists

**Resources**
{links_md}

Would a 20-minute call this week or next still be useful?

Kind regards,
Alexandru Marcov
"""
    return {
        "to": ", ".join(to_emails),
        "subject": tmpl["subject"].format(account=account),
        "body": body,
        "followup_subject": f"Re: {tmpl['subject'].format(account=account)}",
        "followup_body": followup,
        "theme": theme,
    }


async def fetch_salescloud_contacts(account_id: str, account_name: str) -> list[dict]:
    sys.path.insert(0, str(Path.home() / "mcps/salescloud-assistant"))
    from src.ops import run_search

    contacts: list[dict] = []
    query = account_name.split(" B.V.")[0].split(" Stichting ")[-1][:40]
    try:
        result = await run_search(query, limit=25)
        for r in result.get("records") or []:
            obj = r.get("_object")
            acct = (r.get("Account") or {}).get("Name") or r.get("Company") or ""
            if account_name.lower() not in acct.lower() and query.lower() not in acct.lower():
                continue
            if obj == "Contact":
                contacts.append({
                    "source": "salescloud",
                    "name": r.get("Name", ""),
                    "title": r.get("Title", "") or "",
                    "email": r.get("Email", ""),
                    "phone": r.get("Phone") or r.get("MobilePhone") or "",
                })
            elif obj == "Lead":
                contacts.append({
                    "source": "salescloud-lead",
                    "name": r.get("Name", ""),
                    "title": r.get("Title", "") or "",
                    "email": r.get("Email", ""),
                    "phone": r.get("Phone", ""),
                })
    except Exception as e:
        print(f"search error {account_name}: {e}", file=sys.stderr)
    return contacts


def format_contact_line(c: dict, color: str) -> str:
    parts = [c.get("name") or "Unknown", c.get("title") or "", c.get("email") or "", c.get("phone") or ""]
    text = " | ".join(p for p in parts if p)
    src = c.get("source", "")
    if src:
        text += f" [{src}]"
    return f'<span style="color:{color};">{html.escape(text)}</span>'


def main():
    data = json.loads(CONSOLIDATED.read_text())
    supportable_contacts: dict[str, list[dict]] = {}
    supp_file = OUT / "nl_comm_terr02_supportable_contacts.json"
    if supp_file.exists():
        supportable_contacts = json.loads(supp_file.read_text())

    async def enrich():
        for row in data:
            row["renewal_contract_numbers"] = "; ".join(RENEWALS.get(row["account_name"], []))
            sc = await fetch_salescloud_contacts(row["account_id"], row["account_name"])
            row["salescloud_contacts"] = sc
            supp = list(supportable_contacts.get(row["account_name"], []))
            for email in (row.get("sheet_emails") or "").split(";"):
                email = email.strip()
                if email and "@" in email:
                    supp.append({
                        "name": email.split("@")[0].replace(".", " ").title(),
                        "title": "Telemetry contact (SEAP master)",
                        "email": email,
                        "phone": "",
                    })
            row["supportable_contacts"] = supp
            all_contacts = []
            for c in supp:
                all_contacts.append({**c, "source": "supportable"})
            for c in sc:
                all_contacts.append(c)
            row["email_payload"] = build_email(row["account_name"], row["combined_use_cases"], all_contacts)
        return data

    enriched = asyncio.run(enrich())

    # HTML report
    rows_html = []
    for row in enriched:
        contact_lines = []
        for c in row.get("supportable_contacts", []):
            contact_lines.append(format_contact_line({**c, "source": "supportable"}, "#c00000"))
        for c in row.get("salescloud_contacts", []):
            contact_lines.append(format_contact_line(c, "#0066cc"))
        contacts_cell = "<br/>".join(contact_lines) if contact_lines else "<em>No contacts enriched yet</em>"
        rows_html.append(
            f"<tr>"
            f"<td>{row['rank']}</td>"
            f"<td>{html.escape(row['account_name'])}</td>"
            f"<td>{html.escape(row['combined_use_cases'])}</td>"
            f"<td>{html.escape(row['seap_case_details'])}</td>"
            f"<td>{row['total_expected_acv_eur']:,.0f}</td>"
            f"<td>{html.escape(row['renewal_contract_numbers'])}</td>"
            f"<td>{contacts_cell}</td>"
            f"</tr>"
        )

    html_doc = f"""<!DOCTYPE html>
<html><head><meta charset='utf-8'><title>NL_COMM_TERR_CORE_POD01_TERR02 Top 10</title>
<style>
body {{ font-family: Arial, sans-serif; margin: 24px; }}
table {{ border-collapse: collapse; width: 100%; font-size: 12px; }}
th, td {{ border: 1px solid #ccc; padding: 8px; vertical-align: top; }}
th {{ background: #1a1a1a; color: white; }}
.legend span {{ margin-right: 16px; }}
</style></head><body>
<h1>Territory Consolidated Report — NL_COMM_TERR_CORE_POD01_TERR02</h1>
<p>Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} | Top 10 accounts by Total Expected ACV (use-case sheet sum)</p>
<p class='legend'><span style='color:#c00000'>■ Supportable contacts</span> <span style='color:#0066cc'>■ Sales Cloud contacts &amp; leads</span></p>
<table>
<tr><th>#</th><th>Account</th><th>Combined Use Cases</th><th>SEAP Details</th><th>Total Expected ACV (EUR)</th><th>Renewal Contract #s</th><th>Contacts</th></tr>
{''.join(rows_html)}
</table></body></html>"""

    html_path = OUT / "nl_comm_terr02_top10_consolidated_report.html"
    html_path.write_text(html_doc)

    csv_path = OUT / "nl_comm_terr02_top10_consolidated_final.csv"
    with csv_path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=[
            "rank", "account_name", "account_id", "combined_use_cases", "seap_case_details",
            "total_expected_acv_eur", "renewal_contract_numbers", "contacts_combined"
        ])
        w.writeheader()
        for row in enriched:
            lines = []
            for c in row.get("supportable_contacts", []):
                lines.append(f"[RED/Supportable] {c.get('name','')} | {c.get('title','')} | {c.get('email','')} | {c.get('phone','')}")
            for c in row.get("salescloud_contacts", []):
                lines.append(f"[BLUE/SalesCloud] {c.get('name','')} | {c.get('title','')} | {c.get('email','')} | {c.get('phone','')}")
            w.writerow({
                "rank": row["rank"],
                "account_name": row["account_name"],
                "account_id": row["account_id"],
                "combined_use_cases": row["combined_use_cases"],
                "seap_case_details": row["seap_case_details"],
                "total_expected_acv_eur": row["total_expected_acv_eur"],
                "renewal_contract_numbers": row["renewal_contract_numbers"],
                "contacts_combined": " ; ".join(lines),
            })

    emails_path = OUT / "nl_comm_terr02_email_drafts.json"
    calendar_path = OUT / "nl_comm_terr02_calendar_reminders.json"
    base = datetime(2026, 9, 15, 10, 0, 0)
    reminders = []
    for i, row in enumerate(enriched):
        ep = row["email_payload"]
        send_at = base + timedelta(days=0, hours=i)
        followup_at = send_at + timedelta(days=7)
        phone_at = send_at + timedelta(days=10)
        reminders.append({
            "account": row["account_name"],
            "initial_email_subject": ep["subject"],
            "followup_email_at": followup_at.isoformat(),
            "followup_subject": ep["followup_subject"],
            "phone_reminder_at": phone_at.isoformat(),
        })

    emails_path.write_text(json.dumps([{**r["email_payload"], "account": r["account_name"]} for r in enriched], indent=2))
    calendar_path.write_text(json.dumps(reminders, indent=2))
    CONSOLIDATED.write_text(json.dumps(enriched, indent=2))
    print(f"Wrote {html_path}")
    print(f"Wrote {csv_path}")
    print(f"Wrote {emails_path}")
    print(f"Wrote {calendar_path}")


if __name__ == "__main__":
    main()
