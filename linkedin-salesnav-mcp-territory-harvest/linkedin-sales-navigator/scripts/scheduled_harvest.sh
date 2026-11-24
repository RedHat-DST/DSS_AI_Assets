#!/usr/bin/env bash
# One paced harvest batch during work hours. Skips if Sales Nav is not signed in.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv/bin/python"
OUT="$ROOT/output"
LOG="$OUT/scheduled_harvest.log"
LOCK="$OUT/scheduled_harvest.lock"

# Work hours (local time): Mon–Fri, 09:00–17:59
WORK_START="${WORK_START:-9}"
WORK_END="${WORK_END:-18}"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

mkdir -p "$OUT"

if [[ -f "$LOCK" ]]; then
  log "SKIP: another scheduled run appears active ($LOCK)"
  exit 0
fi
trap 'rm -f "$LOCK"' EXIT
echo "$$" >"$LOCK"

DOW="$(date +%u)"   # 1=Mon … 7=Sun
HOUR="$(date +%H | sed 's/^0*//')"
HOUR="${HOUR:-0}"

if [[ "$DOW" -gt 5 ]]; then
  log "SKIP: weekend"
  exit 0
fi
if [[ "$HOUR" -lt "$WORK_START" || "$HOUR" -ge "$WORK_END" ]]; then
  log "SKIP: outside work hours ($HOUR:00, window ${WORK_START}:00–${WORK_END}:00)"
  exit 0
fi

cd "$ROOT"

log "Checking Sales Navigator session..."
if ! "$VENV" - <<'PY' >>"$LOG" 2>&1
import asyncio
import sys

sys.path.insert(0, ".")
from src.auth import AuthRequired, get_auth
from src.chrome import has_sales_nav_session


async def main() -> None:
    auth = get_auth()
    session = await auth.probe_saved_session()
    if not session or not has_sales_nav_session(session.get("cookies") or {}):
        raise AuthRequired("no saved session")
    client = await auth.ensure_client()
    await client.probe_identity()
    await client.close()


try:
    asyncio.run(main())
except Exception as e:
    print(f"session check failed: {e}", file=sys.stderr)
    sys.exit(1)
PY
then
  log "SKIP: Sales Nav not signed in — open MCP Chrome, sign in at linkedin.com/sales, then wait for the next slot."
  exit 0
fi

DONE_BEFORE="$("$VENV" -c "
import json
from pathlib import Path
for name in ('nl_core_territory2_persona_harvest_progress.json', 'persona_harvest_progress.json'):
    p = Path('$OUT') / name
    if p.exists():
        print(len(set(json.load(open(p)).get('done', []))))
        break
else:
    print(0)
" 2>/dev/null || echo 0)"
TOTAL="$("$VENV" -c "import json; print(json.load(open('$OUT/nl_core_territory2_accounts.json'))['account_count'])")"

# One-time fallback requeue for no_company_match (short name + Sales Group)
"$VENV" - <<'PY' >>"$LOG" 2>&1 || true
import json
from pathlib import Path
out = Path("/Users/alexandrumarcov/mcps/linkedin-sales-navigator/output")
for name in ("nl_core_territory2_persona_harvest_progress.json", "persona_harvest_progress.json"):
    p = out / name
    if not p.exists():
        continue
    progress = json.loads(p.read_text())
    if progress.get("fallback_pass_v2"):
        continue
    unmatched = {
        (s.get("account_name") or "").strip()
        for s in (progress.get("summaries") or [])
        if (s.get("search_status") or "") == "no_company_match" and (s.get("account_name") or "").strip()
    }
    if not unmatched:
        progress["fallback_pass_v2"] = True
        p.write_text(json.dumps(progress, indent=2))
        continue
    progress["done"] = [n for n in (progress.get("done") or []) if n not in unmatched]
    progress["summaries"] = [
        s for s in (progress.get("summaries") or [])
        if (s.get("account_name") or "").strip() not in unmatched
    ]
    progress["personas"] = [
        row for row in (progress.get("personas") or [])
        if (row.get("account_name") or "").strip() not in unmatched
    ]
    progress["fallback_pass_v2"] = True
    progress["fallback_retry_queued"] = sorted(unmatched)
    p.write_text(json.dumps(progress, indent=2))
    print(f"Re-queued {len(unmatched)} no_company_match accounts in {p.name}")
PY

DONE_BEFORE="$("$VENV" -c "
import json
from pathlib import Path
for name in ('nl_core_territory2_persona_harvest_progress.json', 'persona_harvest_progress.json'):
    p = Path('$OUT') / name
    if p.exists():
        print(len(set(json.load(open(p)).get('done', []))))
        break
else:
    print(0)
" 2>/dev/null || echo 0)"

if [[ "$DONE_BEFORE" -ge "$TOTAL" ]]; then
  log "Already complete ($DONE_BEFORE/$TOTAL). Running export only."
  "$VENV" scripts/postprocess_harvest_splits.py >>"$LOG" 2>&1
  "$VENV" scripts/export_revenue_buckets.py >>"$LOG" 2>&1
  "$VENV" scripts/export_persona_roles.py >>"$LOG" 2>&1
  exit 0
fi

log "Starting paced batch ($DONE_BEFORE/$TOTAL)..."
"$VENV" scripts/territory_persona_harvest.py >>"$LOG" 2>&1

DONE_AFTER="$("$VENV" -c "import json; print(len(json.load(open('$OUT/persona_harvest_progress.json')).get('done',[])))")"
log "Batch done: $DONE_AFTER/$TOTAL (+$((DONE_AFTER - DONE_BEFORE)))"

if [[ "$DONE_AFTER" -ge "$TOTAL" ]]; then
  log "Territory complete — post-process and export."
  "$VENV" scripts/postprocess_harvest_splits.py >>"$LOG" 2>&1
  "$VENV" scripts/export_revenue_buckets.py >>"$LOG" 2>&1
  "$VENV" scripts/export_persona_roles.py >>"$LOG" 2>&1
  log "Finished. Buckets in ~/Downloads/NL_*_salesnav_*"
fi
