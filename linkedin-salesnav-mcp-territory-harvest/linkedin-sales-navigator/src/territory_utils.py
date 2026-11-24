"""Territory parsing, RHSC revenue classification, and country matching."""

from __future__ import annotations

import re
from typing import Any

# LinkedIn Sales Navigator geo id for Netherlands (REGION filter).
NETHERLANDS_REGION_ID = "urn:li:geo:102890719"

TERRITORY_REGIONS: dict[str, dict[str, Any]] = {
    "Netherlands": {
        "region_id": NETHERLANDS_REGION_ID,
        "aliases": ("netherlands", "nederland", "holland", "the randstad", ", nl"),
        "country_codes": ("nl",),
    },
}


def parse_territory_country(territory: str | None) -> str:
    """Derive the country filter from a territory name (e.g. Netherlands Core Territory 2)."""
    text = (territory or "").strip()
    lower = text.lower()
    if "netherlands" in lower or lower.startswith("nl_") or " nl " in f" {lower} ":
        return "Netherlands"
    match = re.match(r"^([A-Za-z]+)", text)
    if match and match.group(1) in TERRITORY_REGIONS:
        return match.group(1)
    return "Netherlands"


def classify_revenue(global_arr_usd: Any) -> tuple[bool, str]:
    """Return (has_revenue, revenue_segment) from RHSC Global_ARR_USD__c."""
    try:
        arr = float(global_arr_usd or 0)
    except (TypeError, ValueError):
        arr = 0.0
    has_revenue = arr > 0
    segment = "with_revenue" if has_revenue else "no_revenue"
    return has_revenue, segment


# Senior buyers / budget owners — C-level, VP, Director, Head of, owners.
_DECISION_MAKER_TITLE = re.compile(
    r"(?:"
    r"\b(?:ceo|cio|cto|ciso|cfo|coo|cro|cdo|cpo|cao)\b|"
    r"\bchief\s+[\w/&-]+|"
    r"\b(?:executive\s+)?vice[\s-]?president\b|\b(?:e?vp|avp|svp)\b|"
    r"\b(?:senior\s+|sr\.?\s+|group\s+|executive\s+)?director\b|"
    r"\bmanaging\s+director\b|"
    r"\bhead\s+of\b|"
    r"\bgeneral\s+manager\b|\bgm\b|"
    r"\b(?:co-?)?founder\b|\bowner\b|"
    r"\bboard\s+member\b|\bpresident\b"
    r")",
    re.I,
)

# Explicit IC / mid-level signals used only for role_reason tagging.
_INFLUENCER_TITLE = re.compile(
    r"(?:"
    r"\b(?:senior\s+|sr\.?\s+|principal\s+|staff\s+|lead\s+)?(?:architect|engineer|developer|consultant|specialist|analyst)\b|"
    r"\b(?:project|program|product|engineering|platform|devops|sre|cloud)\s+manager\b|"
    r"\bmanager\b|"
    r"\b(?:team\s+)?lead\b|\btech(?:nical)?\s+lead\b|"
    r"\bengineer(?:ing)?\b"
    r")",
    re.I,
)


def classify_persona_role(
    title: str | None,
    management_level: str | None = None,
) -> tuple[str, str]:
    """Classify a job title as decision_maker or influencer.

    Returns (role, reason) where role is ``decision_maker`` or ``influencer``.
    Decision makers: C-suite, VP/AVP, Director, Head of, GM, founder/owner.
    Everyone else in the harvest (managers, architects, engineers, leads) is influencer.
    Optional ZoomInfo ``management_level`` can promote to decision_maker.
    """
    mgmt = (management_level or "").strip().lower()
    if mgmt in {"c level exec", "c-level", "vp level exec", "director"}:
        return "decision_maker", f"mgmt:{mgmt}"
    text = (title or "").strip()
    if not text:
        return "influencer", "missing_title"
    if _DECISION_MAKER_TITLE.search(text):
        return "decision_maker", "senior_title"
    if _INFLUENCER_TITLE.search(text):
        return "influencer", "ic_or_manager_title"
    return "influencer", "default_influencer"


_LEGAL_SUFFIX_TAIL = re.compile(
    r"\s+(N\.?V\.?|B\.?V\.?|C\.?V\.?|GmbH|AG|S\.?A\.?|Ltd\.?|LLC|Inc\.?|Corp\.?|"
    r"Holding|International|Nederland|Netherlands|Belgium|Belgi[eë]|"
    r"Deutschland|Germany|France)\s*$",
    re.I,
)
_NORMALIZE_NOISE = re.compile(
    r"\b(n\.?v\.?|b\.?v\.?|c\.?v\.?|gmbh|ag|sa|sas|ltd|llc|inc|corp|holding|"
    r"participat|international|nederland|netherlands|belgium|belgie|deutschland|"
    r"germany|france|the)\b",
    re.I,
)


def _strip_legal_suffix(name: str) -> str:
    return _LEGAL_SUFFIX_TAIL.sub("", (name or "").strip()).strip(" ,.-")


def _normalized_tokens(name: str) -> list[str]:
    text = _NORMALIZE_NOISE.sub(" ", (name or "").lower())
    return [t for t in re.sub(r"[^a-z0-9]+", " ", text).split() if t]


def company_query_variants(account: dict[str, Any] | str) -> list[str]:
    """Ordered company-name queries: full legal name, short name, Sales Group, Global Sales Group.

    Used when the primary RHSC account name does not resolve in Sales Nav / ZoomInfo.
    """
    if isinstance(account, str):
        name = account
        sales_group = None
        global_sales_group = None
    else:
        name = (
            account.get("account_name")
            or account.get("Name")
            or account.get("name")
            or ""
        )
        sales_group = account.get("sales_group")
        global_sales_group = account.get("global_sales_group")

    variants: list[str] = []

    def add(raw: Any) -> None:
        text = str(raw or "").strip()
        if not text:
            return
        if text not in variants:
            variants.append(text)

    add(name)
    stripped = _strip_legal_suffix(name)
    add(stripped)
    add(sales_group)
    add(_strip_legal_suffix(str(sales_group or "")))
    add(global_sales_group)
    add(_strip_legal_suffix(str(global_sales_group or "")))

    tokens = _normalized_tokens(name)
    if len(tokens) >= 3:
        add(" ".join(tokens[:3]).title())
    if len(tokens) >= 2:
        add(" ".join(tokens[:2]).title())
    if tokens:
        add(tokens[0].title())

    sg_tokens = _normalized_tokens(str(sales_group or ""))
    if len(sg_tokens) >= 2:
        add(" ".join(sg_tokens[:2]).title())
    if sg_tokens and sg_tokens[0] not in tokens[:1]:
        add(sg_tokens[0].title())

    # Drop ultra-short / numeric-only noise
    out: list[str] = []
    seen: set[str] = set()
    for v in variants:
        key = re.sub(r"\s+", " ", v.lower()).strip()
        if len(key) < 2 or key.isdigit() or key in seen:
            continue
        seen.add(key)
        out.append(v)
    return out


def rhsc_fields_from_record(rec: dict[str, Any]) -> dict[str, Any]:
    """Extract Sales Group / Global Sales Group and revenue fields from an RHSC Account."""
    has_revenue, segment = classify_revenue(rec.get("Global_ARR_USD__c"))
    return {
        "sales_group": rec.get("DU_Proxy__c"),
        "sales_group_id": rec.get("DU_Proxy_ID__c"),
        "global_sales_group": rec.get("GU_Proxy__c"),
        "global_sales_group_id": rec.get("GU_Proxy_ID__c"),
        "global_arr_usd": rec.get("Global_ARR_USD__c"),
        "billing_country": rec.get("BillingCountry"),
        "billing_country_code": rec.get("BillingCountryCode"),
        "account_type": rec.get("Type"),
        "has_revenue": has_revenue,
        "revenue_segment": segment,
    }


def lead_matches_territory_country(location: str | None, country: str) -> bool:
    """True when a Sales Nav lead location is in the territory country."""
    loc = (location or "").strip().lower()
    if not loc:
        return False
    cfg = TERRITORY_REGIONS.get(country)
    if not cfg:
        return country.lower() in loc
    if any(alias in loc for alias in cfg["aliases"]):
        return True
    if loc in ("nl", "netherlands", "nederland"):
        return True
    return False


def region_filter_for_country(country: str) -> tuple[str, str] | None:
    """Return (region_name, region_id) for LinkedIn REGION filter, if known."""
    cfg = TERRITORY_REGIONS.get(country)
    if not cfg:
        return None
    return country, cfg["region_id"]
