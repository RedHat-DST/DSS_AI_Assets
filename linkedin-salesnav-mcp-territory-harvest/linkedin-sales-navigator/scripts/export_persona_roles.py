#!/usr/bin/env python3
"""Export harvest personas into decision_maker vs influencer Downloads buckets."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.territory_utils import classify_persona_role

OUTPUT = PROJECT_ROOT / "output"
DOWNLOADS = Path.home() / "Downloads"

PERSONA_FIELDS = [
    "account_name",
    "account_id",
    "sales_group",
    "sales_group_id",
    "global_sales_group",
    "global_sales_group_id",
    "global_arr_usd",
    "has_revenue",
    "revenue_segment",
    "billing_country",
    "territory_country",
    "sales_nav_company",
    "sales_nav_org_id",
    "name",
    "title",
    "persona_role",
    "persona_role_reason",
    "company",
    "location",
    "connection_degree",
    "sales_navigator_url",
    "profile_id",
]

ROLES = {
    "decision_maker": {
        "label": "decision_makers",
        "title": "Decision makers (C-level / VP / Director / Head of / owner)",
    },
    "influencer": {
        "label": "influencers",
        "title": "Influencers (managers, architects, engineers, leads)",
    },
}


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_personas(output_dir: Path, prefix: str) -> list[dict]:
    # Prefer live progress (newest), then final JSON, then CSV.
    progress = output_dir / f"{prefix}_persona_harvest_progress.json"
    legacy = output_dir / "persona_harvest_progress.json"
    for path in (progress, legacy):
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            personas = data.get("personas") or []
            if personas:
                return personas

    combined = output_dir / f"{prefix}_cloud_ccsp_personas.json"
    if combined.exists():
        data = json.loads(combined.read_text(encoding="utf-8"))
        return list(data.get("personas") or [])

    csv_path = output_dir / f"{prefix}_cloud_ccsp_personas.csv"
    if csv_path.exists():
        with csv_path.open(encoding="utf-8") as f:
            return list(csv.DictReader(f))
    raise SystemExit(f"No personas found under {output_dir} for prefix {prefix}")


def _dedupe(personas: list[dict]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    out: list[dict] = []
    for p in personas:
        key = (
            (p.get("profile_id") or p.get("sales_navigator_url") or p.get("name") or "").strip(),
            (p.get("account_name") or "").strip(),
        )
        if key in seen:
            continue
        seen.add(key)
        out.append(p)
    return out


def annotate_roles(personas: list[dict]) -> list[dict]:
    annotated: list[dict] = []
    for p in personas:
        role, reason = classify_persona_role(p.get("title"))
        row = dict(p)
        row["persona_role"] = role
        row["persona_role_reason"] = reason
        annotated.append(row)
    return annotated


def export_role_bucket(
    role: str,
    label: str,
    title: str,
    personas: list[dict],
    output_dir: Path,
    dest_dir: Path,
    prefix: str,
    territory_id: str,
) -> dict:
    rows = [p for p in personas if p.get("persona_role") == role]
    rows.sort(key=lambda r: ((r.get("account_name") or ""), (r.get("name") or "")))

    base = f"{territory_id}_{label}"
    out_csv = dest_dir / f"{base}_personas.csv"
    out_json = dest_dir / f"{base}_personas.json"
    readme = dest_dir / f"{base}_README.txt"
    local_csv = output_dir / f"{prefix}_cloud_ccsp_personas_{role}.csv"
    local_json = output_dir / f"{prefix}_cloud_ccsp_personas_{role}.json"

    payload = {
        "territory": territory_id,
        "persona_role": role,
        "label": label,
        "title": title,
        "persona_count": len(rows),
        "accounts_with_personas": len({p.get("account_name") for p in rows if p.get("account_name")}),
        "definition": title,
        "personas": rows,
    }
    text = json.dumps(payload, indent=2)
    out_json.write_text(text, encoding="utf-8")
    local_json.write_text(text, encoding="utf-8")
    _write_csv(out_csv, rows, PERSONA_FIELDS)
    _write_csv(local_csv, rows, PERSONA_FIELDS)
    readme.write_text(
        f"{territory_id} — {title}\n"
        f"Personas: {len(rows)} across {payload['accounts_with_personas']} accounts\n"
        f"Classification: title-based (C-level/VP/Director/Head of/owner = decision_maker; "
        f"otherwise influencer).\n",
        encoding="utf-8",
    )
    return {
        "role": role,
        "label": label,
        "personas": len(rows),
        "accounts": payload["accounts_with_personas"],
        "files": [out_csv, out_json, readme, local_csv, local_json],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Split Sales Nav personas into decision_makers vs influencers"
    )
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--prefix", default="nl_core_territory2")
    parser.add_argument(
        "--territory-id",
        default="NL_COMM_TERR_CORE_POD01_TERR02",
        help="Territory id used in Downloads filenames",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help="Export folder (default: ~/Downloads/<territory-id>_salesnav_persona_roles)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output)
    territory_id = args.territory_id
    dest_dir = (
        Path(args.dest)
        if args.dest
        else (DOWNLOADS / f"{territory_id}_salesnav_persona_roles")
    )
    dest_dir.mkdir(parents=True, exist_ok=True)

    personas = annotate_roles(_dedupe(_load_personas(output_dir, args.prefix)))
    # Also refresh a combined CSV with role columns under output/
    combined_csv = output_dir / f"{args.prefix}_cloud_ccsp_personas_with_roles.csv"
    _write_csv(combined_csv, personas, PERSONA_FIELDS)

    results = []
    for role, meta in ROLES.items():
        results.append(
            export_role_bucket(
                role,
                meta["label"],
                meta["title"],
                personas,
                output_dir,
                dest_dir,
                args.prefix,
                territory_id,
            )
        )

    print(f"Exported persona roles to {dest_dir}\n")
    print(f"  combined with roles -> {combined_csv.name} ({len(personas)} personas)")
    for r in results:
        print(
            f"  {r['label']}: {r['personas']} personas / {r['accounts']} accounts"
        )
        for f in r["files"]:
            if f.parent == dest_dir:
                print(f"    -> {f.name}")


if __name__ == "__main__":
    main()
