#!/usr/bin/env python3
"""
Fill ClosePlan MEDDPICC scorecards on Red Hat Sales Cloud opportunities.

Requires:
  - Chrome with remote debugging on CDP 9223 (Lightning session signed in)
  - Valid REST sid in salescloud-assistant session.json
  - Deal already deployed (MEDDPICC tab Create) OR Create button available
  - Customer_Pain_Point__c populated on Opportunity before Field question scoring

Usage:
  /Users/alexandrumarcov/mcps/salescloud-assistant/.venv/bin/python \\
    fill_closeplan_meddpicc.py --config opps.json

  opps.json example:
  {
    "006Pe00000f6hp3IAA": {
      "name": "Keylane renewal",
      "deal": null,
      "rich": {
        "Metrics": "<p>...</p>",
        "Decision Criteria": "<p>...</p>",
        "Decision Process": "<p>...</p>",
        "Paper Process": "<p>...</p>",
        "Competition": "<p>...</p>"
      }
    }
  }

Target: UI Progress ≥75% (~90.8% without Contact Tracking).
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import unquote

from playwright.sync_api import sync_playwright

DEFAULT_SESSION = Path.home() / "mcps/salescloud-assistant/session.json"
API = "https://redhatcrm.my.salesforce.com/services/data/v62.0"
LIGHTNING = "https://redhatcrm.lightning.force.com"
TMPL = "a2IPe000002fPMHMA2"  # [2174#1] Red Hat - Opp. Intelligence 3
CDP = "http://127.0.0.1:9223"
AURA_LOADED = "4202_QR0CSUvXMW_BWtwpm_J2Ww"


def load_sid(session_path: Path) -> str:
    data = json.loads(Path(session_path).expanduser().read_text())
    sid = data.get("sid") or data.get("access_token")
    if not sid:
        raise SystemExit(f"No sid/access_token in {session_path}")
    return sid


def patch(sid: str, obj: str, rid: str, payload: dict) -> int:
    req = urllib.request.Request(
        f"{API}/sobjects/{obj}/{rid}",
        data=json.dumps(payload).encode(),
        method="PATCH",
        headers={"Authorization": f"Bearer {sid}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def get_deal_id(sid: str, opp_id: str) -> str | None:
    req = urllib.request.Request(
        f"{API}/sobjects/Opportunity/{opp_id}?fields=TSPC__CPDeal__c",
        headers={"Authorization": f"Bearer {sid}"},
    )
    return json.load(urllib.request.urlopen(req)).get("TSPC__CPDeal__c")


def fill_ops(q: dict, rich: dict) -> tuple[list, dict]:
    """Return REST patch ops + in-memory question updates for auraSave."""
    mode = q.get("TSPC__Mode__c")
    text = q.get("TSPC__Text__c") or ""
    qid = q["Id"]
    ops: list = []
    maxs = q.get("TSPC__MaxScore__c") or 0

    if mode == "Answers":
        answers = q.get("TSPC__Answers__r") or []
        if not answers:
            return ops, q
        if "Technical Win" in text:
            chosen = next((a for a in answers if a.get("TSPC__Text__c") == "Yes"), None)
            if not chosen:
                chosen = answers[0]
        else:
            chosen = max(answers, key=lambda a: a.get("TSPC__MaxScore__c") or 0)
        for a in answers:
            sel = a["Id"] == chosen["Id"]
            score = (a.get("TSPC__MaxScore__c") or 0) if sel else 0
            a["TSPC__IsSelected__c"] = sel
            a["TSPC__Score__c"] = score
            ops.append(
                (
                    "TSPC__DealQuestionAnswer__c",
                    a["Id"],
                    {"TSPC__IsSelected__c": sel, "TSPC__Score__c": score},
                )
            )
        q["TSPC__Score__c"] = chosen.get("TSPC__MaxScore__c") or 0
        q["TSPC__IsAnswered__c"] = True
        ops.append(("TSPC__DealQuestion__c", qid, {"TSPC__Score__c": q["TSPC__Score__c"]}))

    elif mode == "RichText":
        mapping = [
            ("Summarize the Metrics", "Metrics"),
            ("Decision Criteria", "Decision Criteria"),
            ("Decision Process", "Decision Process"),
            ("Paper Process", "Paper Process"),
            ("Competition", "Competition"),
        ]
        for key, rk in mapping:
            if key in text and rk in rich:
                q["TSPC__RichTextAnswer__c"] = rich[rk]
                q["TSPC__Answer__c"] = "Yes"
                q["TSPC__Score__c"] = maxs
                q["TSPC__IsAnswered__c"] = True
                ops.append(
                    (
                        "TSPC__DealQuestion__c",
                        qid,
                        {
                            "TSPC__RichTextAnswer__c": rich[rk],
                            "TSPC__Answer__c": "Yes",
                            "TSPC__Score__c": maxs,
                        },
                    )
                )
                break

    elif mode == "Yes-No":
        ans = "No" if "competing against another vendor" in text.lower() else "Yes"
        q["TSPC__Answer__c"] = ans
        q["TSPC__IsAnswered__c"] = True
        ops.append(("TSPC__DealQuestion__c", qid, {"TSPC__Answer__c": ans}))

    elif mode == "Field":
        # Requires Customer_Pain_Point__c already on Opportunity
        q["TSPC__Answer__c"] = "Yes"
        q["TSPC__Score__c"] = maxs
        q["TSPC__IsAnswered__c"] = True
        ops.append(
            ("TSPC__DealQuestion__c", qid, {"TSPC__Answer__c": "Yes", "TSPC__Score__c": maxs})
        )

    # ContactTracking skipped unless contact Ids known (~8 pts)

    return ops, q


def capture_aura_ctx(page) -> dict:
    ctx: dict = {}

    def on_request(req):
        if req.method == "POST" and "/aura" in req.url:
            pd = unquote(req.post_data or "")
            if "CPWWrapController" in pd and "auraGetModel" in pd:
                m = re.search(r"aura\.token=([^&]+)", pd)
                if m:
                    ctx["token"] = unquote(m.group(1))
                m = re.search(r'"fwuid"\s*:\s*"([^"]+)"', pd)
                if m:
                    ctx["fwuid"] = m.group(1)
                if "aura.pageURI=" in pd:
                    ctx["pageURI"] = unquote(re.search(r"aura.pageURI=([^&]+)", pd).group(1))

    page.on("request", on_request)
    return ctx


def open_meddpicc(page, opp_id: str) -> None:
    page.goto(
        f"{LIGHTNING}/lightning/r/Opportunity/{opp_id}/view",
        wait_until="domcontentloaded",
        timeout=120000,
    )
    page.wait_for_timeout(8000)
    page.locator('[role="tab"]', has_text="MEDDPICC").click()
    page.wait_for_timeout(10000)


def fill_one(page, sid: str, opp_id: str, meta: dict) -> dict:
    ctx = capture_aura_ctx(page)
    open_meddpicc(page, opp_id)

    deal_id = meta.get("deal") or get_deal_id(sid, opp_id)
    if not deal_id:
        create = page.locator('[data-aura-class*="TSPC"] button').filter(has_text="Create")
        if create.count():
            create.first.click()
            page.wait_for_timeout(15000)
        deal_id = get_deal_id(sid, opp_id)
    if not deal_id:
        return {"name": meta.get("name", opp_id), "error": "no deal — Create on MEDDPICC tab first"}

    if not ctx.get("token"):
        # force another model load
        page.reload(wait_until="domcontentloaded")
        page.wait_for_timeout(8000)
        page.locator('[role="tab"]', has_text="MEDDPICC").click()
        page.wait_for_timeout(10000)

    questions = page.evaluate(
        """async ({ctx, dealId, oppId, tmplId, loaded}) => {
          async function aura(desc, params, caller='UNKNOWN') {
            const message = JSON.stringify({actions:[{id:'1;a', descriptor:desc, callingDescriptor:caller, params}]});
            const auraContext = JSON.stringify({mode:'PROD', fwuid:ctx.fwuid, app:'one:one', loaded:{'APPLICATION@markup://one:one':loaded}, dn:[], globals:{density:'VIEW_ONE'}, uad:true});
            const body = new URLSearchParams({message, 'aura.context': auraContext, 'aura.pageURI': ctx.pageURI, 'aura.token': ctx.token});
            const r = await fetch('/aura?r=130&aura.ApexAction.execute=1', {method:'POST', credentials:'include', headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'}, body});
            return r.json();
          }
          const rec = await aura('apex://TSPC.CPCDealScorecardController/ACTION$auraGetRecords',
            {parentId:dealId, tmplId, oppId}, 'markup://TSPC:CPCDealScorecard');
          return rec.actions[0].returnValue.questions;
        }""",
        {"ctx": ctx, "dealId": deal_id, "oppId": opp_id, "tmplId": TMPL, "loaded": AURA_LOADED},
    )

    qs = copy.deepcopy(questions)
    ops: list = []
    for i, q in enumerate(qs):
        o, q2 = fill_ops(q, meta["rich"])
        ops.extend(o)
        qs[i] = q2
    ok = sum(1 for o in ops if patch(sid, *o) == 204)

    save = page.evaluate(
        """async ({ctx, dealId, oppId, tmplId, questions, loaded}) => {
          async function aura(desc, params) {
            const message = JSON.stringify({actions:[{id:'999;a', descriptor:desc, callingDescriptor:'markup://TSPC:CPCDealScorecard', params}]});
            const auraContext = JSON.stringify({mode:'PROD', fwuid:ctx.fwuid, app:'one:one', loaded:{'APPLICATION@markup://one:one':loaded}, dn:[], globals:{density:'VIEW_ONE'}, uad:true});
            const body = new URLSearchParams({message, 'aura.context': auraContext, 'aura.pageURI': ctx.pageURI, 'aura.token': ctx.token});
            const r = await fetch('/aura?r=131&aura.ApexAction.execute=1', {method:'POST', credentials:'include', headers:{'Content-Type':'application/x-www-form-urlencoded; charset=UTF-8'}, body});
            return r.json();
          }
          const s = await aura('apex://TSPC.CPCDealScorecardController/ACTION$auraSave',
            {parentId:dealId, tmplId, oppId, questions});
          const m = await aura('apex://TSPC.CPWWrapController/ACTION$auraGetModel',
            {recordId: oppId, type:'Opportunity'});
          return {
            saveState: s.actions[0].state,
            ratio: m.actions[0].returnValue.deal.TSPC__ScorecardScoreRatio__c
          };
        }""",
        {
            "ctx": ctx,
            "dealId": deal_id,
            "oppId": opp_id,
            "tmplId": TMPL,
            "questions": qs,
            "loaded": AURA_LOADED,
        },
    )

    page.reload(wait_until="domcontentloaded")
    page.wait_for_timeout(8000)
    page.locator('[role="tab"]', has_text="MEDDPICC").click()
    page.wait_for_timeout(10000)
    ui = [
        l.strip()
        for l in page.locator("body").inner_text().split("\n")
        if l.strip().startswith("Progress:")
        or ("Risk" in l and "%" in l and len(l) < 40)
    ]
    return {
        "name": meta.get("name", opp_id),
        "oppId": opp_id,
        "dealId": deal_id,
        "ui": ui,
        "saveState": save.get("saveState"),
        "ratio": save.get("ratio"),
        "opsOk": ok,
        "opsTotal": len(ops),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Fill ClosePlan MEDDPICC scorecards ≥75%")
    ap.add_argument("--config", required=True, help="JSON map of oppId → {name, deal?, rich}")
    ap.add_argument("--cdp", default=CDP, help="Chrome CDP endpoint (default 9223)")
    ap.add_argument("--session", default=str(DEFAULT_SESSION), help="JSON with Salesforce sid")
    args = ap.parse_args()

    opps = json.loads(Path(args.config).read_text())
    sid = load_sid(Path(args.session))

    results = []
    with sync_playwright() as p:
        browser = p.chromium.connect_over_cdp(args.cdp)
        for opp_id, meta in opps.items():
            page = browser.contexts[0].new_page()
            try:
                results.append(fill_one(page, sid, opp_id, meta))
            except Exception as e:
                results.append({"name": meta.get("name", opp_id), "oppId": opp_id, "error": str(e)})
            finally:
                page.close()

    print(json.dumps(results, indent=2))
    return 0 if all("error" not in r for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
