#!/usr/bin/env python3
"""Re-apply RHSC fields and revenue splits to existing harvest output."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from territory_persona_harvest import (  # noqa: E402
    _dedupe_personas,
    _full_summaries,
    _load_account_index,
    _rhsc_meta_for_account,
    _write_final_outputs,
)
from src.territory_utils import lead_matches_territory_country, parse_territory_country


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--accounts",
        default=str(PROJECT_ROOT / "output/nl_core_territory2_accounts.json"),
    )
    parser.add_argument(
        "--personas",
        default=None,
        help="Persona JSON source (default: persona_harvest_progress.json personas)",
    )
    parser.add_argument("--output", default=str(PROJECT_ROOT / "output"))
    parser.add_argument("--prefix", default="nl_core_territory2")
    parser.add_argument(
        "--country-filter",
        action="store_true",
        help="Drop leads outside the territory country",
    )
    args = parser.parse_args()

    accounts_path = Path(args.accounts)
    output_dir = Path(args.output)

    data = json.loads(accounts_path.read_text(encoding="utf-8"))
    territory_country = data.get("territory_country") or parse_territory_country(
        data.get("territory_label") or data.get("territory")
    )
    accounts, account_by_id, territory_country = _load_account_index(data.get("accounts") or [])

    progress_candidates = [
        output_dir / f"{args.prefix}_persona_harvest_progress.json",
        output_dir / "persona_harvest_progress.json",
    ]
    progress_path = next((p for p in progress_candidates if p.exists()), progress_candidates[0])

    if args.personas:
        persona_data = json.loads(Path(args.personas).read_text(encoding="utf-8"))
        raw_personas = persona_data.get("personas") or []
    else:
        progress = (
            json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}
        )
        raw_personas = progress.get("personas") or []

    name_to_rhsc = {a["name"]: _rhsc_meta_for_account(a, territory_country) for a in accounts}

    filtered: list[dict] = []
    for p in raw_personas:
        if args.country_filter and not lead_matches_territory_country(
            p.get("location"), territory_country
        ):
            continue
        rhsc = name_to_rhsc.get(p.get("account_name") or "", {})
        filtered.append({**rhsc, **p, **rhsc})

    unique = _dedupe_personas(filtered)
    progress = json.loads(progress_path.read_text(encoding="utf-8")) if progress_path.exists() else {}
    summaries = progress.get("summaries") or []
    for s in summaries:
        rhsc = name_to_rhsc.get(s.get("account_name") or "", {})
        s.update(rhsc)
    full_summaries = _full_summaries(accounts, summaries, territory_country, account_by_id)

    if args.country_filter:
        removed = len(raw_personas) - len(unique)
        print(
            f"Filtered {removed} non-{territory_country} personas; {len(unique)} remain.",
            flush=True,
        )
    else:
        print(f"Kept all {len(unique)} personas (no country filter).", flush=True)

    _write_final_outputs(
        data,
        accounts_path,
        output_dir,
        unique,
        full_summaries,
        progress,
        accounts,
        territory_country,
        args.prefix,
    )


if __name__ == "__main__":
    main()
