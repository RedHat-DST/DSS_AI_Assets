#!/usr/bin/env bash
# Run Sales Nav harvest in paced batches until complete, then split + export buckets.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$ROOT/.venv/bin/python"
OUT="$ROOT/output"
ACCOUNTS="$OUT/nl_core_territory2_accounts.json"
TOTAL="$(python3 -c "import json; print(json.load(open('$ACCOUNTS'))['account_count'])")"

# Pause between supervisor cycles when the paced run finishes early.
CYCLE_PAUSE="${CYCLE_PAUSE:-2700}"  # 45 minutes

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

run_salesnav() {
  log "Starting paced Sales Navigator harvest (max 40 accounts per cycle)..."
  cd "$ROOT"
  "$VENV" scripts/territory_persona_harvest.py \
    --delay 6 --delay-jitter 4 \
    --request-delay 2.5 --request-jitter 1.5 \
    --batch-size 20 --batch-pause 600 \
    --max-per-run 40 \
    --rate-limit-stop-after 3 \
    >> "$OUT/harvest_paced.log" 2>&1 || true
}

finalize() {
  log "Post-processing splits and exporting revenue buckets..."
  cd "$ROOT"
  "$VENV" scripts/postprocess_harvest_splits.py >> "$OUT/harvest_paced.log" 2>&1
  "$VENV" scripts/export_revenue_buckets.py >> "$OUT/harvest_paced.log" 2>&1
}

log "Paced harvest supervisor started (target: $TOTAL accounts)"

while true; do
  done="$(salesnav_done)"
  log "Progress: $done/$TOTAL searched"

  if [[ "$done" -ge "$TOTAL" ]]; then
    break
  fi

  run_salesnav
  done="$(salesnav_done)"
  if [[ "$done" -ge "$TOTAL" ]]; then
    break
  fi

  log "Cycle complete. Waiting ${CYCLE_PAUSE}s before next paced batch..."
  sleep "$CYCLE_PAUSE"
done

finalize
log "Harvest complete."
