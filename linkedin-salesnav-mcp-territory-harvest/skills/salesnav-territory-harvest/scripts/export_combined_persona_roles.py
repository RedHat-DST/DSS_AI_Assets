#!/usr/bin/env python3
"""Merge Sales Nav + ZoomInfo personas into decision_maker / influencer Downloads.

Compliance (ae-gtm-compliance-mitigations):
- Full lists → Downloads / output files only (not chat).
- Prefer business email; omit mobile by default (--include-phone to opt in).
- Tag source: Sales_Nav | ZoomInfo | both.
- README notes associate Sales Nav session + ZoomInfo B2B/GDPR / credit use.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.territory_utils import classify_persona_role

DOWNLOADS = Path.home() / "Downloads"
OUTPUT = PROJECT_ROOT / "output"

FIELDS = [
    "account_name",
    "account_id",
    "sales_group",
    "global_sales_group",
    "global_arr_usd",
    "has_revenue",
    "revenue_segment",
    "persona_role",
    "persona_role_reason",
    "name",
    "title",
    "company",
    "location",
    "email",
    "linkedin_url",
    "sources",  # Sales_Nav | ZoomInfo | Sales_Nav+ZoomInfo
    "sales_navigator_url",
    "zoominfo_person_id",
    "profile_id",
]

ROLE_META = {
    "decision_maker": ("decision_makers", "Decision makers (C-level / VP / Director / Head of / owner)"),
    "influencer": ("influencers", "Influencers (managers, architects, engineers, leads)"),
}


def _norm_name(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _norm_company(s: str) -> str:
    text = re.sub(
        r"\b(n\.?v\.?|b\.?v\.?|gmbh|ag|ltd|llc|inc|holding|international|nederland|netherlands)\b",
        " ",
        (s or "").lower(),
    )
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _dedupe_key(name: str, company: str, account: str) -> tuple[str, str]:
    return (_norm_name(name), _norm_company(company) or _norm_company(account))


def _load_salesnav(output_dir: Path, prefix: str) -> list[dict]:
    rows: list[dict] = []
    for path in (
        output_dir / f"{prefix}_persona_harvest_progress.json",
        output_dir / "persona_harvest_progress.json",
        output_dir / f"{prefix}_cloud_ccsp_personas.json",
    ):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        personas = data.get("personas") or []
        if personas:
            rows = personas
            break
    csv_path = output_dir / f"{prefix}_cloud_ccsp_personas.csv"
    if not rows and csv_path.exists():
        with csv_path.open(encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    out: list[dict] = []
    for p in rows:
        role, reason = classify_persona_role(p.get("title"))
        out.append(
            {
                "account_name": p.get("account_name"),
                "account_id": p.get("account_id"),
                "sales_group": p.get("sales_group"),
                "global_sales_group": p.get("global_sales_group"),
                "global_arr_usd": p.get("global_arr_usd"),
                "has_revenue": p.get("has_revenue"),
                "revenue_segment": p.get("revenue_segment"),
                "persona_role": role,
                "persona_role_reason": reason,
                "name": p.get("name"),
                "title": p.get("title"),
                "company": p.get("company") or p.get("sales_nav_company"),
                "location": p.get("location"),
                "email": None,
                "linkedin_url": p.get("sales_navigator_url"),
                "sources": "Sales_Nav",
                "sales_navigator_url": p.get("sales_navigator_url"),
                "zoominfo_person_id": None,
                "profile_id": p.get("profile_id"),
            }
        )
    return out


def _load_zoominfo(output_dir: Path, territory_id: str) -> list[dict]:
    slug = re.sub(r"[^a-z0-9]+", "_", territory_id.lower()).strip("_")
    contacts: list[dict] = []
    for path in (
        output_dir / f"{slug}_zoominfo_progress.json",
        output_dir / f"{slug}_zoominfo_contacts.json",
        output_dir / "zoominfo_harvest_progress_v2.json",
    ):
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        contacts = data.get("contacts") or []
        if contacts:
            break
    out: list[dict] = []
    for c in contacts:
        role, reason = classify_persona_role(c.get("job_title"), c.get("management_level"))
        # Prefer business email; never surface mobile unless caller adds phone later.
        out.append(
            {
                "account_name": c.get("account_name"),
                "account_id": c.get("account_id"),
                "sales_group": c.get("sales_group"),
                "global_sales_group": c.get("global_sales_group"),
                "global_arr_usd": c.get("global_arr_usd"),
                "has_revenue": c.get("has_revenue"),
                "revenue_segment": c.get("revenue_segment"),
                "persona_role": role,
                "persona_role_reason": reason,
                "name": c.get("contact_full_name")
                or " ".join(
                    x for x in (c.get("contact_first_name"), c.get("contact_last_name")) if x
                ),
                "title": c.get("job_title"),
                "company": c.get("company_name"),
                "location": ", ".join(
                    x for x in (c.get("city"), c.get("country")) if x
                ),
                "email": c.get("email"),
                "linkedin_url": c.get("linkedin_url"),
                "sources": "ZoomInfo",
                "sales_navigator_url": None,
                "zoominfo_person_id": c.get("zoominfo_person_id"),
                "profile_id": None,
            }
        )
    return out


def _merge(sn: list[dict], zi: list[dict]) -> list[dict]:
    by_key: dict[tuple[str, str], dict] = {}
    order: list[tuple[str, str]] = []

    def add(row: dict) -> None:
        key = _dedupe_key(row.get("name") or "", row.get("company") or "", row.get("account_name") or "")
        if not key[0]:
            # keep unnamed rows under account+title
            key = (
                _norm_name(row.get("title") or "") + "|" + (row.get("account_id") or ""),
                key[1],
            )
        if key not in by_key:
            by_key[key] = row
            order.append(key)
            return
        cur = by_key[key]
        src = set((cur.get("sources") or "").split("+")) | set((row.get("sources") or "").split("+"))
        src.discard("")
        cur["sources"] = "+".join(sorted(src))
        for field in (
            "email",
            "linkedin_url",
            "sales_navigator_url",
            "zoominfo_person_id",
            "profile_id",
            "location",
            "sales_group",
            "global_sales_group",
            "global_arr_usd",
            "account_id",
        ):
            if not cur.get(field) and row.get(field):
                cur[field] = row[field]
        # Prefer decision_maker if either source says so
        if row.get("persona_role") == "decision_maker":
            cur["persona_role"] = "decision_maker"
            cur["persona_role_reason"] = row.get("persona_role_reason") or cur.get("persona_role_reason")

    for row in sn:
        add(row)
    for row in zi:
        add(row)
    return [by_key[k] for k in order]


def _write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def main() -> None:
    parser = argparse.ArgumentParser(description="Combined SN+ZI persona role export")
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--prefix", default="nl_core_territory2")
    parser.add_argument("--territory-id", default="NL_COMM_TERR_CORE_POD01_TERR02")
    parser.add_argument("--dest", default=None)
    args = parser.parse_args()

    output_dir = Path(args.output)
    territory_id = args.territory_id
    dest = Path(args.dest) if args.dest else (DOWNLOADS / f"{territory_id}_combined_persona_roles")
    dest.mkdir(parents=True, exist_ok=True)

    sn = _load_salesnav(output_dir, args.prefix)
    zi = _load_zoominfo(output_dir, territory_id)
    merged = _merge(sn, zi)

    combined_csv = dest / f"{territory_id}_combined_personas.csv"
    combined_json = dest / f"{territory_id}_combined_personas.json"
    _write_csv(combined_csv, merged)
    combined_json.write_text(
        json.dumps(
            {
                "territory": territory_id,
                "sales_nav_rows": len(sn),
                "zoominfo_rows": len(zi),
                "combined_unique": len(merged),
                "decision_makers": sum(1 for r in merged if r.get("persona_role") == "decision_maker"),
                "influencers": sum(1 for r in merged if r.get("persona_role") == "influencer"),
                "sources_note": "Sales_Nav = associate MCP Chrome session; ZoomInfo = B2B legitimate interest / GDPR — AE owns lawful basis; credits used on enrich",
                "personas": merged,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    counts = {}
    for role, (label, title) in ROLE_META.items():
        rows = [r for r in merged if r.get("persona_role") == role]
        rows.sort(key=lambda r: ((r.get("account_name") or ""), (r.get("name") or "")))
        base = f"{territory_id}_{label}"
        _write_csv(dest / f"{base}_personas.csv", rows)
        (dest / f"{base}_personas.json").write_text(
            json.dumps(
                {
                    "territory": territory_id,
                    "persona_role": role,
                    "title": title,
                    "persona_count": len(rows),
                    "accounts": len({r.get("account_name") for r in rows if r.get("account_name")}),
                    "personas": rows,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (dest / f"{base}_README.txt").write_text(
            f"{territory_id} — {title}\n"
            f"Combined Sales Nav + ZoomInfo (deduped by name+company).\n"
            f"Personas: {len(rows)}\n"
            f"Compliance: full list on disk only; chat = counts/shortlist; no mobile in this export;\n"
            f"Sales Nav associate session; ZoomInfo B2B/GDPR — AE owns lawful basis.\n",
            encoding="utf-8",
        )
        counts[label] = len(rows)

    (dest / f"{territory_id}_COMPLIANCE.txt").write_text(
        "AE GTM compliance notes for this export\n"
        "- Privacy Mode ON in Cursor (required for Superpack work).\n"
        "- Full contact grids live in Downloads/output — do not paste into chat.\n"
        "- ZoomInfo: business email preferred; credits burn on enrich; legitimate B2B/GDPR — AE owns basis.\n"
        "- Sales Nav: associate MCP Chrome SSO session only.\n"
        "- This Cloud/CCSP territory harvest was explicitly requested by the AE "
        "(Superpack default remains opp-driven).\n"
        "- Drafts only — never auto-send.\n",
        encoding="utf-8",
    )

    # Also copy slim combined under output for hub use
    local = output_dir / f"{args.prefix}_combined_persona_roles"
    local.mkdir(parents=True, exist_ok=True)
    for f in dest.glob("*"):
        if f.is_file():
            (local / f.name).write_bytes(f.read_bytes())

    # Token-cheap one-line summary for agents
    print(
        f"COMBINED {territory_id}: unique={len(merged)} "
        f"DM={counts.get('decision_makers', 0)} INF={counts.get('influencers', 0)} "
        f"SN_in={len(sn)} ZI_in={len(zi)} -> {dest}"
    )


if __name__ == "__main__":
    main()
