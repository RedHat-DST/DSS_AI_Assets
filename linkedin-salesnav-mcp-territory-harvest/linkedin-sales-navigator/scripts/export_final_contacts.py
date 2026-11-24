#!/usr/bin/env python3
"""Merge Sales Nav + ZoomInfo persona harvests into outreach-ready CSV."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT = PROJECT_ROOT / "output"
DOWNLOADS = Path.home() / "Downloads"

FIELDS = [
    "account_id",
    "account_name",
    "account_owner",
    "contact_first_name",
    "contact_last_name",
    "contact_full_name",
    "job_title",
    "management_level",
    "company_name",
    "email",
    "email_status",
    "phone",
    "linkedin_url",
    "zoominfo_person_id",
    "zoominfo_company_id",
    "sales_navigator_url",
    "profile_id",
    "persona_relevance_score",
    "persona_match_reason",
    "country",
    "city",
    "source",
]


def split_name(full: str) -> tuple[str, str]:
    parts = (full or "").strip().split()
    if not parts:
        return "", ""
    if len(parts) == 1:
        return parts[0], ""
    return parts[0], " ".join(parts[1:])


def norm_name(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (name or "").lower())


def load_salesnav() -> list[dict]:
    path = OUTPUT / "nl_core_territory2_cloud_ccsp_personas.json"
    if not path.exists():
        progress = OUTPUT / "persona_harvest_progress.json"
        if not progress.exists():
            return []
        data = json.loads(progress.read_text(encoding="utf-8"))
        return data.get("personas") or []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("personas") or []


def load_zoominfo() -> list[dict]:
    for progress_name in ("zoominfo_harvest_progress_v2.json", "zoominfo_harvest_progress.json"):
        progress = OUTPUT / progress_name
        if progress.exists():
            data = json.loads(progress.read_text(encoding="utf-8"))
            contacts = data.get("contacts") or []
            if contacts:
                return contacts
    path = OUTPUT / "nl_comm_terr_core_pod01_terr02_cloud_ccsp_contacts.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("contacts") or []
    return []


def load_accounts() -> dict[str, dict]:
    path = OUTPUT / "nl_comm_terr_core_pod01_terr02_accounts.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    return {a["account_name"]: a for a in data.get("accounts", [])}


def to_row(raw: dict, accounts: dict[str, dict]) -> dict:
    acct_name = raw.get("account_name") or ""
    acct = accounts.get(acct_name, {})
    first = raw.get("contact_first_name") or raw.get("first_name")
    last = raw.get("contact_last_name") or raw.get("last_name")
    full = raw.get("contact_full_name") or raw.get("name")
    if not first and full:
        first, last = split_name(full)
    return {
        "account_id": raw.get("account_id") or acct.get("account_id"),
        "account_name": acct_name,
        "account_owner": raw.get("account_owner") or acct.get("owner_alias"),
        "contact_first_name": first,
        "contact_last_name": last,
        "contact_full_name": full or " ".join(x for x in (first, last) if x),
        "job_title": raw.get("job_title") or raw.get("title"),
        "management_level": raw.get("management_level"),
        "company_name": raw.get("company_name") or raw.get("company"),
        "email": raw.get("email"),
        "email_status": raw.get("email_status") or ("missing" if not raw.get("email") else "verified"),
        "phone": raw.get("phone"),
        "linkedin_url": raw.get("linkedin_url") or raw.get("sales_navigator_url"),
        "zoominfo_person_id": raw.get("zoominfo_person_id"),
        "zoominfo_company_id": raw.get("zoominfo_company_id"),
        "sales_navigator_url": raw.get("sales_navigator_url"),
        "profile_id": raw.get("profile_id"),
        "persona_relevance_score": raw.get("persona_relevance_score", 50),
        "persona_match_reason": raw.get("persona_match_reason") or raw.get("source", "salesnav"),
        "country": raw.get("country") or acct.get("country") or "Netherlands",
        "city": raw.get("city") or raw.get("location"),
        "source": raw.get("source") or "salesnav",
    }


def merge(salesnav: list[dict], zoominfo: list[dict], accounts: dict[str, dict]) -> list[dict]:
    merged: dict[tuple[str, str], dict] = {}
    for raw in salesnav:
        row = to_row(raw, accounts)
        row["source"] = "salesnav"
        key = (row["account_name"], norm_name(row["contact_full_name"]))
        merged[key] = row
    for raw in zoominfo:
        row = to_row(raw, accounts)
        row["source"] = "zoominfo"
        key = (row["account_name"], norm_name(row["contact_full_name"]))
        if key in merged:
            existing = merged[key]
            for field in ("email", "phone", "linkedin_url", "zoominfo_person_id", "zoominfo_company_id", "management_level"):
                if row.get(field) and not existing.get(field):
                    existing[field] = row[field]
            existing["source"] = "salesnav+zoominfo"
            if row.get("email"):
                existing["email_status"] = row.get("email_status") or "verified"
        else:
            merged[key] = row
    rows = list(merged.values())
    rows.sort(key=lambda r: (r["account_name"] or "", -(r["persona_relevance_score"] or 0)))
    return rows


def write_outputs(rows: list[dict]) -> None:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT / "nl_comm_terr_core_pod01_terr02_cloud_ccsp_contacts_merged.json"
    csv_path = OUTPUT / "nl_comm_terr_core_pod01_terr02_cloud_ccsp_contacts_merged.csv"
    dl_csv = DOWNLOADS / "NL_COMM_TERR_CORE_POD01_TERR02_cloud_ccsp_contacts.csv"
    dl_summary = DOWNLOADS / "NL_COMM_TERR_CORE_POD01_TERR02_summary.csv"

    payload = {
        "territory": "NL_COMM_TERR_CORE_POD01_TERR02",
        "contact_count": len(rows),
        "accounts_with_personas": len({r["account_name"] for r in rows}),
        "contacts_with_email": len([r for r in rows if r.get("email")]),
        "contacts": rows,
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    for path in (csv_path, dl_csv):
        with path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)

    summary_rows = []
    by_acct: dict[str, list[dict]] = {}
    for r in rows:
        by_acct.setdefault(r["account_name"], []).append(r)
    for acct, contacts in sorted(by_acct.items()):
        top = contacts[0]
        summary_rows.append(
            {
                "account_name": acct,
                "account_id": top.get("account_id"),
                "contacts_found": len(contacts),
                "top_contact_name": top.get("contact_full_name"),
                "top_contact_title": top.get("job_title"),
                "top_contact_email": top.get("email") or "",
            }
        )
    with dl_summary.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "account_name",
                "account_id",
                "contacts_found",
                "top_contact_name",
                "top_contact_title",
                "top_contact_email",
            ],
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    print(f"Merged {len(rows)} contacts -> {dl_csv}")
    print(f"Summary -> {dl_summary}")


def main() -> None:
    accounts = load_accounts()
    rows = merge(load_salesnav(), load_zoominfo(), accounts)
    write_outputs(rows)


if __name__ == "__main__":
    main()
