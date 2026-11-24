#!/usr/bin/env bash
# Automatic AE GTM compliance gate — run before Sales Nav / ZoomInfo harvest.
# Hard-fails if Cursor Privacy Mode is OFF. Optional regional/drafts affirmation file.
set -euo pipefail

AFFIRM_FILE="${AE_GTM_COMPLIANCE_AFFIRM:-$HOME/.cursor/ae-gtm-compliance-affirmation.json}"
STATE_DB="${CURSOR_STATE_VSCDB:-$HOME/Library/Application Support/Cursor/User/globalStorage/state.vscdb}"
REQUIRE_AFFIRM="${AE_GTM_REQUIRE_AFFIRM:-1}"
PYTHON="${AE_GTM_COMPLIANCE_PYTHON:-python3}"

fail() { echo "FAIL compliance: $*" >&2; exit 2; }
ok() { echo "OK compliance: $*"; }

if [[ ! -f "$STATE_DB" ]]; then
  fail "Cursor state DB missing ($STATE_DB) — cannot verify Privacy Mode"
fi

"$PYTHON" - <<'PY' || exit 2
import json, sqlite3, sys
from pathlib import Path

db = Path.home() / "Library/Application Support/Cursor/User/globalStorage/state.vscdb"
con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
cur = con.cursor()

def get(key: str):
    row = cur.execute("SELECT value FROM ItemTable WHERE key=?", (key,)).fetchone()
    if not row:
        return None
    val = row[0]
    if isinstance(val, bytes):
        val = val.decode("utf-8", errors="replace")
    return val

legacy = get("cursorai/donotchange/privacyMode")
mode2_raw = get("cursorai/donotchange/newPrivacyMode2")
mode2 = None
if mode2_raw:
    try:
        mode2 = json.loads(mode2_raw)
    except Exception:
        mode2 = {"raw": mode2_raw}

# ON signals used by Cursor Privacy Mode
on_tokens = {
    "true",
    "1",
    "PRIVACY_MODE_NO_STORAGE",
    "PRIVACY_MODE_NO_TRAINING",
    "NO_STORAGE",
    "ENABLED",
    "ON",
}
off_tokens = {
    "false",
    "0",
    "PRIVACY_MODE_DISABLED",
    "PRIVACY_MODE_OFF",
    "DISABLED",
    "OFF",
    "ALLOW_STORAGE",
    "PRIVACY_MODE_USAGE_DATA",  # treat usage-data / non-privacy as not OK for AE GTM
}

legacy_s = str(legacy).strip().lower() if legacy is not None else ""
mode2_s = ""
if isinstance(mode2, dict):
    mode2_s = str(mode2.get("privacyMode") or mode2.get("raw") or "").strip()

mode2_u = mode2_s.upper()
legacy_on = legacy_s in {"true", "1", "yes"}
legacy_off = legacy_s in {"false", "0", "no"}
mode2_on = mode2_u in on_tokens or mode2_u.replace("PRIVACY_MODE_", "") in {"NO_STORAGE", "NO_TRAINING"}
mode2_off = mode2_u in off_tokens or "DISABLED" in mode2_u or mode2_u.endswith("_OFF")

if mode2_off or legacy_off:
    print(
        f"FAIL: Cursor Privacy Mode is OFF "
        f"(privacyMode={legacy!r}, newPrivacyMode2={mode2_s!r}). "
        f"Turn Privacy Mode ON in Cursor Settings, then retry harvest.",
        file=sys.stderr,
    )
    sys.exit(2)

if not (legacy_on or mode2_on):
    print(
        f"FAIL: Could not confirm Privacy Mode ON "
        f"(privacyMode={legacy!r}, newPrivacyMode2={mode2_s!r}). "
        f"Turn Privacy Mode ON in Cursor Settings, then retry harvest.",
        file=sys.stderr,
    )
    sys.exit(2)

print(f"OK: Privacy Mode ON (legacy={legacy_s or 'n/a'}, mode2={mode2_s or 'n/a'})")
con.close()
PY

if [[ "$REQUIRE_AFFIRM" == "1" ]]; then
  if [[ ! -f "$AFFIRM_FILE" ]]; then
    fail "missing affirmation file $AFFIRM_FILE — run: bash ~/mcps/linkedin-sales-navigator/scripts/affirm_compliance.sh"
  fi
  "$PYTHON" - <<PY || exit 2
import json, sys
from pathlib import Path
from datetime import datetime, timezone
p = Path("$AFFIRM_FILE")
data = json.loads(p.read_text())
need = ("privacy_mode_on", "regional_allowed", "drafts_only")
missing = [k for k in need if not data.get(k)]
if missing:
    print(f"FAIL: affirmation incomplete, missing true flags: {missing}", file=sys.stderr)
    sys.exit(2)
# optional expiry (default 180 days)
max_days = int(data.get("max_age_days") or 180)
affirmed = data.get("affirmed_at") or ""
try:
    # accept Z or +00:00
    ts = datetime.fromisoformat(affirmed.replace("Z", "+00:00"))
    age = (datetime.now(timezone.utc) - ts.astimezone(timezone.utc)).days
    if age > max_days:
        print(f"FAIL: affirmation expired ({age}d > {max_days}d) — re-run affirm_compliance.sh", file=sys.stderr)
        sys.exit(2)
except Exception:
    print("FAIL: affirmation has invalid affirmed_at — re-run affirm_compliance.sh", file=sys.stderr)
    sys.exit(2)
print(f"OK: AE affirmation present (regional+drafts, age_days≈{age})")
PY
fi

ok "harvest compliance gate passed"
exit 0
