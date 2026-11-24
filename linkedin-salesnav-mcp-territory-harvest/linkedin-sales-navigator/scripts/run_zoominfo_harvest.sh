#!/usr/bin/env bash
# Keep ZoomInfo harvest running until all 438 accounts are processed.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUT="$ROOT/output"
TOTAL=438
VENV="$ROOT/.venv/bin/python"

log() { echo "[$(date '+%H:%M:%S')] $*" | tee -a "$OUT/zoominfo_supervisor.log"; }

done_count() {
  python3 -c "
import json
from pathlib import Path
p=Path('$OUT/zoominfo_harvest_progress_v2.json')
print(len(json.load(open(p)).get('done',[])) if p.exists() else 0)
"
}

log "ZoomInfo supervisor started (target: $TOTAL accounts)"

while true; do
  d="$(done_count)"
  log "Progress: $d / $TOTAL"
  if [[ "$d" -ge "$TOTAL" ]]; then
    log "ZoomInfo harvest complete."
    break
  fi
  cd "$ROOT"
  log "Launching harvest batch..."
  "$VENV" scripts/zoominfo_territory_harvest.py --delay 0.6 --max-per-account 5 --batch-size 15 \
    --no-enrich --progress-name zoominfo_harvest_progress_v2.json \
    >> "$OUT/zoominfo_harvest_v2.log" 2>&1 || true
  d="$(done_count)"
  if [[ "$d" -ge "$TOTAL" ]]; then
    log "ZoomInfo harvest complete."
    break
  fi
  log "Batch ended early ($d/$TOTAL). Retrying in 30s..."
  sleep 30
done

log "Supervisor exiting."
