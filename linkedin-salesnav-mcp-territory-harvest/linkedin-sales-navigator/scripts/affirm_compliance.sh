#!/usr/bin/env bash
# One-time / refresh AE affirmation for harvest compliance gate.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AFFIRM_FILE="${AE_GTM_COMPLIANCE_AFFIRM:-$HOME/.cursor/ae-gtm-compliance-affirmation.json}"
mkdir -p "$(dirname "$AFFIRM_FILE")"

# Privacy Mode only (skip affirm file — we are creating it)
AE_GTM_REQUIRE_AFFIRM=0 bash "$ROOT/check_compliance_gate.sh"

python3 - <<PY
import json
from datetime import datetime, timezone
from pathlib import Path
p = Path("$AFFIRM_FILE")
payload = {
    "privacy_mode_on": True,
    "regional_allowed": True,
    "drafts_only": True,
    "affirmed_at": datetime.now(timezone.utc).isoformat(),
    "max_age_days": 180,
    "note": "AE affirms Privacy Mode ON, territory/Works Council use allowed, drafts only (agent never auto-sends).",
}
p.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
print(f"Wrote {p}")
PY

bash "$ROOT/check_compliance_gate.sh"
echo "Compliance affirmation saved. Harvests may proceed."
