#!/usr/bin/env bash
# Full pipeline: session-gated paced harvest → postprocess → revenue buckets → DONE.
# Designed not to stall: short batches, circuit-breaker on 429, skip when logged out.
#
# Usage:
#   scripts/run_loop.sh \
#     --accounts /path/to/accounts.json \
#     --output /path/to/output \
#     --territory-id NL_COMM_TERR_CORE_POD01_TERR02 \
#     --prefix nl_core_territory2
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_ROOT="${SALESNAV_MCP_ROOT:-$HOME/mcps/linkedin-sales-navigator}"
PYTHON="${SALESNAV_HARVEST_PYTHON:-$MCP_ROOT/.venv/bin/python}"
ACCOUNTS=""
OUTPUT=""
TERRITORY_ID=""
PREFIX=""
COUNTRY="Netherlands"
MAX_PER_RUN=25
DELAY=6
DELAY_JITTER=4
BATCH_SIZE=0
BATCH_PAUSE=90
RATE_LIMIT_STOP=3
CYCLE_PAUSE_OK=120
CYCLE_PAUSE_RATE_LIMIT=900
CYCLE_PAUSE_NO_SESSION=0
UNLOAD_AGENT_ON_DONE=1

while [[ $# -gt 0 ]]; do
  case "$1" in
    --accounts) ACCOUNTS="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --territory-id) TERRITORY_ID="$2"; shift 2 ;;
    --prefix) PREFIX="$2"; shift 2 ;;
    --country) COUNTRY="$2"; shift 2 ;;
    --mcp-root) MCP_ROOT="$2"; PYTHON="$MCP_ROOT/.venv/bin/python"; shift 2 ;;
    --max-per-run) MAX_PER_RUN="$2"; shift 2 ;;
    --delay) DELAY="$2"; shift 2 ;;
    --cycle-pause) CYCLE_PAUSE_OK="$2"; shift 2 ;;
    --rate-limit-pause) CYCLE_PAUSE_RATE_LIMIT="$2"; shift 2 ;;
    --keep-agent) UNLOAD_AGENT_ON_DONE=0; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

if [[ -z "$ACCOUNTS" || -z "$OUTPUT" || -z "$TERRITORY_ID" ]]; then
  echo "Required: --accounts --output --territory-id" >&2
  exit 1
fi

if [[ -z "$PREFIX" ]]; then
  PREFIX="$(echo "$TERRITORY_ID" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g; s/^_|_$//g')"
fi

if [[ ! -x "$PYTHON" ]]; then
  echo "Python not found: $PYTHON (run install.sh)" >&2
  exit 1
fi

export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
mkdir -p "$OUTPUT"

SLUG="$(echo "$TERRITORY_ID" | tr '[:upper:]' '[:lower:]' | sed -E 's/[^a-z0-9]+/_/g; s/^_|_$//g')"
PROGRESS="$OUTPUT/${PREFIX}_persona_harvest_progress.json"
LEGACY_PROGRESS="$OUTPUT/persona_harvest_progress.json"
LOCK_FILE="$OUTPUT/${SLUG}_salesnav_loop.pid"
STATE_FILE="$OUTPUT/${SLUG}_salesnav_state.json"
DONE_FILE="$OUTPUT/${SLUG}_salesnav_DONE"
LOG_FILE="$OUTPUT/${SLUG}_salesnav_loop.log"
AGENT_LABEL="com.redhat.salesnav-harvest.$(echo "$TERRITORY_ID" | tr '[:upper:]' '[:lower:]' | tr '_' '-')"

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"; }

write_state() {
  local phase="$1"
  "$PYTHON" - <<PY
import json
from pathlib import Path
from datetime import datetime
Path("$STATE_FILE").write_text(json.dumps({
  "territory": "$TERRITORY_ID",
  "prefix": "$PREFIX",
  "phase": "$phase",
  "updated_at": datetime.now().isoformat(timespec="seconds"),
}, indent=2) + "\n")
PY
}

progress_path() {
  if [[ -f "$PROGRESS" ]]; then echo "$PROGRESS"
  elif [[ -f "$LEGACY_PROGRESS" ]]; then echo "$LEGACY_PROGRESS"
  else echo "$PROGRESS"
  fi
}

unique_total() {
  "$PYTHON" - <<PY
import json
from pathlib import Path
data = json.loads(Path("$ACCOUNTS").read_text())
names = {(a.get("account_name") or a.get("Name") or "").strip() for a in (data.get("accounts") or [])}
names.discard("")
print(len(names))
PY
}

unique_done() {
  local p
  p="$(progress_path)"
  "$PYTHON" - <<PY
import json
from pathlib import Path
p = Path("$p")
print(len(set(json.load(open(p)).get("done", []))) if p.exists() else 0)
PY
}

session_ok() {
  "$PYTHON" - <<PY
import asyncio, sys
sys.path.insert(0, "$MCP_ROOT")
from src.auth import get_auth
from src.chrome import cdp_alive, has_sales_nav_session
from src.config import load_config

cfg = load_config()
if not cdp_alive(cfg.cdp_port):
    # Try silent spawn via ensure path
    pass

async def main():
    auth = get_auth()
    try:
        session = await auth.probe_saved_session()
    except Exception:
        return False
    if not session:
        return False
    return has_sales_nav_session(session.get("cookies") or {})

try:
    ok = asyncio.run(main())
except Exception:
    ok = False
sys.exit(0 if ok else 1)
PY
}

unload_agent() {
  if [[ "$UNLOAD_AGENT_ON_DONE" -eq 1 ]]; then
    launchctl bootout "gui/$(id -u)/${AGENT_LABEL}" 2>/dev/null || true
    log "Unloaded LaunchAgent ${AGENT_LABEL}"
  fi
}

if [[ -f "$DONE_FILE" ]]; then
  log "DONE marker present ($DONE_FILE). Nothing to do."
  unload_agent
  exit 0
fi

if [[ -f "$LOCK_FILE" ]]; then
  old_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    log "Already running (pid $old_pid), exiting."
    exit 0
  fi
fi

echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

# Preflight (non-strict session — we gate batches ourselves)
bash "$SKILL_DIR/scripts/preflight.sh" \
  --accounts "$ACCOUNTS" --output "$OUTPUT" --mcp-root "$MCP_ROOT" \
  >> "$LOG_FILE" 2>&1 || {
  log "Preflight failed — see $LOG_FILE"
  exit 1
}

TOTAL="$(unique_total)"
d="$(unique_done)"
log "Starting Sales Nav pipeline for $TERRITORY_ID (harvest $d/$TOTAL unique, pid $$)"
write_state "harvest"

consecutive_no_progress=0

while true; do
  d="$(unique_done)"
  log "Harvest progress: $d/$TOTAL unique"
  if [[ "$d" -ge "$TOTAL" ]]; then
    break
  fi

  if ! session_ok; then
    log "SKIP batch: Sales Nav session missing. Sign in at linkedin.com/sales in MCP Chrome."
    write_state "waiting_for_session"
    # Exit cleanly so LaunchAgent does not flash Chrome; next login resumes.
    if [[ "$CYCLE_PAUSE_NO_SESSION" -gt 0 ]]; then
      log "Sleeping ${CYCLE_PAUSE_NO_SESSION}s then rechecking session..."
      sleep "$CYCLE_PAUSE_NO_SESSION"
      continue
    fi
    log "Exiting until next login / manual restart (session required)."
    exit 0
  fi

  before="$d"
  write_state "harvest"
  cd "$MCP_ROOT"
  "$PYTHON" scripts/territory_persona_harvest.py \
    --accounts "$ACCOUNTS" \
    --output "$OUTPUT" \
    --prefix "$PREFIX" \
    --delay "$DELAY" \
    --delay-jitter "$DELAY_JITTER" \
    --batch-size "$BATCH_SIZE" \
    --batch-pause "$BATCH_PAUSE" \
    --max-per-run "$MAX_PER_RUN" \
    --rate-limit-stop-after "$RATE_LIMIT_STOP" \
    >> "$OUTPUT/${SLUG}_salesnav_harvest.log" 2>&1 || true

  d="$(unique_done)"
  gained=$((d - before))
  log "Batch finished: +$gained (now $d/$TOTAL)"

  if [[ "$d" -ge "$TOTAL" ]]; then
    break
  fi

  # Detect rate-limit / no-progress stalls
  if [[ "$gained" -le 0 ]]; then
    consecutive_no_progress=$((consecutive_no_progress + 1))
    pause="$CYCLE_PAUSE_RATE_LIMIT"
    log "No progress (streak=$consecutive_no_progress). Cooling down ${pause}s..."
  else
    consecutive_no_progress=0
    pause="$CYCLE_PAUSE_OK"
    log "Cooling down ${pause}s before next batch..."
  fi

  # Cap runaway loops: after 8 zero-progress batches, exit for login resume
  if [[ "$consecutive_no_progress" -ge 8 ]]; then
    log "Too many zero-progress batches — exiting (rate limit or session). Resume later."
    write_state "paused_rate_limit"
    exit 0
  fi

  sleep "$pause"
done

log "Harvest complete ($TOTAL unique accounts)."
write_state "export"

"$PYTHON" "$MCP_ROOT/scripts/postprocess_harvest_splits.py" \
  --accounts "$ACCOUNTS" --output "$OUTPUT" --prefix "$PREFIX" \
  >> "$OUTPUT/${SLUG}_salesnav_export.log" 2>&1 || true

"$PYTHON" "$MCP_ROOT/scripts/export_revenue_buckets.py" \
  --output "$OUTPUT" --prefix "$PREFIX" \
  --territory-id "$TERRITORY_ID" \
  --dest "$HOME/Downloads/${TERRITORY_ID}_salesnav_revenue_buckets" \
  >> "$OUTPUT/${SLUG}_salesnav_export.log" 2>&1 || true

date > "$DONE_FILE"
write_state "done"
log "DONE. Buckets -> ~/Downloads/${TERRITORY_ID}_salesnav_revenue_buckets/"
unload_agent
exit 0
