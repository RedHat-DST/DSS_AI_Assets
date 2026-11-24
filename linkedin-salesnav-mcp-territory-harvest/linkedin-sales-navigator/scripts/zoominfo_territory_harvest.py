#!/usr/bin/env python3
"""Harvest Cloud/CCSP personas via ZoomInfo MCP for RHSC territory accounts."""

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

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROC_HOME = Path.home() / ".cursor/R.O.C."
LAUNCHER = ROC_HOME / "bin/mcp-zoominfo.sh"

CLOUD_KEYWORDS = re.compile(
    r"\b(cloud|ccsp|openshift|kubernetes|k8s|platform\s+eng|devops|sre|"
    r"site reliability|infrastructure|hybrid cloud|cloud ops|cloud operat|"
    r"cloud arch|cloud eng|virtuali[sz]ation|data\s*cent|iaas|paas|saas|"
    r"multi[\s-]?cloud|private cloud|public cloud|container)\b",
    re.I,
)

IT_LEADERSHIP = re.compile(
    r"\b(cio|cto|chief information|chief technology|chief digital|"
    r"director.{0,25}(it|technology|infrastructure|platform|digital|cloud|engineering)|"
    r"head of.{0,25}(it|technology|infrastructure|platform|digital|cloud|engineering)|"
    r"vp.{0,25}(it|technology|infrastructure|platform|digital|cloud|engineering)|"
    r"vice president.{0,25}(it|technology|infrastructure|platform|digital|cloud|engineering))\b",
    re.I,
)

JOB_FUNCTIONS_STRICT = [
    "Cloud / Mobility",
    "Infrastructure",
    "DevOps",
]

JOB_FUNCTIONS_BROAD = JOB_FUNCTIONS_STRICT + [
    "Information Technology",
    "IT Operations",
    "Enterprise Architecture",
    "Technology Operations",
    "Engineering & Technical",
    "Digital Transformation",
    "Information Security",
]

MANAGEMENT_LEVELS = ["Director", "VP Level Exec", "C Level Exec", "Manager"]

NL_HINTS = re.compile(r"\b(netherlands|nederland|amsterdam|rotterdam|utrecht|den haag|eindhoven)\b", re.I)

CONTACT_FIELDS = [
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
    "persona_relevance_score",
    "persona_match_reason",
    "country",
    "city",
    "source",
]


def parse_tool_result(result) -> dict | list | None:
    if result.isError:
        texts = [c.text for c in result.content if hasattr(c, "text")]
        raise RuntimeError("; ".join(texts) or "tool error")
    for block in result.content:
        if hasattr(block, "text") and block.text:
            try:
                return json.loads(block.text)
            except json.JSONDecodeError:
                return {"raw": block.text}
    return None


def normalize_company(name: str) -> str:
    n = re.sub(
        r"\b(n\.?v\.?|b\.?v\.?|c\.?v\.?|holding|participat|international|nederland|netherlands|the)\b",
        "",
        (name or "").lower(),
        flags=re.I,
    )
    return re.sub(r"[^a-z0-9]+", " ", n).strip()


def company_match_score(query: str, candidate: str) -> float:
    q = normalize_company(query)
    c = normalize_company(candidate)
    if not q or not c:
        return 0.0
    if q == c or q in c or c in q:
        return 1.0
    q_tokens = set(q.split())
    c_tokens = set(c.split())
    if not q_tokens or not c_tokens:
        return 0.0
    return len(q_tokens & c_tokens) / max(len(q_tokens), len(c_tokens))


def company_query_variants(account: dict) -> list[str]:
    name = account.get("account_name") or account.get("Name") or ""
    variants: list[str] = []
    for raw in (
        name,
        re.sub(r"\s+(N\.?V\.?|B\.?V\.?|C\.?V\.?)$", "", name, flags=re.I).strip(),
        account.get("sales_group"),
        account.get("global_sales_group"),
    ):
        if raw and raw not in variants:
            variants.append(raw.strip())
    tokens = normalize_company(name).split()
    if len(tokens) >= 2:
        variants.append(" ".join(tokens[:2]).title())
    if tokens:
        variants.append(tokens[0].title())
    # dedupe preserving order
    seen: set[str] = set()
    out: list[str] = []
    for v in variants:
        key = v.lower()
        if key and key not in seen:
            seen.add(key)
            out.append(v)
    return out


def is_cloud_persona(title: str) -> bool:
    return bool(CLOUD_KEYWORDS.search(title or ""))


def is_it_leadership(title: str) -> bool:
    return bool(IT_LEADERSHIP.search(title or ""))


def is_relevant_persona(title: str, strict: bool) -> bool:
    if is_cloud_persona(title) or is_it_leadership(title):
        return True
    if strict:
        return False
    title_l = (title or "").lower()
    return any(
        k in title_l
        for k in (
            "information technology",
            "infrastructure",
            "platform",
            "technology",
            "digital",
            "engineering",
            "architect",
        )
    )


def score_persona(title: str, mgmt: str | None = None, match_reason: str = "") -> tuple[int, str]:
    reasons: list[str] = []
    score = 0
    if is_cloud_persona(title):
        score += 50
        reasons.append("cloud_keyword")
    if is_it_leadership(title):
        score += 40
        reasons.append("it_leadership")
    title_l = (title or "").lower()
    if any(k in title_l for k in ("architect", "head of", "vp ", "vice president", "director")):
        score += 15
        reasons.append("senior_role")
    if mgmt in {"C Level Exec", "VP Level Exec", "Director"}:
        score += 10
        reasons.append("mgmt_level")
    if match_reason:
        reasons.append(match_reason)
    return score, "+".join(dict.fromkeys(reasons)) or "broad_it"


def nl_contact_hint(attrs: dict, company_attrs: dict) -> bool:
    blob = " ".join(
        str(attrs.get(k) or "")
        for k in ("city", "state", "country", "metroRegion", "location")
    )
    blob += " " + str((company_attrs or {}).get("country") or "")
    return bool(NL_HINTS.search(blob)) or (company_attrs or {}).get("country", "").lower() == "netherlands"


async def call_tool(session: ClientSession, name: str, args: dict, retries: int = 3):
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            return parse_tool_result(await session.call_tool(name, args))
        except Exception as e:
            last_err = e
            if attempt + 1 < retries:
                await asyncio.sleep(1.5 * (attempt + 1))
    raise last_err or RuntimeError("tool call failed")


async def search_company(session: ClientSession, account: dict) -> dict | None:
    name = account.get("account_name") or ""
    best: tuple[float, dict] | None = None
    for query in company_query_variants(account):
        for with_country in (True, False):
            args = {"companyName": query, "pageSize": 15}
            if with_country:
                args["country"] = "Netherlands"
            payload = await call_tool(session, "search_companies", args)
            for row in (payload or {}).get("data") or []:
                attrs = row.get("attributes") or {}
                cname = attrs.get("name") or ""
                score = company_match_score(name, cname)
                if query.lower() in cname.lower() or cname.lower() in query.lower():
                    score += 0.15
                if (attrs.get("country") or "").lower() == "netherlands":
                    score += 0.1
                if account.get("sales_group") and company_match_score(account["sales_group"], cname) >= 0.5:
                    score += 0.2
                if best is None or score > best[0]:
                    best = (score, row)
        if best and best[0] >= 0.55:
            break
    if best and best[0] >= 0.35:
        return best[1]
    return None


def contact_row(
    row: dict,
    company_row: dict,
    account_name: str,
    match_reason: str,
) -> dict:
    cattrs = row.get("attributes") or {}
    company_attrs = company_row.get("attributes") or {}
    company_id = int(company_row["id"])
    company_name = (cattrs.get("company") or {}).get("name") or company_attrs.get("name") or account_name
    title = cattrs.get("jobTitle") or ""
    score, reason = score_persona(title, cattrs.get("managementLevel"), match_reason)
    return {
        "zoominfo_person_id": str(row.get("id")),
        "zoominfo_company_id": str(company_id),
        "contact_first_name": cattrs.get("firstName"),
        "contact_last_name": cattrs.get("lastName"),
        "contact_full_name": " ".join(x for x in (cattrs.get("firstName"), cattrs.get("lastName")) if x),
        "job_title": title,
        "management_level": cattrs.get("managementLevel"),
        "company_name": company_name,
        "country": cattrs.get("country") or company_attrs.get("country"),
        "city": cattrs.get("city"),
        "email": None,
        "email_status": "pending_enrich",
        "phone": None,
        "linkedin_url": None,
        "persona_relevance_score": score,
        "persona_match_reason": reason,
        "source": "zoominfo",
    }


async def search_contacts_pass(
    session: ClientSession,
    company_row: dict,
    *,
    job_functions: list[str],
    strict_titles: bool,
    page_size: int,
) -> list[dict]:
    company_id = int(company_row["id"])
    payload = await call_tool(
        session,
        "search_contacts",
        {
            "companyIdList": [company_id],
            "jobFunctionList": job_functions,
            "managementLevelList": MANAGEMENT_LEVELS,
            "pageSize": page_size,
            "userIntent": "Territory harvest NL_COMM_TERR_CORE_POD01_TERR02 cloud/CCSP personas v2",
        },
    )
    company_attrs = company_row.get("attributes") or {}
    account_name = company_attrs.get("name") or ""
    out: list[dict] = []
    for row in (payload or {}).get("data") or []:
        title = (row.get("attributes") or {}).get("jobTitle") or ""
        if not is_relevant_persona(title, strict=strict_titles):
            continue
        out.append(
            contact_row(
                row,
                company_row,
                account_name,
                "strict_cloud" if strict_titles else "broad_it",
            )
        )
    return out


async def search_contacts_for_company(
    session: ClientSession,
    company_row: dict,
    account_name: str,
    max_per_account: int,
) -> list[dict]:
    seen: set[str] = set()
    merged: list[dict] = []

    for strict, jobs, size in (
        (True, JOB_FUNCTIONS_STRICT, min(25, max_per_account * 4)),
        (False, JOB_FUNCTIONS_BROAD, min(25, max_per_account * 5)),
    ):
        batch = await search_contacts_pass(
            session, company_row, job_functions=jobs, strict_titles=strict, page_size=size
        )
        for c in batch:
            pid = c["zoominfo_person_id"]
            if pid in seen:
                continue
            seen.add(pid)
            merged.append(c)
        if len(merged) >= max_per_account:
            break

    company_attrs = company_row.get("attributes") or {}
    # Prefer NL-located contacts when we have enough; otherwise keep global leadership.
    nl = [c for c in merged if nl_contact_hint({"city": c.get("city"), "country": c.get("country")}, company_attrs)]
    if len(nl) >= max(2, max_per_account // 2):
        merged = nl + [c for c in merged if c not in nl]

    merged.sort(key=lambda x: x["persona_relevance_score"], reverse=True)
    return merged[:max_per_account]


async def enrich_batch(session: ClientSession, contacts: list[dict]) -> None:
    batch = [{"personId": c["zoominfo_person_id"]} for c in contacts if c.get("zoominfo_person_id")]
    if not batch:
        return
    payload = await call_tool(
        session,
        "enrich_contacts",
        {
            "contacts": batch[:10],
            "requiredFields": ["email", "phone", "jobTitle", "externalUrls"],
        },
    )
    enriched = {}
    for item in (payload or {}).get("data") or []:
        pid = str(item.get("id") or (item.get("attributes") or {}).get("personId") or "")
        enriched[pid] = item.get("attributes") or item
    for c in contacts:
        attrs = enriched.get(c["zoominfo_person_id"]) or {}
        email = attrs.get("email")
        c["email"] = email
        c["email_status"] = "verified" if email else "missing"
        c["phone"] = attrs.get("phone") or attrs.get("directPhone")
        urls = attrs.get("externalUrls") or attrs.get("externalURL")
        if isinstance(urls, list) and urls:
            c["linkedin_url"] = urls[0]
        else:
            c["linkedin_url"] = attrs.get("linkedInUrl") or urls
        if attrs.get("jobTitle"):
            c["job_title"] = attrs.get("jobTitle")


def write_csv(path: Path, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CONTACT_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


async def run(
    accounts_path: Path,
    output_dir: Path,
    *,
    max_accounts: int | None = None,
    batch_size: int | None = None,
    max_per_account: int = 5,
    delay: float = 0.5,
    enrich: bool = True,
    fresh: bool = False,
    progress_name: str = "zoominfo_harvest_progress_v2.json",
) -> None:
    data = json.loads(accounts_path.read_text(encoding="utf-8"))
    accounts = data.get("accounts") or []
    if max_accounts:
        accounts = accounts[:max_accounts]

    output_dir.mkdir(parents=True, exist_ok=True)
    progress_file = output_dir / progress_name
    contacts_json = output_dir / "nl_comm_terr_core_pod01_terr02_cloud_ccsp_contacts.json"
    contacts_csv = output_dir / "nl_comm_terr_core_pod01_terr02_cloud_ccsp_contacts.csv"
    no_persona_csv = output_dir / "accounts_with_no_cloud_personas.csv"

    progress = {"done": [], "contacts": [], "errors": [], "no_personas": [], "version": 2}
    if not fresh and progress_file.exists():
        progress = json.loads(progress_file.read_text(encoding="utf-8"))

    done = set(progress.get("done") or [])
    all_contacts: list[dict] = list(progress.get("contacts") or [])

    server_params = StdioServerParameters(
        command=str(LAUNCHER),
        env={"ROC_HOME": str(ROC_HOME), "ZOOMINFO_MCP_PORT": "46819"},
    )

    async def with_session(fn):
        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                return await fn(session)

    total = len(accounts)
    processed_this_run = 0
    for idx, acct in enumerate(accounts, 1):
        name = acct.get("account_name") or acct.get("Name")
        if not name or name in done:
            continue
        if batch_size is not None and processed_this_run >= batch_size:
            print(f"Batch limit reached ({batch_size}), exiting for reconnect.", flush=True)
            break
        print(f"[{idx}/{total}] {name}", flush=True)
        try:

            async def process_account(session: ClientSession):
                company_row = await search_company(session, acct)
                if not company_row:
                    return None
                personas = await search_contacts_for_company(
                    session, company_row, name, max_per_account
                )
                for p in personas:
                    p["account_id"] = acct.get("account_id")
                    p["account_name"] = name
                    p["account_owner"] = acct.get("owner_alias")
                if personas and enrich:
                    for i in range(0, len(personas), 10):
                        try:
                            await enrich_batch(session, personas[i : i + 10])
                        except Exception as enrich_err:
                            print(f"  -> enrich warning: {enrich_err}", flush=True)
                return personas

            personas = await with_session(process_account)
            if personas is None:
                progress["no_personas"].append(
                    {"account_name": name, "account_id": acct.get("account_id"), "reason": "company_not_found"}
                )
                progress["done"].append(name)
                progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")
                processed_this_run += 1
                print("  -> company not found", flush=True)
                await asyncio.sleep(delay)
                continue
            if not personas:
                progress["no_personas"].append(
                    {"account_name": name, "account_id": acct.get("account_id"), "reason": "no_cloud_personas"}
                )
            all_contacts.extend(personas)
            progress["done"].append(name)
            progress["contacts"] = all_contacts
            progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")
            processed_this_run += 1
            print(f"  -> {len(personas)} personas", flush=True)
        except Exception as e:
            progress.setdefault("errors", []).append({"account": name, "error": str(e)})
            progress_file.write_text(json.dumps(progress, indent=2), encoding="utf-8")
            print(f"  -> error: {e}", flush=True)
        await asyncio.sleep(delay)

    seen: set[tuple[str, str]] = set()
    unique: list[dict] = []
    for c in all_contacts:
        key = (c.get("zoominfo_person_id") or "", c.get("account_name") or "")
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)
    unique.sort(key=lambda x: (x.get("account_name") or "", -(x.get("persona_relevance_score") or 0)))

    payload = {
        "territory": data.get("territory") or "NL_COMM_TERR_CORE_POD01_TERR02",
        "version": 2,
        "accounts_processed": len(progress.get("done") or []),
        "accounts_with_personas": len({c["account_name"] for c in unique}),
        "contact_count": len(unique),
        "contacts": unique,
    }
    contacts_json.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    write_csv(contacts_csv, unique)
    if progress.get("no_personas"):
        with no_persona_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=["account_name", "account_id", "reason"])
            writer.writeheader()
            writer.writerows(progress["no_personas"])

    print(
        f"Done. {len(unique)} contacts across {payload['accounts_with_personas']} accounts -> {contacts_csv}",
        flush=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--accounts",
        default=str(PROJECT_ROOT / "output/nl_comm_terr_core_pod01_terr02_accounts.json"),
    )
    parser.add_argument("--output", default=str(PROJECT_ROOT / "output"))
    parser.add_argument("--max", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None, help="Max accounts per invocation (for MCP reconnect)")
    parser.add_argument("--max-per-account", type=int, default=5)
    parser.add_argument("--delay", type=float, default=0.5)
    parser.add_argument("--no-enrich", action="store_true")
    parser.add_argument("--fresh", action="store_true")
    parser.add_argument("--progress-name", default="zoominfo_harvest_progress_v2.json")
    args = parser.parse_args()
    asyncio.run(
        run(
            Path(args.accounts),
            Path(args.output),
            max_accounts=args.max,
            batch_size=args.batch_size,
            max_per_account=args.max_per_account,
            delay=args.delay,
            enrich=not args.no_enrich,
            fresh=args.fresh,
            progress_name=args.progress_name,
        )
    )


if __name__ == "__main__":
    main()
