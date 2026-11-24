"""LinkedIn Voyager and Sales Navigator API client."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote, unquote, urlparse, parse_qs

import httpx

from .chrome import cookie_header, csrf_from_cookies

LEAD_SEARCH_DECORATION = "com.linkedin.sales.deco.desktop.searchv2.LeadSearchResult-14"
ACCOUNT_SEARCH_DECORATION = "com.linkedin.sales.deco.desktop.searchv2.AccountSearchResult-7"
PROFILE_DECORATION = "com.linkedin.sales.deco.desktop.profile.WebTopCard-11"
COMPANY_DECORATION = "com.linkedin.sales.deco.desktop.company.CompanyTopCard-8"

SALES_API_BASE = "https://www.linkedin.com/sales-api"
VOYAGER_API_BASE = "https://www.linkedin.com/voyager/api"


class SessionExpired(RuntimeError):
    """LinkedIn rejected the session — user must log in again."""


class RateLimited(RuntimeError):
    """LinkedIn rate-limited the request."""


def _is_auth_error(status: int) -> bool:
    return status in {401, 403, 999}


def _normalize_whitespace(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _lead_search_query(keywords: str) -> str:
    encoded = quote(keywords, safe="")
    return f"(spellCorrectionEnabled:true,recentSearchParam:(doLogHistory:true),keywords:{encoded})"


def _account_search_query(keywords: str) -> str:
    encoded = quote(keywords, safe="")
    return f"(spellCorrectionEnabled:true,recentSearchParam:(doLogHistory:true),keywords:{encoded})"


def _extract_profile_id(value: str) -> str | None:
    """Extract a Sales Navigator profile id from a URL or urn."""
    if not value:
        return None
    text = value.strip()
    if text.startswith("urn:li:fs_salesProfile:"):
        return text.split(":")[-1]
    if text.startswith("urn:li:fsd_profile:"):
        return text.split(":")[-1]
    m = re.search(r"/sales/lead/([^,/]+)", text)
    if m:
        return m.group(1)
    m = re.search(r"/in/([^/?#]+)", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"[A-Za-z0-9_-]+", text):
        return text
    return None


def _extract_company_id(value: str) -> str | None:
    if not value:
        return None
    text = value.strip()
    if text.startswith("urn:li:fs_salesCompany:"):
        return text.split(":")[-1]
    m = re.search(r"/sales/company/(\d+)", text)
    if m:
        return m.group(1)
    m = re.search(r"/company/(\d+)", text)
    if m:
        return m.group(1)
    if re.fullmatch(r"\d+", text):
        return text
    return None


def _is_person_record(raw: dict[str, Any]) -> bool:
    if raw.get("firstName") or raw.get("fullName"):
        return True
    type_name = str(raw.get("$type") or raw.get("type") or "")
    return "PeopleSearchHit" in type_name or "sales.profile" in type_name


def _extract_people(payload: Any) -> list[dict[str, Any]]:
    """Sales Nav lead search returns people in `included`, not top-level elements."""
    if not isinstance(payload, dict):
        return []
    people: list[dict[str, Any]] = []
    included = payload.get("included")
    if isinstance(included, list):
        people.extend([e for e in included if isinstance(e, dict) and _is_person_record(e)])
    if people:
        return people
    for e in _unwrap_elements(payload):
        if _is_person_record(e):
            people.append(e)
    return people


def _unwrap_elements(payload: Any) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    elements = payload.get("elements")
    if isinstance(elements, list):
        return [e for e in elements if isinstance(e, dict)]
    data = payload.get("data")
    if isinstance(data, dict):
        inner = data.get("elements")
        if isinstance(inner, list):
            return [e for e in inner if isinstance(e, dict)]
    included = payload.get("included")
    if isinstance(included, list):
        return [e for e in included if isinstance(e, dict)]
    return []


def _normalize_company_name(name: str) -> str:
    text = _normalize_whitespace(name).lower()
    for suffix in (" b.v.", " n.v.", " b.v", " n.v", " holding", " group", " international"):
        if text.endswith(suffix):
            text = text[: -len(suffix)].strip()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def _company_match_score(target: str, candidate: str) -> float:
    t = _normalize_company_name(target)
    c = _normalize_company_name(candidate)
    if not t or not c:
        return 0.0
    if t == c:
        return 1.0
    t_tokens = set(t.split())
    c_tokens = set(c.split())
    if not t_tokens or not c_tokens:
        return 0.0
    inter = len(t_tokens & c_tokens)
    if inter == 0:
        return 0.0
    recall = inter / len(t_tokens)
    precision = inter / len(c_tokens)
    return (2 * precision * recall) / (precision + recall)


def _region_filter_token(region_id: str, region_name: str) -> str:
    rid = quote(region_id, safe="")
    rtext = quote(region_name, safe="")
    return (
        f"(type:REGION,values:List(("
        f"id:{rid},text:{rtext},selectionType:INCLUDED,parent:(id:0)"
        ")))"
    )


def _company_filter_query(
    org_id: str,
    display_name: str,
    *,
    keywords: str = "",
    region_name: str | None = None,
    region_id: str | None = None,
) -> str:
    org_num = org_id.split(":")[-1] if ":" in org_id else org_id
    org_token = f"urn%3Ali%3Aorganization%3A{org_num}"
    text = quote(display_name, safe="")
    company_filter = (
        "(type:CURRENT_COMPANY,values:List(("
        f"id:{org_token},text:{text},selectionType:INCLUDED,parent:(id:0)"
        ")))"
    )
    filters = [company_filter]
    if region_name and region_id:
        filters.append(_region_filter_token(region_id, region_name))
    filters_str = ",".join(filters)
    inner = f"(recentSearchParam:(doLogHistory:true),filters:List({filters_str}))"
    if keywords:
        return inner[:-1] + f",keywords:{quote(keywords, safe='')})"
    return inner


def _company_suggestions(payload: Any) -> list[dict[str, str]]:
    if not isinstance(payload, dict):
        return []
    metadata = (payload.get("data") or {}).get("metadata") or {}
    out: list[dict[str, str]] = []
    for filt in metadata.get("filters") or []:
        single = filt.get("singleFilterMetadata") or {}
        if single.get("type") != "CURRENT_COMPANY":
            continue
        for value in single.get("values") or []:
            display = _pick(value, "displayValue")
            org_id = _pick(value, "id")
            if display and org_id:
                out.append({"display_name": str(display), "org_id": str(org_id)})
    return out


def _pick(d: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in d and d[key] is not None:
            return d[key]
    return default


def _format_lead(raw: dict[str, Any]) -> dict[str, Any]:
    first = _pick(raw, "firstName")
    last = _pick(raw, "lastName")
    full_name = _pick(raw, "fullName")
    if not full_name and (first or last):
        full_name = f"{first or ''} {last or ''}".strip()

    current_positions = raw.get("currentPositions") or []
    position = current_positions[0] if current_positions else {}
    if isinstance(position, dict):
        title = _pick(position, "title")
        company = _pick(position, "companyName") or _pick(position, "company", "name")
    else:
        title = _pick(raw, "title", "headline")
        company = None

    entity_urn = _pick(raw, "entityUrn", "objectUrn")
    profile_id = None
    if entity_urn:
        profile_id = str(entity_urn).split(":")[-1]

    return {
        "name": full_name or _pick(raw, "name"),
        "first_name": first,
        "last_name": last,
        "title": title or _pick(raw, "headline", "occupation"),
        "company": company,
        "location": _pick(raw, "location", "geoRegion"),
        "profile_id": profile_id,
        "entity_urn": entity_urn,
        "sales_navigator_url": f"https://www.linkedin.com/sales/lead/{profile_id}" if profile_id else None,
        "linkedin_url": _pick(raw, "flagshipProfileUrl", "publicIdentifier") and (
            f"https://www.linkedin.com/in/{_pick(raw, 'publicIdentifier')}"
            if _pick(raw, "publicIdentifier")
            else None
        ),
        "connection_degree": _pick(raw, "degree"),
        "summary": _pick(raw, "summary"),
        "raw_keys": sorted(raw.keys()),
    }


def _format_company(raw: dict[str, Any]) -> dict[str, Any]:
    entity_urn = _pick(raw, "entityUrn", "objectUrn")
    company_id = None
    if entity_urn:
        company_id = str(entity_urn).split(":")[-1]

    return {
        "name": _pick(raw, "name", "companyName"),
        "company_id": company_id,
        "entity_urn": entity_urn,
        "industry": _pick(raw, "industry"),
        "employee_count": _pick(raw, "employeeCount", "employeeCountRange"),
        "headquarters": _pick(raw, "headquarters", "location"),
        "website": _pick(raw, "website"),
        "description": _pick(raw, "description"),
        "sales_navigator_url": f"https://www.linkedin.com/sales/company/{company_id}" if company_id else None,
        "linkedin_url": _pick(raw, "flagshipCompanyUrl"),
        "raw_keys": sorted(raw.keys()),
    }


class LinkedInClient:
    def __init__(self, cookies: dict[str, str], csrf_token: str):
        self.cookies = cookies
        self.csrf_token = csrf_token
        self._client = httpx.AsyncClient(timeout=60.0, follow_redirects=True)

    @property
    def headers(self) -> dict[str, str]:
        csrf = csrf_from_cookies(self.cookies) or self.csrf_token
        return {
            "csrf-token": csrf,
            "x-restli-protocol-version": "2.0.0",
            "x-li-lang": "en_US",
            "x-li-page-instance": "urn:li:page:d_sales2_search_people;cursorMcpHarvest==",
            "x-li-track": (
                '{"clientVersion":"2.0.8893","mpVersion":"2.0.8893","osName":"web",'
                '"timezoneOffset":2,"timezone":"Europe/Amsterdam","deviceFormFactor":"DESKTOP",'
                '"mpName":"lighthouse-web","displayDensity":2,"displayWidth":1920,"displayHeight":1080}'
            ),
            "accept": "application/vnd.linkedin.normalized+json+2.1",
            "accept-language": "en-US,en;q=0.9",
            "user-agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
            ),
            "cookie": cookie_header(self.cookies),
            "referer": "https://www.linkedin.com/sales/search/people",
        }

    async def request(self, method: str, url: str, **kwargs) -> Any:
        headers = dict(self.headers)
        headers.update(kwargs.pop("headers", {}) or {})
        r = await self._client.request(method, url, headers=headers, **kwargs)
        if _is_auth_error(r.status_code):
            raise SessionExpired(f"LinkedIn session expired (HTTP {r.status_code})")
        if r.status_code == 429:
            raise RateLimited("LinkedIn rate limit hit. Wait a few minutes and retry.")
        try:
            body = r.json()
        except Exception:
            body = r.text
        if r.status_code >= 400:
            raise RuntimeError(f"LinkedIn API error {r.status_code}: {str(body)[:500]}")
        return body

    async def close(self) -> None:
        await self._client.aclose()

    async def probe_identity(self) -> dict[str, Any]:
        """Validate session and return the current user."""
        url = f"{VOYAGER_API_BASE}/me"
        body = await self.request("GET", url)
        mini = (body or {}).get("miniProfile") or {}
        if not mini and isinstance(body, dict):
            mini = body
        first = _pick(mini, "firstName")
        last = _pick(mini, "lastName")
        public_id = _pick(mini, "publicIdentifier")
        return {
            "name": f"{first or ''} {last or ''}".strip() or None,
            "first_name": first,
            "last_name": last,
            "public_id": public_id,
            "profile_url": f"https://www.linkedin.com/in/{public_id}" if public_id else None,
            "entity_urn": _pick(mini, "entityUrn", "objectUrn"),
            "headline": _pick(mini, "occupation", "headline"),
        }

    async def search_leads(
        self,
        keywords: str,
        *,
        start: int = 0,
        count: int = 25,
    ) -> dict[str, Any]:
        query = _lead_search_query(keywords)
        url = (
            f"{SALES_API_BASE}/salesApiLeadSearch"
            f"?q=searchQuery&query={query}"
            f"&start={start}&count={count}"
            f"&decorationId={LEAD_SEARCH_DECORATION}"
        )
        body = await self.request("GET", url)
        leads = [_format_lead(e) for e in _extract_people(body)]
        paging = ((body or {}).get("data") or {}).get("paging") or (body or {}).get("paging") or {}
        return {
            "keywords": keywords,
            "start": start,
            "count": count,
            "total": paging.get("total"),
            "leads": leads,
            "company_suggestions": _company_suggestions(body),
        }

    async def resolve_company(
        self,
        company_name: str,
        *,
        score_against: str | None = None,
        min_score: float = 0.5,
        country_hint: str | None = "Netherlands",
    ) -> dict[str, Any] | None:
        """Resolve a Sales Navigator organization id from a company name."""
        target = score_against or company_name
        queries = [company_name]
        if country_hint:
            queries.append(f"{company_name} {country_hint}")
        best: dict[str, Any] | None = None
        best_score = 0.0
        for query in queries:
            result = await self.search_leads(query, count=1)
            suggestions = result.get("company_suggestions") or []
            for suggestion in suggestions:
                display = suggestion.get("display_name", "")
                score = max(
                    _company_match_score(target, display),
                    _company_match_score(company_name, display),
                )
                if score > best_score:
                    best_score = score
                    best = {**suggestion, "match_score": score, "query_used": query}
            if best_score >= 0.85:
                break
        if not best or best_score < min_score:
            return None
        return best

    async def resolve_company_variants(
        self,
        account: dict[str, Any] | str,
        *,
        min_score: float = 0.45,
        country_hint: str | None = "Netherlands",
    ) -> dict[str, Any] | None:
        """Try full name, shortened name, Sales Group, then Global Sales Group."""
        from src.territory_utils import company_query_variants

        if isinstance(account, str):
            primary = account
            variants = company_query_variants(account)
        else:
            primary = (
                account.get("account_name")
                or account.get("Name")
                or account.get("name")
                or ""
            )
            variants = company_query_variants(account)

        best: dict[str, Any] | None = None
        for variant in variants:
            resolved = await self.resolve_company(
                variant,
                score_against=primary or variant,
                min_score=min_score,
                country_hint=country_hint,
            )
            if not resolved:
                continue
            score = float(resolved.get("match_score") or 0)
            if best is None or score > float(best.get("match_score") or 0):
                best = {
                    **resolved,
                    "query_variant": variant,
                }
            if score >= 0.85:
                break
        return best

    async def search_leads_at_company(
        self,
        company_name: str,
        *,
        org_id: str | None = None,
        display_name: str | None = None,
        keywords: str = "",
        region_name: str | None = None,
        region_id: str | None = None,
        start: int = 0,
        count: int = 25,
        account: dict[str, Any] | None = None,
        min_resolve_score: float = 0.45,
    ) -> dict[str, Any]:
        resolved = None
        if not org_id or not display_name:
            if account is not None:
                resolved = await self.resolve_company_variants(
                    account,
                    min_score=min_resolve_score,
                )
            else:
                resolved = await self.resolve_company(
                    company_name,
                    min_score=min_resolve_score,
                )
            if not resolved:
                return {
                    "company_name": company_name,
                    "resolved": False,
                    "leads": [],
                    "total": 0,
                }
            org_id = resolved["org_id"]
            display_name = resolved["display_name"]
        query = _company_filter_query(
            org_id,
            display_name,
            keywords=keywords,
            region_name=region_name,
            region_id=region_id,
        )
        url = (
            f"{SALES_API_BASE}/salesApiLeadSearch"
            f"?q=searchQuery&query={query}"
            f"&start={start}&count={count}"
            f"&decorationId={LEAD_SEARCH_DECORATION}"
        )
        body = await self.request("GET", url)
        leads = [_format_lead(e) for e in _extract_people(body)]
        paging = ((body or {}).get("data") or {}).get("paging") or (body or {}).get("paging") or {}
        return {
            "company_name": company_name,
            "resolved": True,
            "org_id": org_id,
            "display_name": display_name,
            "query_variant": (resolved or {}).get("query_variant") if resolved else None,
            "match_score": (resolved or {}).get("match_score") if resolved else None,
            "keywords": keywords,
            "region_name": region_name,
            "region_id": region_id,
            "start": start,
            "count": count,
            "total": paging.get("total"),
            "leads": leads,
        }

    async def search_companies(
        self,
        keywords: str,
        *,
        start: int = 0,
        count: int = 25,
    ) -> dict[str, Any]:
        query = _account_search_query(keywords)
        url = (
            f"{SALES_API_BASE}/salesApiAccountSearch"
            f"?q=searchQuery&query={query}"
            f"&start={start}&count={count}"
            f"&decorationId={ACCOUNT_SEARCH_DECORATION}"
        )
        body = await self.request("GET", url)
        elements = _unwrap_elements(body)
        companies = [_format_company(e) for e in elements]
        paging = (body or {}).get("paging") or {}
        return {
            "keywords": keywords,
            "start": start,
            "count": count,
            "total": paging.get("total"),
            "companies": companies,
        }

    async def get_profile(self, profile_ref: str) -> dict[str, Any]:
        profile_id = _extract_profile_id(profile_ref)
        if not profile_id:
            raise ValueError(f"Could not parse profile id from: {profile_ref}")

        url = (
            f"{SALES_API_BASE}/salesApiProfiles/"
            f"(profileId:{profile_id},authType:NAME_SEARCH)"
            f"?decorationId={PROFILE_DECORATION}"
        )
        body = await self.request("GET", url)
        if isinstance(body, dict):
            data = body.get("data") or body
            if isinstance(data, dict):
                return _format_lead(data)
        return {"raw": body}

    async def get_company(self, company_ref: str) -> dict[str, Any]:
        company_id = _extract_company_id(company_ref)
        if not company_id:
            raise ValueError(f"Could not parse company id from: {company_ref}")

        url = (
            f"{SALES_API_BASE}/salesApiCompanies/{company_id}"
            f"?decorationId={COMPANY_DECORATION}"
        )
        body = await self.request("GET", url)
        if isinstance(body, dict):
            data = body.get("data") or body
            if isinstance(data, dict):
                return _format_company(data)
        return {"raw": body}

    async def list_saved_lists(self, list_type: str = "people") -> dict[str, Any]:
        """List saved lead or account lists."""
        entity = "LEAD" if list_type == "people" else "ACCOUNT"
        url = (
            f"{SALES_API_BASE}/salesApiLists"
            f"?q=listType&listType={entity}&start=0&count=100"
        )
        body = await self.request("GET", url)
        elements = _unwrap_elements(body)
        lists = []
        for e in elements:
            list_id = _pick(e, "id") or (
                str(_pick(e, "entityUrn", "")).split(":")[-1] if _pick(e, "entityUrn") else None
            )
            lists.append(
                {
                    "id": list_id,
                    "name": _pick(e, "name", "listName"),
                    "count": _pick(e, "listSize", "totalCount"),
                    "type": list_type,
                    "url": f"https://www.linkedin.com/sales/lists/{list_type}/{list_id}" if list_id else None,
                }
            )
        return {"list_type": list_type, "lists": lists}

    async def get_saved_list(
        self,
        list_id: str,
        list_type: str = "people",
        *,
        start: int = 0,
        count: int = 25,
    ) -> dict[str, Any]:
        entity = "people" if list_type == "people" else "company"
        url = (
            f"{SALES_API_BASE}/salesApiLists/{list_id}/listItems"
            f"?q=list&start={start}&count={count}"
        )
        body = await self.request("GET", url, headers={"referer": f"https://www.linkedin.com/sales/lists/{entity}/{list_id}"})
        elements = _unwrap_elements(body)
        if list_type == "people":
            items = [_format_lead(e) for e in elements]
        else:
            items = [_format_company(e) for e in elements]
        paging = (body or {}).get("paging") or {}
        return {
            "list_id": list_id,
            "list_type": list_type,
            "start": start,
            "count": count,
            "total": paging.get("total"),
            "items": items,
        }

    async def search_from_url(self, search_url: str, *, start: int = 0, count: int = 25) -> dict[str, Any]:
        """Execute a Sales Navigator search URL copied from the browser."""
        parsed = urlparse(search_url)
        if "linkedin.com" not in parsed.netloc:
            raise ValueError("URL must be a linkedin.com Sales Navigator search URL")

        path = parsed.path.lower()
        params = parse_qs(parsed.query)

        if "/sales/search/people" in path or "salesapileadsearch" in search_url.lower():
            query = params.get("query", [None])[0]
            if query:
                url = (
                    f"{SALES_API_BASE}/salesApiLeadSearch"
                    f"?q=searchQuery&query={quote(unquote(query), safe='(),:')}"
                    f"&start={start}&count={count}"
                    f"&decorationId={LEAD_SEARCH_DECORATION}"
                )
            else:
                keywords = params.get("keywords", [""])[0]
                return await self.search_leads(keywords, start=start, count=count)
            body = await self.request("GET", url)
            return {
                "search_url": search_url,
                "start": start,
                "count": count,
                "leads": [_format_lead(e) for e in _extract_people(body)],
            }

        if "/sales/search/company" in path or "salesapiaccountsearch" in search_url.lower():
            query = params.get("query", [None])[0]
            if query:
                url = (
                    f"{SALES_API_BASE}/salesApiAccountSearch"
                    f"?q=searchQuery&query={quote(unquote(query), safe='(),:')}"
                    f"&start={start}&count={count}"
                    f"&decorationId={ACCOUNT_SEARCH_DECORATION}"
                )
            else:
                keywords = params.get("keywords", [""])[0]
                return await self.search_companies(keywords, start=start, count=count)
            body = await self.request("GET", url)
            elements = _unwrap_elements(body)
            return {
                "search_url": search_url,
                "start": start,
                "count": count,
                "companies": [_format_company(e) for e in elements],
            }

        if "/sales/lists/" in path:
            parts = [p for p in path.split("/") if p]
            try:
                idx = parts.index("lists")
                list_type = parts[idx + 1]
                list_id = parts[idx + 2]
            except (ValueError, IndexError):
                raise ValueError(f"Could not parse saved list from URL: {search_url}") from None
            return await self.get_saved_list(list_id, list_type, start=start, count=count)

        raise ValueError(
            "Unsupported Sales Navigator URL. Use a people search, company search, or saved list URL."
        )


async def probe_identity(cookies: dict[str, str], csrf_token: str) -> dict[str, Any]:
    client = LinkedInClient(cookies, csrf_token)
    try:
        identity = await client.probe_identity()
        identity["has_sales_nav_cookie"] = bool(cookies.get("li_a"))
        return identity
    finally:
        await client.close()


async def probe_session(cookies: dict[str, str], csrf_token: str) -> dict[str, Any]:
    """Validate cookies and return identity, or raise SessionExpired."""
    if not cookies.get("li_at"):
        raise SessionExpired("Missing li_at cookie")
    if not cookies.get("li_a"):
        raise SessionExpired(
            "Missing Sales Navigator cookie (li_a). Open linkedin.com/sales in Chrome "
            "and confirm your Sales Navigator subscription is active."
        )
    return await probe_identity(cookies, csrf_token)
