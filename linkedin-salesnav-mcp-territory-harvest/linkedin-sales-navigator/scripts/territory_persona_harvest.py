#!/usr/bin/env python3
"""Harvest Cloud/CCSP personas from Sales Navigator for RHSC territory accounts."""

from __future__ import annotations

import argparse
import asyncio
import csv
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.auth import AuthRequired, get_auth
from src.harvest_pacing import (
    PacingConfig,
    pace_batch_break,
    pace_between_accounts,
    pace_between_requests,
)
from src.linkedin import RateLimited, SessionExpired, _company_match_score, _normalize_company_name
from src.territory_utils import (
    company_query_variants,
    lead_matches_territory_country,
    parse_territory_country,
    region_filter_for_country,
)

CLOUD_KEYWORDS = re.compile(
    r"\b(cloud|ccsp|openshift|kubernetes|k8s|platform\s+eng|devops|sre|"
    r"site reliability|infrastructure|hybrid cloud|cloud ops|cloud operat|"
    r"cloud arch|cloud eng|virtuali[sz]ation|data\s*cent|iaas|paas|saas|"
    r"multi[\s-]?cloud|private cloud|public cloud|container)\b",
    re.I,
)

RHSC_ACCOUNT_FIELDS = [
    "sales_group",
    "sales_group_id",
    "global_sales_group",
    "global_sales_group_id",
    "global_arr_usd",
    "has_revenue",
    "revenue_segment",
    "billing_country",
    "territory_country",
]

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
    "company_query_variant",
    "company_match_score",
    "company_resolved",
    "persona_count",
    "search_status",
]


def is_cloud_persona(lead: dict) -> bool:
    title = lead.get("title") or ""
    if not title.strip():
        return False
    blob = " ".join(str(lead.get(k) or "") for k in ("title", "summary"))
    return bool(CLOUD_KEYWORDS.search(blob))


def normalize_company_name(name: str) -> str:
    return re.sub(r"\s+", " ", (name or "")).strip()


def _lead_matches_company(lead: dict, company: str, sales_nav_company: str | None = None) -> bool:
    lead_company = (lead.get("company") or "").strip()
    if not lead_company:
        return False
    targets = [company]
    if sales_nav_company:
        targets.append(sales_nav_company)
    for target in targets:
        if _company_match_score(target, lead_company) >= 0.5:
            return True
    return False


def _write_csv(csv_file: Path, rows: list[dict], fieldnames: list[str]) -> None:
    with csv_file.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _load_account_index(accounts_raw: list) -> tuple[list[dict], dict[str, dict], str]:
    territory_country = "Netherlands"
    accounts: list[dict] = []
    by_id: dict[str, dict] = {}
    for row in accounts_raw:
        if not isinstance(row, dict):
            continue
        name = row.get("account_name") or row.get("Name") or row.get("name")
        aid = row.get("account_id") or row.get("Id") or row.get("id")
        if not name:
            continue
        territory_country = row.get("territory_country") or territory_country
        rhsc = {k: row.get(k) for k in RHSC_ACCOUNT_FIELDS if k in row}
        entry = {
            "id": aid,
            "name": normalize_company_name(str(name)),
            **rhsc,
        }
        accounts.append(entry)
        if aid:
            by_id[str(aid)] = entry
    return accounts, by_id, territory_country


def _rhsc_meta_for_account(acct: dict, territory_country: str) -> dict:
    return {
        "sales_group": acct.get("sales_group"),
        "sales_group_id": acct.get("sales_group_id"),
        "global_sales_group": acct.get("global_sales_group"),
        "global_sales_group_id": acct.get("global_sales_group_id"),
        "global_arr_usd": acct.get("global_arr_usd"),
        "has_revenue": acct.get("has_revenue"),
        "revenue_segment": acct.get("revenue_segment"),
        "billing_country": acct.get("billing_country"),
        "territory_country": acct.get("territory_country") or territory_country,
    }


def _collect_personas(
    leads: list[dict],
    company: str,
    result: dict,
    seen_ids: set[str],
    *,
    territory_country: str,
    rhsc_meta: dict,
    filter_country: bool = False,
) -> list[dict]:
    personas: list[dict] = []
    for lead in leads:
        pid = str(lead.get("profile_id") or lead.get("entity_urn") or "")
        if not pid or pid in seen_ids:
            continue
        if not _lead_matches_company(lead, company, result.get("display_name")):
            continue
        if filter_country and not lead_matches_territory_country(
            lead.get("location"), territory_country
        ):
            continue
        if not is_cloud_persona(lead):
            continue
        seen_ids.add(pid)
        personas.append(
            {
                "account_name": company,
                **rhsc_meta,
                "name": lead.get("name"),
                "title": lead.get("title"),
                "company": lead.get("company"),
                "location": lead.get("location"),
                "connection_degree": lead.get("connection_degree"),
                "sales_navigator_url": lead.get("sales_navigator_url"),
                "profile_id": lead.get("profile_id"),
                "sales_nav_company": result.get("display_name"),
                "sales_nav_org_id": result.get("org_id"),
            }
        )
    return personas


async def search_account_personas(
    client,
    company: str,
    *,
    territory_country: str,
    rhsc_meta: dict,
    account: dict | None = None,
    limit: int = 25,
    filter_country: bool = False,
    pacing: PacingConfig | None = None,
) -> tuple[list[dict], dict]:
    meta = {
        "company_resolved": False,
        "sales_nav_company": None,
        "sales_nav_org_id": None,
        "company_query_variant": None,
        "company_match_score": None,
        "search_status": "no_company_match",
        **rhsc_meta,
    }
    region_name, region_id = (None, None)
    if filter_country:
        region = region_filter_for_country(territory_country)
        if region:
            region_name, region_id = region

    resolve_account = account or {
        "name": company,
        "account_name": company,
        "sales_group": rhsc_meta.get("sales_group"),
        "global_sales_group": rhsc_meta.get("global_sales_group"),
    }
    variants = company_query_variants(resolve_account)
    if variants:
        print(f"  company queries: {' | '.join(variants[:6])}", flush=True)

    result = await client.search_leads_at_company(
        company,
        count=limit,
        region_name=region_name,
        region_id=region_id,
        account=resolve_account,
    )
    if pacing:
        await pace_between_requests(pacing)
    if not result.get("resolved"):
        return [], meta

    meta.update(
        {
            "company_resolved": True,
            "sales_nav_company": result.get("display_name"),
            "sales_nav_org_id": result.get("org_id"),
            "company_query_variant": result.get("query_variant"),
            "company_match_score": result.get("match_score"),
            "search_status": "ok",
        }
    )

    seen_ids: set[str] = set()
    personas = _collect_personas(
        result.get("leads") or [],
        company,
        result,
        seen_ids,
        territory_country=territory_country,
        rhsc_meta=rhsc_meta,
        filter_country=filter_country,
    )
    if not personas:
        if pacing:
            await pace_between_requests(pacing)
        refined = await client.search_leads_at_company(
            company,
            org_id=result.get("org_id"),
            display_name=result.get("display_name"),
            keywords="cloud openshift devops infrastructure platform architect",
            count=limit,
            region_name=region_name,
            region_id=region_id,
        )
        personas = _collect_personas(
            refined.get("leads") or [],
            company,
            result,
            seen_ids,
            territory_country=territory_country,
            rhsc_meta=rhsc_meta,
            filter_country=filter_country,
        )
        if personas:
            meta["search_status"] = "ok_keyword_refine"
    return personas, meta


def _split_by_revenue(
    personas: list[dict],
    summaries: list[dict],
    prefix: str,
    output_dir: Path,
) -> None:
    for segment, label in (("no_revenue", "no_revenue"), ("with_revenue", "with_revenue")):
        seg_personas = [p for p in personas if p.get("revenue_segment") == segment]
        seg_summaries = [s for s in summaries if s.get("revenue_segment") == segment]
        _write_csv(
            output_dir / f"{prefix}_cloud_ccsp_personas_{label}.csv",
            seg_personas,
            PERSONA_FIELDS,
        )
        _write_csv(
            output_dir / f"{prefix}_account_persona_summary_{label}.csv",
            seg_summaries,
            SUMMARY_FIELDS,
        )
        (output_dir / f"{prefix}_cloud_ccsp_personas_{label}.json").write_text(
            json.dumps(
                {
                    "revenue_segment": segment,
                    "persona_count": len(seg_personas),
                    "accounts_with_personas": len({p["account_name"] for p in seg_personas}),
                    "personas": seg_personas,
                    "summaries": seg_summaries,
                },
                indent=2,
            ),
            encoding="utf-8",
        )


def _write_final_outputs(
    data: dict,
    accounts_path: Path,
    output_dir: Path,
    unique: list[dict],
    full_summaries: list[dict],
    progress: dict,
    accounts: list[dict],
    territory_country: str,
    prefix: str,
) -> None:
    json_file = output_dir / f"{prefix}_cloud_ccsp_personas.json"
    csv_file = output_dir / f"{prefix}_cloud_ccsp_personas.csv"
    summary_file = output_dir / f"{prefix}_account_persona_summary.csv"

    payload = {
        "territory": data.get("territory") or data.get("territory_label") or "Netherlands Core Territory 2",
        "territory_country": territory_country,
        "source_accounts": accounts_path.name,
        "accounts_searched": len(progress.get("done") or []),
        "accounts_with_personas": len({p["account_name"] for p in unique}),
        "persona_count": len(unique),
        "personas_no_revenue": len([p for p in unique if p.get("revenue_segment") == "no_revenue"]),
        "personas_with_revenue": len([p for p in unique if p.get("revenue_segment") == "with_revenue"]),
        "personas": unique,
        "summaries": full_summaries,
    }
    json_file.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _write_csv(csv_file, unique, PERSONA_FIELDS)
    _write_csv(summary_file, full_summaries, SUMMARY_FIELDS)
    _split_by_revenue(unique, full_summaries, prefix, output_dir)

    print(
        f"Done. {len(unique)} personas across {payload['accounts_with_personas']} accounts "
        f"(no_revenue={payload['personas_no_revenue']}, with_revenue={payload['personas_with_revenue']}) "
        f"-> {json_file}",
        flush=True,
    )
    print(f"Full account summary -> {summary_file}", flush=True)
    print(f"Split lists -> {prefix}_*_no_revenue / *_with_revenue", flush=True)


async def _harvest_one_account(
    client,
    auth,
    acct: dict,
    *,
    territory_country: str,
    filter_country: bool,
    pacing: PacingConfig,
    progress: dict,
    progress_file: Path,
    all_personas: list[dict],
    summaries: list[dict],
) -> tuple[str, bool]:
    """Process one account. Returns (status, should_stop_run). status: ok|rate_limited|session|auth|error."""
    company = acct["name"]
    rhsc_meta = _rhsc_meta_for_account(acct, territory_country)
    try:
        personas, meta = await search_account_personas(
            client,
            company,
            territory_country=territory_country,
            rhsc_meta=rhsc_meta,
            account=acct,
            filter_country=filter_country,
            pacing=pacing,
        )
        for p in personas:
            p["account_id"] = acct.get("id")
        all_personas.extend(personas)
        summaries.append(
            {
                "account_name": company,
                "account_id": acct.get("id"),
                "sales_nav_company": meta.get("sales_nav_company"),
                "sales_nav_org_id": meta.get("sales_nav_org_id"),
                "company_query_variant": meta.get("company_query_variant"),
                "company_match_score": meta.get("company_match_score"),
                "company_resolved": meta.get("company_resolved"),
                "persona_count": len(personas),
                "search_status": meta.get("search_status"),
                **rhsc_meta,
            }
        )
        progress["done"].append(company)
        progress["personas"] = all_personas
        progress["summaries"] = summaries
        rate_limited = progress.get("rate_limited") or []
        if company in rate_limited:
            progress["rate_limited"] = [c for c in rate_limited if c != company]
        progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")
        print(
            f"  -> {len(personas)} personas | resolved={meta.get('company_resolved')} "
            f"| {meta.get('sales_nav_company') or 'n/a'}",
            flush=True,
        )
        return "ok", False
    except SessionExpired:
        print("  -> session expired, reconnecting browser client...", flush=True)
        auth.clear_client()
        try:
            await auth.ensure_client()
        except AuthRequired:
            print("AUTH REQUIRED — open linkedin.com/sales in MCP Chrome", file=sys.stderr)
            sys.exit(2)
        return "session", False
    except RateLimited:
        progress.setdefault("rate_limited", []).append(company)
        progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")
        print("  -> rate limited, deferring to next run", flush=True)
        return "rate_limited", False
    except AuthRequired as e:
        print(f"AUTH REQUIRED: {e}", file=sys.stderr)
        sys.exit(2)
    except Exception as e:
        progress.setdefault("errors", []).append({"account": company, "error": str(e)})
        progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")
        print(f"  -> error: {e}", flush=True)
        return "error", False


def _requeue_unmatched(progress: dict) -> int:
    """Pull no_company_match accounts out of done so name/Sales Group fallbacks can retry."""
    unmatched = {
        (s.get("account_name") or "").strip()
        for s in (progress.get("summaries") or [])
        if (s.get("search_status") or "") == "no_company_match" and (s.get("account_name") or "").strip()
    }
    if not unmatched:
        return 0
    progress["done"] = [n for n in (progress.get("done") or []) if n not in unmatched]
    progress["summaries"] = [
        s for s in (progress.get("summaries") or []) if (s.get("account_name") or "").strip() not in unmatched
    ]
    # Keep any personas already captured for other accounts; drop unmatched rows if present.
    progress["personas"] = [
        p for p in (progress.get("personas") or []) if (p.get("account_name") or "").strip() not in unmatched
    ]
    progress["fallback_retry_queued"] = sorted(unmatched)
    return len(unmatched)


async def run(
    accounts_path: Path,
    output_dir: Path,
    *,
    start: int = 0,
    max_accounts: int | None = None,
    fresh: bool = False,
    retry_unmatched: bool = False,
    prefix: str = "nl_core_territory2",
    filter_country: bool = False,
    pacing: PacingConfig | None = None,
) -> None:
    pacing = pacing or PacingConfig()
    data = json.loads(accounts_path.read_text(encoding="utf-8"))
    territory_country = data.get("territory_country") or parse_territory_country(
        data.get("territory_label") or data.get("territory")
    )
    accounts, account_by_id, territory_country = _load_account_index(data.get("accounts") or [])
    if not any(a.get("sales_group") is not None or a.get("has_revenue") is not None for a in accounts):
        print(
            "WARNING: accounts file lacks RHSC enrichment (sales_group, has_revenue). "
            "Run scripts/enrich_rhsc_accounts.py first.",
            flush=True,
        )

    if max_accounts is not None:
        accounts = accounts[start : start + max_accounts]
    else:
        accounts = accounts[start:]

    output_dir.mkdir(parents=True, exist_ok=True)
    # Prefer slug/prefix progress; fall back to legacy shared file for resume.
    progress_file = output_dir / f"{prefix}_persona_harvest_progress.json"
    legacy_progress = output_dir / "persona_harvest_progress.json"
    if not progress_file.exists() and legacy_progress.exists():
        progress_file = legacy_progress

    progress = {"done": [], "personas": [], "summaries": [], "errors": [], "rate_limited": []}
    if not fresh and progress_file.exists():
        try:
            progress = json.loads(progress_file.read_text(encoding="utf-8"))
        except Exception:
            pass
    # Always write checkpoints to the prefix-named file going forward.
    progress_file = output_dir / f"{prefix}_persona_harvest_progress.json"

    if retry_unmatched and not fresh:
        n = _requeue_unmatched(progress)
        if n:
            progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")
            print(f"Re-queued {n} no_company_match accounts for name/Sales Group fallbacks.", flush=True)

    done_names = set(progress.get("done") or [])
    all_personas: list[dict] = list(progress.get("personas") or [])
    summaries: list[dict] = list(progress.get("summaries") or [])
    auth = get_auth()
    client = await auth.ensure_client()

    total = len(accounts)
    processed_this_run = 0
    accounts_since_break = 0
    consecutive_rate_limits = 0
    pending = [a for a in accounts if a["name"] not in done_names]
    if pacing.max_per_run:
        pending = pending[: pacing.max_per_run]
        print(
            f"Paced run: up to {len(pending)} accounts "
            f"(delay {pacing.delay}-{pacing.delay + pacing.delay_jitter:.0f}s, "
            f"batch {pacing.batch_size}/{pacing.batch_pause:.0f}s pause)",
            flush=True,
        )

    for idx, acct in enumerate(pending, 1):
        company = acct["name"]
        rhsc_meta = _rhsc_meta_for_account(acct, territory_country)
        done_count = len(progress.get("done") or [])
        print(
            f"[{idx}/{len(pending)}] {company} ({rhsc_meta.get('revenue_segment') or 'unknown'}) "
            f"| territory {done_count}/{total}",
            flush=True,
        )
        status, _ = await _harvest_one_account(
            client,
            auth,
            acct,
            territory_country=territory_country,
            filter_country=filter_country,
            pacing=pacing,
            progress=progress,
            progress_file=progress_file,
            all_personas=all_personas,
            summaries=summaries,
        )
        if status == "session":
            client = await auth.ensure_client()
            continue

        processed_this_run += 1
        accounts_since_break += 1
        if status == "rate_limited":
            consecutive_rate_limits += 1
            if consecutive_rate_limits >= pacing.rate_limit_stop_after:
                print(
                    f"Stopping run after {consecutive_rate_limits} consecutive rate limits "
                    f"(resume later with the same command).",
                    flush=True,
                )
                break
        else:
            consecutive_rate_limits = 0

        done_count = len(progress.get("done") or [])
        if done_count % 25 == 0:
            _write_final_outputs(
                data,
                accounts_path,
                output_dir,
                _dedupe_personas(all_personas),
                _full_summaries(accounts, summaries, territory_country, account_by_id),
                progress,
                accounts,
                territory_country,
                prefix,
            )

        accounts_since_break = await pace_batch_break(pacing, accounts_since_break)
        await pace_between_accounts(pacing)

    retry_queue = list(dict.fromkeys(progress.get("rate_limited") or []))
    if pacing.retry_at_end and retry_queue:
        print(f"Retrying {len(retry_queue)} rate-limited accounts at end...", flush=True)
        progress["rate_limited"] = []
        for company in retry_queue:
            if company in set(progress.get("done") or []):
                continue
            acct = next((a for a in accounts if a["name"] == company), {"name": company, "id": None})
            print(f"[retry] {company}", flush=True)
            status, _ = await _harvest_one_account(
                client,
                auth,
                acct,
                territory_country=territory_country,
                filter_country=filter_country,
                pacing=pacing,
                progress=progress,
                progress_file=progress_file,
                all_personas=all_personas,
                summaries=summaries,
            )
            if status == "session":
                client = await auth.ensure_client()
            await pace_between_accounts(pacing)
    elif retry_queue:
        print(
            f"Deferred {len(retry_queue)} rate-limited accounts to the next paced run.",
            flush=True,
        )

    unique = _dedupe_personas(all_personas)
    full_summaries = _full_summaries(accounts, summaries, territory_country, account_by_id)
    _write_final_outputs(
        data,
        accounts_path,
        output_dir,
        unique,
        full_summaries,
        progress,
        accounts,
        territory_country,
        prefix,
    )


def _dedupe_personas(all_personas: list[dict]) -> list[dict]:
    seen = set()
    unique: list[dict] = []
    for p in all_personas:
        key = (p.get("profile_id"), p.get("account_name"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(p)
    return unique


def _full_summaries(
    accounts: list[dict],
    summaries: list[dict],
    territory_country: str,
    account_by_id: dict[str, dict],
) -> list[dict]:
    summary_by_name = {s["account_name"]: s for s in summaries}
    full_summaries: list[dict] = []
    for acct in accounts:
        name = acct["name"]
        rhsc_meta = _rhsc_meta_for_account(acct, territory_country)
        row = summary_by_name.get(name) or {
            "account_name": name,
            "account_id": acct.get("id"),
            "sales_nav_company": None,
            "sales_nav_org_id": None,
            "company_resolved": False,
            "persona_count": 0,
            "search_status": "not_searched",
            **rhsc_meta,
        }
        if acct.get("id") and acct["id"] in account_by_id:
            for k, v in _rhsc_meta_for_account(account_by_id[acct["id"]], territory_country).items():
                if v is not None:
                    row[k] = v
        full_summaries.append(row)
    return full_summaries


def _build_pacing(args: argparse.Namespace) -> PacingConfig:
    if getattr(args, "fast", False):
        return PacingConfig(
            delay=2.0,
            delay_jitter=1.0,
            request_delay=1.0,
            request_jitter=0.5,
            batch_size=0,
            batch_pause=0.0,
            max_per_run=args.max_per_run,
            rate_limit_stop_after=10,
            retry_at_end=True,
        )
    return PacingConfig(
        delay=args.delay,
        delay_jitter=args.delay_jitter,
        request_delay=args.request_delay,
        request_jitter=args.request_jitter,
        batch_size=args.batch_size,
        batch_pause=args.batch_pause,
        max_per_run=args.max_per_run,
        rate_limit_stop_after=args.rate_limit_stop_after,
        retry_at_end=args.retry_at_end,
    )


def _require_compliance_gate() -> None:
    """Hard-stop harvest unless Cursor Privacy Mode ON + AE affirmation file."""
    import subprocess

    gate = PROJECT_ROOT / "scripts" / "check_compliance_gate.sh"
    if not gate.exists():
        print(f"FAIL compliance: missing {gate}", file=sys.stderr)
        sys.exit(2)
    rc = subprocess.call(["bash", str(gate)])
    if rc != 0:
        sys.exit(rc)


def main():
    parser = argparse.ArgumentParser(
        description="Harvest Cloud/CCSP personas with anti-burst pacing (default)."
    )
    parser.add_argument(
        "--accounts",
        default=str(PROJECT_ROOT / "output/nl_core_territory2_accounts.json"),
    )
    parser.add_argument("--output", default=str(PROJECT_ROOT / "output"))
    parser.add_argument("--prefix", default="nl_core_territory2")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--max", type=int, default=None, help="Slice territory list (offset/limit)")
    parser.add_argument("--fresh", action="store_true", help="Ignore previous progress")
    parser.add_argument(
        "--retry-unmatched",
        action="store_true",
        help="Re-queue accounts previously marked no_company_match and retry with "
        "shortened names + RHSC Sales Group / Global Sales Group",
    )
    parser.add_argument(
        "--country-filter",
        action="store_true",
        help="Restrict leads to territory country (Sales Nav REGION filter + location match)",
    )
    parser.add_argument(
        "--fast",
        action="store_true",
        help="Legacy fast mode (short delays, end-of-run retries; may trigger 429s)",
    )
    parser.add_argument("--delay", type=float, default=6.0, help="Base seconds between accounts")
    parser.add_argument("--delay-jitter", type=float, default=4.0, help="Random extra seconds per account")
    parser.add_argument("--request-delay", type=float, default=2.5, help="Base seconds between API calls")
    parser.add_argument("--request-jitter", type=float, default=1.5, help="Random extra seconds per API call")
    parser.add_argument(
        "--batch-size",
        type=int,
        default=20,
        help="Accounts per batch before a long pause (0 = disable)",
    )
    parser.add_argument(
        "--batch-pause",
        type=float,
        default=600.0,
        help="Seconds to pause after each batch (default 10 min)",
    )
    parser.add_argument(
        "--max-per-run",
        type=int,
        default=40,
        help="Max new accounts per invocation (0 = unlimited)",
    )
    parser.add_argument(
        "--rate-limit-stop-after",
        type=int,
        default=3,
        help="Stop run after N consecutive 429 responses",
    )
    parser.add_argument(
        "--retry-at-end",
        action="store_true",
        help="Retry rate-limited accounts in the same run (can cause burst)",
    )
    args = parser.parse_args()
    _require_compliance_gate()
    pacing = _build_pacing(args)
    if args.max_per_run == 0:
        pacing.max_per_run = None
    asyncio.run(
        run(
            Path(args.accounts),
            Path(args.output),
            start=args.start,
            max_accounts=args.max,
            fresh=args.fresh,
            retry_unmatched=args.retry_unmatched,
            prefix=args.prefix,
            filter_country=args.country_filter,
            pacing=pacing,
        )
    )


if __name__ == "__main__":
    main()
