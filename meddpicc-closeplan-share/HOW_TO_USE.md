# ClosePlan MEDDPICC fill script — quick start

Fills the Red Hat Sales Cloud **MEDDPICC / ClosePlan** scorecard so UI Progress reaches **≥75%** (typically ~90% without linking EB/Champion contacts).

## What you need

1. **Python 3.11+** with Playwright:
   ```bash
   python3 -m venv .venv && source .venv/bin/activate
   pip install playwright && playwright install chromium
   ```
2. **Chrome** with remote debugging on **9223**, signed into Salesforce:
   ```bash
   /Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome \
     --remote-debugging-port=9223 \
     --user-data-dir="$HOME/chrome-sf-debug"
   ```
3. A **`session.json`** with your Salesforce sid, e.g. `{ "sid": "00D....!...." }`  
   (Cursor Sales Cloud MCP writes this after SSO if you use that setup.)

## Steps

1. On the opp, fill **Customer Pain Point** in RHSC (Field question reads it).
2. MEDDPICC tab → **Create** if no ClosePlan yet.
3. Copy `opps.example.json` → `opps.json` and put your opp Id + short HTML for Metrics / Decision Criteria / Decision Process / Paper Process / Competition.
4. Run:
   ```bash
   source .venv/bin/activate
   python fill_closeplan_meddpicc.py \
     --config opps.json \
     --session ~/path/to/session.json \
     --cdp http://127.0.0.1:9223
   ```
5. Check printed JSON and the MEDDPICC **Progress** bar (≥75%).

## Watch-outs

- Use MEDDPICC tab **Create** — do not bare-API create the deal.
- Do not delete/recreate deals to fix scores.
- ~28% Progress → answers not patched; ~68% → RichText/Field scores missing.

Questions → Alexandru Marcov (`amarcov@redhat.com`).
