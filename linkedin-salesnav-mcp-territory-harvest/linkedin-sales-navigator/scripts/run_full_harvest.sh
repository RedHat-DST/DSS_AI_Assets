#!/usr/bin/env bash
# Run Sales Nav + ZoomInfo harvests to completion, then export to Downloads.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv/bin/python"
OUT="$ROOT/output"
ACCOUNTS="$OUT/nl_comm_terr_core_pod01_terr02_accounts.json"
TOTAL="$(python3 -c "import json; print(json.load(open('$ACCOUNTS'))['account_count'])")"
CYCLE_PAUSE="${CYCLE_PAUSE:-2700}"

log() { echo "[$(date '+%H:%M:%S')] $*"; }

salesnav_done() {
  python3 -c "
import json
from pathlib import Path
p=Path('$OUT/persona_harvest_progress.json')
if not p.exists(): print(0); raise SystemExit
d=json.load(open(p))
print(len(d.get('done',[])))
"
}

zoominfo_done() {
  python3 -c "
import json
from pathlib import Path
p=Path('$OUT/zoominfo_harvest_progress.json')
if not p.exists(): print(0); raise SystemExit
d=json.load(open(p))
print(len(d.get('done',[])))
"
}

run_salesnav() {
  log "Starting paced Sales Navigator harvest..."
  cd "$ROOT"
  "$VENV" scripts/territory_persona_harvest.py \
    --delay 6 --delay-jitter 4 \
    --batch-size 20 --batch-pause 600 \
    --max-per-run 40 \
    --rate-limit-stop-after 3 \
    >> "$OUT/harvest_resume.log" 2>&1 || true
}

run_zoominfo() {
  log "Starting ZoomInfo harvest..."
  cd "$ROOT"
  "$VENV" scripts/zoominfo_territory_harvest.py --delay 0.6 --max-per-account 5 --no-enrich \
    >> "$OUT/zoominfo_harvest.log" 2>&1 || true
}

export_results() {
  log "Exporting merged contact list to Downloads..."
  cd "$ROOT"
  "$VENV" scripts/postprocess_harvest_splits.py >> "$OUT/export.log" 2>&1
  "$VENV" scripts/export_revenue_buckets.py >> "$OUT/export.log" 2>&1
  "$VENV" scripts/export_final_contacts.py >> "$OUT/export.log" 2>&1
  cp "$OUT/nl_comm_terr_core_pod01_terr02_accounts.csv" \
    "$HOME/Downloads/NL_COMM_TERR_CORE_POD01_TERR02_accounts.csv" 2>/dev/null || true
  log "Export complete."
}

log "Territory harvest supervisor started (target: $TOTAL accounts)"

while true; do
  sd="$(salesnav_done)"
  zd="$(zoominfo_done)"
  log "Progress: SalesNav $sd/$TOTAL | ZoomInfo $zd/$TOTAL"

  if [[ "$sd" -lt "$TOTAL" ]]; then
    run_salesnav
    sd="$(salesnav_done)"
  fi

  if [[ "$zd" -lt "$TOTAL" ]]; then
    run_zoominfo
    zd="$(zoominfo_done)"
  fi

  sd="$(salesnav_done)"
  zd="$(zoominfo_done)"
  if [[ "$sd" -ge "$TOTAL" && "$zd" -ge "$TOTAL" ]]; then
    break
  fi

  log "Waiting ${CYCLE_PAUSE}s before next paced cycle..."
  sleep "$CYCLE_PAUSE"
done

export_results
log "All done."
