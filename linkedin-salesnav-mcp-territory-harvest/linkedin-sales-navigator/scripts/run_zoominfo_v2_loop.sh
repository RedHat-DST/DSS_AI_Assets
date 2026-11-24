#!/usr/bin/env bash
# Resume ZoomInfo v2 territory harvest until complete; safe to run on login.
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

LOCK_FILE="$ROOT/output/zoominfo_v2_loop.pid"
LOG_FILE="$ROOT/output/zoominfo_v2_loop.log"
TOTAL=438

log() { echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"; }

done_count() {
  python3 -c "
import json
from pathlib import Path
p = Path('output/zoominfo_harvest_progress_v2.json')
print(len(json.load(open(p)).get('done', [])) if p.exists() else 0)
"
}

contact_count() {
  python3 -c "
import json
from pathlib import Path
p = Path('output/zoominfo_harvest_progress_v2.json')
print(len(json.load(open(p)).get('contacts', [])) if p.exists() else 0)
"
}

if [[ -f "$LOCK_FILE" ]]; then
  old_pid="$(cat "$LOCK_FILE" 2>/dev/null || true)"
  if [[ -n "$old_pid" ]] && kill -0 "$old_pid" 2>/dev/null; then
    log "Already running (pid $old_pid), exiting."
    exit 0
  fi
fi

echo $$ > "$LOCK_FILE"
trap 'rm -f "$LOCK_FILE"' EXIT

d="$(done_count)"
if [[ "$d" -ge "$TOTAL" ]]; then
  log "Harvest already complete ($d/$TOTAL). Running export if needed."
  .venv/bin/python scripts/export_final_contacts.py >> output/export.log 2>&1 || true
  exit 0
fi

log "Starting ZoomInfo v2 harvest loop from $d/$TOTAL (pid $$)"

while true; do
  d="$(done_count)"
  c="$(contact_count)"
  log "Progress: $d/$TOTAL contacts=$c"
  if [[ "$d" -ge "$TOTAL" ]]; then
    .venv/bin/python scripts/export_final_contacts.py >> output/export.log 2>&1 || true
    log "Harvest complete. Export written to Downloads."
    exit 0
  fi
  .venv/bin/python scripts/zoominfo_territory_harvest.py \
    --delay 0.6 --max-per-account 5 --batch-size 15 --no-enrich \
    --progress-name zoominfo_harvest_progress_v2.json \
    >> output/zoominfo_harvest_v2.log 2>&1 || true
  sleep 5
done
