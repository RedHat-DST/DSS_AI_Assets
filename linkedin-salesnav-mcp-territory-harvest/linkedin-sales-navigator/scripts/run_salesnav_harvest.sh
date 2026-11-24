#!/usr/bin/env bash
# Keep Sales Navigator harvest running until all 438 accounts are processed.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/output"
TOTAL=438
VENV="$ROOT/.venv/bin/python"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$OUT/salesnav_supervisor.log"; }

done_count() {
  python3 -c "
import json
from pathlib import Path
p=Path('$OUT/persona_harvest_progress.json')
print(len(json.load(open(p)).get('done',[])) if p.exists() else 0)
"
}

log "Sales Navigator supervisor started (target: $TOTAL accounts)"

while true; do
  d="$(done_count)"
  log "Progress: $d / $TOTAL"
  if [[ "$d" -ge "$TOTAL" ]]; then
    log "Sales Navigator harvest complete."
    break
  fi
  cd "$ROOT"
  log "Launching harvest batch..."
  "$VENV" scripts/territory_persona_harvest.py --delay 3.5 \
    >> "$OUT/harvest_resume.log" 2>&1 || true
  d="$(done_count)"
  if [[ "$d" -ge "$TOTAL" ]]; then
    log "Sales Navigator harvest complete."
    break
  fi
  log "Batch ended ($d/$TOTAL). Waiting 5 min for rate limits..."
  sleep 300
done

log "Re-exporting merged contacts..."
"$VENV" scripts/export_final_contacts.py >> "$OUT/export.log" 2>&1 || true
log "Done."
