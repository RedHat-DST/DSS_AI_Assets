#!/usr/bin/env python3
"""Filter New Pipe / territory opps locally (no LLM).

Input: JSON array or {"records": [...]} / report-like rows from Sales Cloud export.
Output:
  - masked chat table (stdout + file)
  - vault JSON (PII / ACV)
  - cleartext working set for tool rehydration only (local, do not paste in chat)

Example:
  python filter_pipeline_opps.py \\
    --in opps.json \\
    --out-dir ~/.cursor/skills/relance-new-pipe/output \\
    --close-from 2026-09-01 --close-to 2026-12-31
"""

from __future__ import annotations

import argparse
import json
import re
from datetime import date, datetime
from pathlib import Path
from typing import Any

from pii_vault import PiiVault

NOT_THIS_YEAR = re.compile(
    r"not this year|hors ann[eé]e|pas cette ann[eé]e|push to 20\d{2}",
    re.I,
)

FIELD_ALIASES = {
    "id": ("Id", "id", "OpportunityId", "Opportunity ID"),
    "name": ("Name", "name", "Opportunity Name", "Sujet", "OpportunityName"),
    "account": ("AccountName", "Account", "Compte", "account", "Account.Name"),
    "stage": ("StageName", "Stage", "stage"),
    "forecast": ("ForecastCategoryName", "ForecastCategory", "Forecast", "forecast"),
    "close": ("CloseDate", "close", "Close Date", "Date de clôture"),
    "owner": ("OwnerAlias", "OwnerName", "Owner", "owner"),
    "acv": ("Amount", "ACV", "acv", "ExpectedRevenue"),
    "next_steps": ("Next_Steps__c", "NextSteps", "Next Steps", "next_steps"),
    "opp_number": ("OpportunityNumber", "OppNumber", "Opp#", "Opportunity_Number__c"),
}


def _get(row: dict[str, Any], key: str) -> Any:
    for alias in FIELD_ALIASES[key]:
        if alias in row and row[alias] not in (None, ""):
            return row[alias]
        # nested Account.Name style flattened
        if "." not in alias and any(k.endswith("." + alias) or k == alias for k in row):
            for k, v in row.items():
                if k == alias or k.endswith("." + alias):
                    if v not in (None, ""):
                        return v
    return ""


def _parse_date(val: Any) -> date | None:
    if not val:
        return None
    if isinstance(val, date) and not isinstance(val, datetime):
        return val
    s = str(val)[:10]
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _load_rows(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("records", "rows", "opportunities", "data", "factMap"):
            if key in data and isinstance(data[key], list):
                return [r for r in data[key] if isinstance(r, dict)]
        # single report cell dump
        if all(isinstance(v, (str, int, float, type(None))) for v in data.values()):
            return [data]
    raise SystemExit(f"Unrecognized JSON shape in {path}")


def filter_rows(
    rows: list[dict[str, Any]],
    *,
    close_from: date | None,
    close_to: date | None,
    forecast_only: str = "Pipeline",
) -> list[dict[str, Any]]:
    kept: list[dict[str, Any]] = []
    for row in rows:
        forecast = str(_get(row, "forecast") or "")
        if forecast_only and forecast_only.lower() not in forecast.lower():
            # exact-ish: require Pipeline token when category present
            if forecast and forecast.strip().lower() != forecast_only.lower():
                continue
        close = _parse_date(_get(row, "close"))
        if close_from and close and close < close_from:
            continue
        if close_to and close and close > close_to:
            continue
        next_steps = str(_get(row, "next_steps") or "")
        if next_steps and NOT_THIS_YEAR.search(next_steps):
            continue
        kept.append(
            {
                "id": str(_get(row, "id") or ""),
                "opp_number": str(_get(row, "opp_number") or ""),
                "account": str(_get(row, "account") or ""),
                "name": str(_get(row, "name") or ""),
                "stage": str(_get(row, "stage") or ""),
                "acv": str(_get(row, "acv") or ""),
                "close": close.isoformat() if close else str(_get(row, "close") or ""),
                "owner": str(_get(row, "owner") or ""),
                "forecast": forecast or forecast_only,
                "next_steps": next_steps[:500],
            }
        )
    return kept


def main() -> int:
    ap = argparse.ArgumentParser(description="Filter Pipeline opps + emit masked chat table")
    ap.add_argument("--in", dest="infile", type=Path, required=True)
    ap.add_argument(
        "--out-dir",
        type=Path,
        default=Path.home() / ".cursor/skills/relance-new-pipe/output",
    )
    ap.add_argument("--close-from", type=str, default="")
    ap.add_argument("--close-to", type=str, default="")
    ap.add_argument("--forecast", type=str, default="Pipeline")
    args = ap.parse_args()

    close_from = _parse_date(args.close_from) if args.close_from else None
    close_to = _parse_date(args.close_to) if args.close_to else None

    rows = filter_rows(
        _load_rows(args.infile),
        close_from=close_from,
        close_to=close_to,
        forecast_only=args.forecast,
    )

    vault = PiiVault()
    masked_rows: list[dict[str, Any]] = []
    for row in rows:
        masked_rows.append(
            vault.mask_record(
                row,
                {
                    "account": "ACCT",
                    "name": "OPP",
                    "acv": "ACV",
                    "owner": "OWNER",
                    "id": "SFID",
                },
                text_fields=["next_steps"],
                mask_amounts_in=["next_steps"],
            )
        )
        # also mask emails inside next_steps cleartext path already via mask_record

    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    clear_path = out_dir / "pipeline_opps.clear.json"
    masked_path = out_dir / "pipeline_opps.masked.json"
    vault_path = out_dir / "pipeline_opps.vault.json"
    table_path = out_dir / "pipeline_opps.chat.md"

    clear_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
    masked_path.write_text(json.dumps(masked_rows, indent=2, ensure_ascii=False), encoding="utf-8")
    vault.save(vault_path)

    lines = [
        "| # | Opp token | Acct token | Stage | ACV token | Close | Owner token | Forecast | Next Steps (masked) |",
        "|---|-----------|------------|-------|-----------|-------|-------------|----------|---------------------|",
    ]
    for i, m in enumerate(masked_rows, 1):
        ns = (m.get("next_steps") or "").replace("|", "/").replace("\n", " ")[:120]
        lines.append(
            f"| {i} | {m.get('name') or m.get('opp_number') or m.get('id')} | {m.get('account')} | "
            f"{m.get('stage')} | {m.get('acv')} | {m.get('close')} | {m.get('owner')} | "
            f"{m.get('forecast')} | {ns} |"
        )
    table = "\n".join(lines) + "\n"
    table_path.write_text(table, encoding="utf-8")

    print(f"Kept {len(rows)} Pipeline opps")
    print(f"Clear (local only, do not paste in chat): {clear_path}")
    print(f"Masked (safe for agent/chat): {masked_path}")
    print(f"Vault (local rehydrate): {vault_path}")
    print(f"Chat table: {table_path}")
    print()
    print("=== PASTE ONLY THE MASKED TABLE BELOW ===")
    print(table)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
