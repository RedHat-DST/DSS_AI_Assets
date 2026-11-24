#!/usr/bin/env bash
# Preflight checks — exit non-zero if harvest would stall or fail immediately.
set -euo pipefail

SKILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MCP_ROOT="${SALESNAV_MCP_ROOT:-$HOME/mcps/linkedin-sales-navigator}"
ACCOUNTS=""
OUTPUT=""
STRICT_SESSION=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --accounts) ACCOUNTS="$2"; shift 2 ;;
    --output) OUTPUT="$2"; shift 2 ;;
    --mcp-root) MCP_ROOT="$2"; shift 2 ;;
    --require-session) STRICT_SESSION=1; shift ;;
    *) echo "Unknown arg: $1" >&2; exit 1 ;;
  esac
done

FAIL=0
warn() { echo "WARN: $*" >&2; }
fail() { echo "FAIL: $*" >&2; FAIL=1; }
ok() { echo "OK: $*"; }

echo "=== Sales Nav territory harvest — preflight ==="

# 0. Compliance gate (Privacy Mode + AE affirmation) — hard stop
COMPLIANCE_GATE="${MCP_ROOT}/scripts/check_compliance_gate.sh"
if [[ ! -x "$COMPLIANCE_GATE" ]]; then
  chmod +x "$COMPLIANCE_GATE" 2>/dev/null || true
fi
if [[ -f "$COMPLIANCE_GATE" ]]; then
  if ! bash "$COMPLIANCE_GATE"; then
    fail "Compliance gate failed — harvest blocked"
    echo "=== PREFLIGHT FAILED ==="
    exit 1
  fi
  ok "Compliance gate"
else
  fail "Missing $COMPLIANCE_GATE"
fi

# 1. MCP project
if [[ ! -d "$MCP_ROOT" ]]; then
  fail "MCP root missing: $MCP_ROOT (run install.sh)"
else
  ok "MCP root $MCP_ROOT"
fi

PYTHON="$MCP_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  fail "Python venv missing: $PYTHON"
else
  ok "Python $PYTHON"
fi

for f in mcp_server.py scripts/territory_persona_harvest.py scripts/postprocess_harvest_splits.py scripts/export_revenue_buckets.py src/harvest_pacing.py; do
  if [[ ! -f "$MCP_ROOT/$f" ]]; then
    fail "Missing $MCP_ROOT/$f"
  fi
done
ok "Harvest scripts present"

# 2. Shared MCP Chrome helper
if [[ ! -f "$HOME/mcps/mcp-chrome/shared.py" ]]; then
  fail "Shared MCP Chrome missing: ~/mcps/mcp-chrome/shared.py"
else
  ok "mcp-chrome shared.py"
fi

# 3. Accounts JSON
if [[ -n "$ACCOUNTS" ]]; then
  if [[ ! -f "$ACCOUNTS" ]]; then
    fail "Accounts file not found: $ACCOUNTS"
  else
    "$PYTHON" - <<PY
import json, sys
from pathlib import Path
p = Path("$ACCOUNTS")
data = json.loads(p.read_text())
accounts = data.get("accounts") or []
names = {(a.get("account_name") or a.get("Name") or "").strip() for a in accounts}
names.discard("")
enriched = sum(1 for a in accounts if a.get("has_revenue") is not None or a.get("sales_group") is not None)
print(f"accounts_rows={len(accounts)} unique_names={len(names)} enriched={enriched}")
if not names:
    sys.exit(2)
if enriched == 0:
    print("WARN_NO_RHSC_ENRICHMENT", file=sys.stderr)
PY
    rc=$?
    if [[ $rc -eq 2 ]]; then
      fail "Accounts JSON has no usable account names"
    else
      ok "Accounts JSON readable"
    fi
  fi
fi

# 4. CDP / session (non-fatal unless --require-session)
set +e
"$PYTHON" - <<PY
import asyncio, sys
sys.path.insert(0, "$MCP_ROOT")
from src.chrome import cdp_alive, has_sales_nav_session
from src.config import load_config

cfg = load_config()
port = cfg.cdp_port
alive = cdp_alive(port)
print(f"cdp_port={port} alive={alive}")
if not alive:
    sys.exit(3)

async def check():
    from src.auth import get_auth
    auth = get_auth()
    try:
        session = await auth.probe_saved_session()
    except Exception as e:
        print(f"session_probe_error={e}")
        return False
    if not session:
        print("session=none")
        return False
    cookies = session.get("cookies") or {}
    ok = has_sales_nav_session(cookies)
    print(f"has_li_at={'li_at' in cookies} has_li_a={'li_a' in cookies} sales_nav_session={ok}")
    return ok

try:
    ok = asyncio.run(check())
except Exception as e:
    print(f"session_check_failed={e}")
    sys.exit(3)
sys.exit(0 if ok else 4)
PY
sess_rc=$?
set -e
if [[ $sess_rc -eq 0 ]]; then
  ok "Sales Nav session valid"
elif [[ $sess_rc -eq 3 ]]; then
  warn "MCP Chrome CDP not up yet — will start on first harvest / salesnav_auth"
  [[ "$STRICT_SESSION" -eq 1 ]] && fail "CDP required (--require-session)"
elif [[ $sess_rc -eq 4 ]]; then
  warn "Not signed into Sales Navigator — sign in before harvest batches will work"
  [[ "$STRICT_SESSION" -eq 1 ]] && fail "Sales Nav session required"
else
  warn "Session check returned $sess_rc"
fi

# 5. Output dir
if [[ -n "$OUTPUT" ]]; then
  mkdir -p "$OUTPUT"
  ok "Output dir $OUTPUT"
fi

# 6. No conflicting long sleep supervisor
if pgrep -fl 'run_paced_harvest|run_salesnav_harvest' >/dev/null 2>&1; then
  warn "Legacy supervisor process found — prefer skill run_loop / login agent only"
fi

if [[ "$FAIL" -ne 0 ]]; then
  echo "=== PREFLIGHT FAILED ==="
  exit 1
fi
echo "=== PREFLIGHT PASSED ==="
exit 0
