#!/usr/bin/env python3
"""NotebookLM Drive source attach — Triodos-proven path (no manual intervention).

Uses MCP Chrome CDP :9222.
Primary: Add sources → Drive → picker iframe (isolated world) → meta multi-select → Select items/Insert.
Fallback: Add sources → Websites → paste Google Doc URLs one-by-one.

Never ask the AE to attach manually. Retry Drive picker if Websites is incomplete.
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.parse
import urllib.request
from typing import Any

from websocket import create_connection

CDP = "http://127.0.0.1:9222"


def _http_json(url: str, method: str = "GET") -> Any:
    req = urllib.request.Request(url, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


class CDPSession:
    def __init__(self, ws_url: str, timeout: float = 180):
        self.ws = create_connection(ws_url, timeout=timeout, suppress_origin=True)
        self.mid = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.mid += 1
        self.ws.send(json.dumps({"id": self.mid, "method": method, "params": params or {}}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self.mid:
                return r

    def eval(self, expr: str, context_id: int | None = None) -> Any:
        params: dict[str, Any] = {
            "expression": expr,
            "returnByValue": True,
            "awaitPromise": True,
        }
        if context_id is not None:
            params["contextId"] = context_id
        r = self.call("Runtime.evaluate", params)
        if "exceptionDetails" in r.get("result", {}):
            raise RuntimeError(str(r["result"]["exceptionDetails"])[:600])
        return r.get("result", {}).get("result", {}).get("value")

    def click_xy(self, x: float, y: float, modifiers: int = 0) -> None:
        for typ in ("mousePressed", "mouseReleased"):
            self.call(
                "Input.dispatchMouseEvent",
                {
                    "type": typ,
                    "x": x,
                    "y": y,
                    "button": "left",
                    "clickCount": 1,
                    "modifiers": modifiers,
                },
            )

    def close(self) -> None:
        try:
            self.ws.close()
        except Exception:
            pass


def find_notebook_tab(notebook_id: str | None = None, notebook_url: str | None = None) -> dict:
    tabs = _http_json(f"{CDP}/json/list")
    pages = [t for t in tabs if t.get("type") == "page"]
    if notebook_url:
        for t in pages:
            if notebook_url.rstrip("/") in (t.get("url") or ""):
                return t
    if notebook_id:
        for t in pages:
            if notebook_id in (t.get("url") or ""):
                return t
    for t in pages:
        u = t.get("url") or ""
        if "notebook.google.com/notebook/" in u or "notebooklm.google.com/notebook/" in u:
            return t
    raise RuntimeError("No NotebookLM notebook tab open in MCP Chrome (CDP 9222)")


def ensure_notebook_tab(notebook_url: str) -> dict:
    try:
        return find_notebook_tab(notebook_url=notebook_url)
    except RuntimeError:
        tab = _http_json(f"{CDP}/json/new?{urllib.parse.quote(notebook_url, safe='')}", method="PUT")
        time.sleep(4)
        return find_notebook_tab(notebook_url=notebook_url) if "id" not in tab else tab


def open_add_sources_drive(nb: CDPSession) -> None:
    nb.call("Page.bringToFront")
    # Dismiss leftover dialogs
    nb.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    nb.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
    time.sleep(0.4)
    opened = nb.eval(
        """(() => {
      const a=[...document.querySelectorAll('button,[role=button]')].find(b=>/Add sources/i.test(b.innerText||b.getAttribute('aria-label')||''));
      if(!a) return false;
      a.click();
      return true;
    })()"""
    )
    if not opened:
        raise RuntimeError("Add sources button not found")
    time.sleep(1.2)
    # Prefer exact short "Drive" tile — not drive_presentation source chips
    drive = nb.eval(
        """(() => {
      const nodes=[...document.querySelectorAll('button,[role=button]')];
      let d=nodes.find(b=>{
        const t=(b.innerText||b.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim();
        return t==='Drive' || t==='drive Drive' || /^drive\\s*$/i.test(t);
      });
      if(!d) d=nodes.find(b=>{
        const t=(b.innerText||b.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim();
        return t.toLowerCase().endsWith('drive') && t.length<=20 && !/presentation|pdf/i.test(t);
      });
      if(!d) return {ok:false, sample:nodes.map(b=>(b.innerText||'').replace(/\\s+/g,' ').trim()).filter(t=>t&&t.length<40).slice(0,40)};
      d.click();
      return {ok:true, text:(d.innerText||d.getAttribute('aria-label')||'').slice(0,40)};
    })()"""
    )
    if not (isinstance(drive, dict) and drive.get("ok")):
        raise RuntimeError(f"Drive tile not found: {drive}")
    time.sleep(4)


def picker_context(nb: CDPSession) -> tuple[dict, int]:
    iframe_info = nb.eval(
        """(() => {
      const ifr=[...document.querySelectorAll('iframe')].filter(f=>(f.src||'').includes('picker')&&f.getBoundingClientRect().width>100);
      if(!ifr.length) return null;
      const f=ifr[ifr.length-1];
      const r=f.getBoundingClientRect();
      return {x:r.x,y:r.y,w:r.width,h:r.height,id:f.id,src:f.src.slice(0,120)};
    })()"""
    )
    if not iframe_info:
        raise RuntimeError("Drive picker iframe not present")
    ft = nb.call("Page.getFrameTree")
    frames: list[dict] = []

    def walk(n: dict) -> None:
        frames.append(n.get("frame") or {})
        for c in n.get("childFrames") or []:
            walk(c)

    walk(ft["result"]["frameTree"])
    picker = next((f for f in frames if "picker" in (f.get("url") or "")), None)
    if not picker:
        raise RuntimeError("Picker frame not in frame tree")
    world = nb.call(
        "Page.createIsolatedWorld",
        {
            "frameId": picker["id"],
            "worldName": f"nlm_attach_{int(time.time())}",
            "grantUniversalAccess": True,
        },
    )
    ctx = world["result"]["executionContextId"]
    return iframe_info, ctx


def search_picker(nb: CDPSession, ctx: int, query: str) -> None:
    box = nb.eval(
        """(() => {
      const input=document.querySelector('input[type=text], input[aria-label*="Search" i], input[placeholder*="Search" i]');
      if(!input) return null;
      const r=input.getBoundingClientRect();
      input.focus();
      return {x:r.x+r.width/2,y:r.y+r.height/2};
    })()""",
        context_id=ctx,
    )
    if not box:
        return
    # Parent-page clicks need iframe offset applied by caller — search uses in-frame Input via isolated eval + key events on page
    # Use JS value set + Enter inside picker world
    nb.eval(
        f"""(() => {{
      const input=document.querySelector('input[type=text], input[aria-label*="Search" i], input[placeholder*="Search" i]');
      if(!input) return false;
      const set=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;
      input.focus();
      set.call(input, {json.dumps(query)});
      input.dispatchEvent(new Event('input',{{bubbles:true}}));
      input.dispatchEvent(new KeyboardEvent('keydown',{{key:'Enter',bubbles:true}}));
      input.dispatchEvent(new KeyboardEvent('keyup',{{key:'Enter',bubbles:true}}));
      return true;
    }})()""",
        context_id=ctx,
    )
    time.sleep(2.5)


def select_names_in_picker(nb: CDPSession, iframe_info: dict, ctx: int, names: list[str]) -> dict:
    ox, oy = iframe_info["x"], iframe_info["y"]
    first = True
    selected: list[str] = []
    missing: list[str] = []

    for name in names:
        # Prefer search when list is long / file not in Recent
        search_picker(nb, ctx, name.split("—")[0].strip()[:60] if "—" in name else name[:60])
        nb.eval(
            f"""(() => {{
          const opt=[...document.querySelectorAll('[role=option]')].find(el => {{
            const t=(el.innerText||'').trim().split('\\n')[0];
            return t==={json.dumps(name)} || t.includes({json.dumps(name[:40])});
          }});
          if(opt) opt.scrollIntoView({{block:'center'}});
        }})()""",
            context_id=ctx,
        )
        time.sleep(0.35)
        r2 = nb.eval(
            f"""(() => {{
          const opts=[...document.querySelectorAll('[role=option]')];
          let opt=opts.find(el => (el.innerText||'').trim().split('\\n')[0]==={json.dumps(name)});
          if(!opt) opt=opts.find(el => (el.innerText||'').includes({json.dumps(name[:40])}));
          if(!opt) return null;
          const r=opt.getBoundingClientRect();
          return {{x:r.x+36, y:r.y+r.height/2, t:(el=> (el.innerText||'').trim().split('\\n')[0])(opt)}};
        }})()""",
            context_id=ctx,
        )
        if not r2:
            missing.append(name)
            continue
        mods = 0 if first else 4  # Meta multi-select on Mac CDP
        nb.click_xy(ox + r2["x"], oy + r2["y"], modifiers=mods)
        first = False
        selected.append(r2.get("t") or name)
        time.sleep(0.45)

    # Confirm button: "Select items" or "Insert"
    btn = nb.eval(
        """(() => {
          const labels=['Select items','Insert','Open','Select'];
          for (const lab of labels) {
            const b=[...document.querySelectorAll('button')].find(el => (el.innerText||'').trim()===lab && !el.disabled);
            if(b){
              const r=b.getBoundingClientRect();
              return {lab, x:r.x+r.width/2, y:r.y+r.height/2};
            }
          }
          return {labs:[...document.querySelectorAll('button')].map(b=>(b.innerText||'').trim()).filter(Boolean).slice(0,25)};
        })()""",
        context_id=ctx,
    )
    if isinstance(btn, dict) and "x" in btn:
        nb.click_xy(ox + btn["x"], oy + btn["y"], modifiers=0)
        time.sleep(8)
    return {"selected": selected, "missing": missing, "confirm": btn}


def attach_via_drive(notebook_url: str, names: list[str]) -> dict:
    tab = ensure_notebook_tab(notebook_url)
    try:
        urllib.request.urlopen(f"{CDP}/json/activate/{tab['id']}").read()
    except Exception:
        pass
    nb = CDPSession(tab["webSocketDebuggerUrl"])
    try:
        if notebook_url not in (tab.get("url") or ""):
            nb.call("Page.navigate", {"url": notebook_url})
            time.sleep(5)
        open_add_sources_drive(nb)
        iframe_info, ctx = picker_context(nb)
        result = select_names_in_picker(nb, iframe_info, ctx, names)
        body = nb.eval("(document.body.innerText||'').slice(0,8000)") or ""
        found = [n for n in names if n[:28].lower() in body.lower() or any(p.lower() in body.lower() for p in n.split()[:4])]
        result["verified_in_ui"] = found
        result["source_count_hint"] = ( __import__("re").search(r"(\d+)\s*sources?", body, __import__("re").I) or [None, None])[1]
        result["ok"] = len(result["missing"]) == 0 or len(found) >= max(1, len(names) - len(result["missing"]))
        return result
    finally:
        nb.close()


def attach_via_websites(notebook_url: str, urls: list[str]) -> dict:
    """Fallback: Websites tile + paste Google Doc URLs."""
    tab = ensure_notebook_tab(notebook_url)
    nb = CDPSession(tab["webSocketDebuggerUrl"])
    attached = []
    failed = []
    try:
        nb.call("Page.navigate", {"url": notebook_url})
        time.sleep(4)
        for url in urls:
            nb.eval(
                """(() => {
                  const a=[...document.querySelectorAll('button,[role=button]')].find(b=>/Add sources/i.test(b.innerText||''));
                  a && a.click();
                })()"""
            )
            time.sleep(1.2)
            ok = nb.eval(
                """(() => {
                  const nodes=[...document.querySelectorAll('button,[role=button]')];
                  const w=nodes.find(b=>{
                    const t=(b.innerText||b.getAttribute('aria-label')||'').replace(/\\s+/g,' ').trim().toLowerCase();
                    return t==='websites' || t.endsWith('websites') || t==='website';
                  });
                  if(!w) return false;
                  w.click();
                  return true;
                })()"""
            )
            if not ok:
                failed.append(url)
                continue
            time.sleep(1.5)
            box = nb.eval(
                """(() => {
                  const inputs=[...document.querySelectorAll('input,textarea')].filter(i=>i.getBoundingClientRect().width>150);
                  const input=inputs.find(i=>/url|paste|link|website/i.test((i.placeholder||'')+(i.getAttribute('aria-label')||'')))
                    || inputs.sort((a,b)=>b.getBoundingClientRect().width-a.getBoundingClientRect().width)[0];
                  if(!input) return null;
                  const r=input.getBoundingClientRect();
                  input.focus();
                  return {x:r.x+r.width/2,y:r.y+r.height/2};
                })()"""
            )
            if not box:
                failed.append(url)
                continue
            nb.click_xy(box["x"], box["y"])
            nb.call("Input.dispatchKeyEvent", {"type": "keyDown", "key": "a", "code": "KeyA", "modifiers": 2, "windowsVirtualKeyCode": 65})
            nb.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": "a", "code": "KeyA", "modifiers": 2, "windowsVirtualKeyCode": 65})
            nb.call("Input.insertText", {"text": url})
            time.sleep(0.3)
            sub = nb.eval(
                """(() => {
                  for (const lab of ['Insert','Add','Done','Import']) {
                    const b=[...document.querySelectorAll('button')].find(el=>(el.innerText||'').trim()===lab && !el.disabled);
                    if(b){ b.click(); return lab; }
                  }
                  return null;
                })()"""
            )
            time.sleep(5)
            if sub:
                attached.append(url)
            else:
                failed.append(url)
        return {"attached": attached, "failed": failed, "ok": len(failed) == 0}
    finally:
        nb.close()


def attach_sources(
    notebook_url: str,
    *,
    drive_names: list[str] | None = None,
    website_urls: list[str] | None = None,
) -> dict:
    """Always try Drive picker (Triodos path). Optionally also try Websites URLs."""
    report: dict[str, Any] = {"notebook_url": notebook_url, "steps": []}
    if website_urls:
        try:
            w = attach_via_websites(notebook_url, website_urls)
            report["steps"].append({"websites": w})
        except Exception as e:
            report["steps"].append({"websites_error": str(e)})
    if drive_names:
        # Drive picker can attach what Websites missed; always run for reliability
        d = attach_via_drive(notebook_url, drive_names)
        report["steps"].append({"drive": d})
        report["ok"] = bool(d.get("ok"))
        report["missing"] = d.get("missing") or []
        return report
    report["ok"] = bool(report["steps"]) and all(
        (s.get("websites") or {}).get("ok") for s in report["steps"] if "websites" in s
    )
    return report


def main() -> None:
    ap = argparse.ArgumentParser(description="Attach Drive docs to NotebookLM (Triodos CDP method)")
    ap.add_argument("--notebook-url", required=True)
    ap.add_argument("--name", action="append", default=[], help="Drive file display name (repeatable)")
    ap.add_argument("--url", action="append", default=[], help="Optional Google Doc URL for Websites fallback")
    args = ap.parse_args()
    if not args.name and not args.url:
        raise SystemExit("Provide --name and/or --url")
    result = attach_sources(args.notebook_url, drive_names=args.name or None, website_urls=args.url or None)
    print(json.dumps(result, indent=2))
    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
