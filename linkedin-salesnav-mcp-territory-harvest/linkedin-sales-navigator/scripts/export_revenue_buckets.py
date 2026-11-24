#!/usr/bin/env python3
"""Export harvest into two buckets: revenue-generating vs non-revenue-generating accounts."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
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
    "company",
    "location",
    "connection_degree",
    "sales_navigator_url",
    "profile_id",
]

SUMMARY_FIELDS = [
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
    "company_resolved",
    "persona_count",
    "search_status",
]

BUCKETS = {
    "no_revenue": {
        "label": "non_revenue_generating",
        "title": "Non-revenue generating (no Red Hat ARR)",
    },
    "with_revenue": {
        "label": "revenue_generating",
        "title": "Revenue generating (Global_ARR_USD > 0)",
    },
}


def _write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def export_bucket(
    segment: str,
    label: str,
    title: str,
    output_dir: Path,
    dest_dir: Path,
    prefix: str,
    territory_id: str,
) -> dict:
    personas_src = output_dir / f"{prefix}_cloud_ccsp_personas_{segment}.json"
    summary_src = output_dir / f"{prefix}_account_persona_summary_{segment}.csv"

    if personas_src.exists():
        persona_data = json.loads(personas_src.read_text(encoding="utf-8"))
        personas = persona_data.get("personas") or []
    else:
        combined = json.loads(
            (output_dir / f"{prefix}_cloud_ccsp_personas.json").read_text(encoding="utf-8")
        )
        personas = [p for p in combined.get("personas") or [] if p.get("revenue_segment") == segment]

    if summary_src.exists():
        with summary_src.open(encoding="utf-8") as f:
            summaries = list(csv.DictReader(f))
    else:
        combined_summary = output_dir / f"{prefix}_account_persona_summary.csv"
        with combined_summary.open(encoding="utf-8") as f:
            summaries = [
                r for r in csv.DictReader(f) if r.get("revenue_segment") == segment
            ]

    base = f"{territory_id}_{label}"
    personas_csv = dest_dir / f"{base}_personas.csv"
    personas_json = dest_dir / f"{base}_personas.json"
    accounts_csv = dest_dir / f"{base}_accounts.csv"
    readme = dest_dir / f"{base}_README.txt"

    payload = {
        "territory": territory_id,
        "bucket": segment,
        "title": title,
        "persona_count": len(personas),
        "account_count": len(summaries),
        "accounts_with_personas": len({p["account_name"] for p in personas}),
        "personas": personas,
    }
    personas_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_csv(personas_csv, personas, PERSONA_FIELDS)
    _write_csv(accounts_csv, summaries, SUMMARY_FIELDS)
    readme.write_text(
        f"{territory_id} — {title}\n"
        f"Personas: {len(personas)} across {payload['accounts_with_personas']} accounts\n"
        f"Territory accounts in bucket: {len(summaries)}\n",
        encoding="utf-8",
    )

    return {
        "segment": segment,
        "label": label,
        "personas": len(personas),
        "accounts": len(summaries),
        "accounts_with_personas": payload["accounts_with_personas"],
        "files": [personas_csv, personas_json, accounts_csv, readme],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(OUTPUT))
    parser.add_argument("--prefix", default="nl_core_territory2")
    parser.add_argument(
        "--territory-id",
        default=None,
        help="Territory name for Downloads filenames (e.g. NL_COMM_TERR_CORE_POD01_TERR02)",
    )
    parser.add_argument(
        "--dest",
        default=None,
        help="Export folder (default: ~/Downloads/<territory-id>_salesnav_revenue_buckets)",
    )
    args = parser.parse_args()

    territory_id = args.territory_id or args.prefix.upper()
    dest_dir = Path(args.dest) if args.dest else (DOWNLOADS / f"{territory_id}_salesnav_revenue_buckets")
    output_dir = Path(args.output)
    dest_dir.mkdir(parents=True, exist_ok=True)

    results = []
    for segment, meta in BUCKETS.items():
        results.append(
            export_bucket(
                segment,
                meta["label"],
                meta["title"],
                output_dir,
                dest_dir,
                args.prefix,
                territory_id,
            )
        )

    print(f"Exported to {dest_dir}\n")
    for r in results:
        print(
            f"  {r['label']}: {r['personas']} personas / "
            f"{r['accounts_with_personas']} accounts with hits "
            f"({r['accounts']} territory accounts total)"
        )
        for f in r["files"]:
            print(f"    -> {f.name}")


if __name__ == "__main__":
    main()
