#!/usr/bin/env bash
# One-line harvest status — token-cheap for agents (counts only, no PII dump).
set -euo pipefail
OUT="${1:-$HOME/mcps/linkedin-sales-navigator/output}"
PREFIX="${2:-nl_core_territory2}"
TERR="${3:-NL_COMM_TERR_CORE_POD01_TERR02}"
PYTHON="${SALESNAV_HARVEST_PYTHON:-$HOME/mcps/linkedin-sales-navigator/.venv/bin/python}"
"$PYTHON" - <<PY
import json
from pathlib import Path
out = Path("$OUT")
terr = "$TERR"
prefix = "$PREFIX"
sn_path = out / f"{prefix}_persona_harvest_progress.json"
if not sn_path.exists():
    sn_path = out / "persona_harvest_progress.json"
sn = json.loads(sn_path.read_text()) if sn_path.exists() else {}
done = len(set(sn.get("done") or []))
personas = len(sn.get("personas") or [])
accts = len({p.get("account_name") for p in (sn.get("personas") or [])})
slug = terr.lower().replace("-", "_")
# normalize slug like export
import re
slug = re.sub(r"[^a-z0-9]+", "_", terr.lower()).strip("_")
zi_path = out / f"{slug}_zoominfo_progress.json"
zi = json.loads(zi_path.read_text()) if zi_path.exists() else {}
zi_done = len(set(zi.get("done") or []))
zi_c = len(zi.get("contacts") or [])
state = out / f"{slug}_salesnav_state.json"
phase = json.loads(state.read_text()).get("phase") if state.exists() else "?"
print(f"SN {done}/433 personas={personas} accts={accts} phase={phase} | ZI {zi_done}/433 contacts={zi_c}")
PY
