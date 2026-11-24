#!/usr/bin/env bash
# Turnkey installer: Sales Nav territory harvest skill + MCP wiring checks.
# Safe to re-run. Does not copy LinkedIn cookies.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEST="${SKILLS_DIR:-$HOME/.cursor/skills}/salesnav-territory-harvest"
MCP_ROOT="${SALESNAV_MCP_ROOT:-$HOME/mcps/linkedin-sales-navigator}"
MCP_CHROME="${MCP_CHROME_ROOT:-$HOME/mcps/mcp-chrome}"
CURSOR_MCP="${CURSOR_MCP:-$HOME/.cursor/mcp.json}"

echo "=============================================="
echo " Sales Nav Territory Harvest — turnkey install"
echo "=============================================="
echo "  Package: $SCRIPT_DIR"
echo "  Skill:   $DEST"
echo "  MCP:     $MCP_ROOT"
echo ""

# ---- 1. Skill files ----
mkdir -p "$DEST/scripts"
cp "$SCRIPT_DIR/SKILL.md" "$DEST/SKILL.md"
[[ -f "$SCRIPT_DIR/README.md" ]] && cp "$SCRIPT_DIR/README.md" "$DEST/README.md"
[[ -f "$SCRIPT_DIR/TURNKEY-PROMPT.md" ]] && cp "$SCRIPT_DIR/TURNKEY-PROMPT.md" "$DEST/TURNKEY-PROMPT.md"
[[ -f "$SCRIPT_DIR/SHARE.md" ]] && cp "$SCRIPT_DIR/SHARE.md" "$DEST/SHARE.md"
[[ -f "$SCRIPT_DIR/reference.md" ]] && cp "$SCRIPT_DIR/reference.md" "$DEST/reference.md"
cp "$SCRIPT_DIR/scripts/"*.sh "$DEST/scripts/" 2>/dev/null || true
cp "$SCRIPT_DIR/install.sh" "$DEST/install.sh"
chmod +x "$DEST/scripts/"*.sh "$DEST/install.sh" 2>/dev/null || true
echo "[1/5] Skill files -> $DEST"

# ---- 2. MCP project ----
if [[ ! -d "$MCP_ROOT" ]]; then
  echo "[2/5] ERROR: Sales Nav MCP not found at $MCP_ROOT"
  echo "       Clone/install linkedin-sales-navigator under ~/mcps/ first."
  exit 1
fi
if [[ ! -x "$MCP_ROOT/.venv/bin/python" ]]; then
  echo "[2/5] Creating MCP venv..."
  python3 -m venv "$MCP_ROOT/.venv"
  "$MCP_ROOT/.venv/bin/pip" install --upgrade pip >/dev/null
  if [[ -f "$MCP_ROOT/requirements.txt" ]]; then
    "$MCP_ROOT/.venv/bin/pip" install -r "$MCP_ROOT/requirements.txt" >/dev/null
  fi
  "$MCP_ROOT/.venv/bin/playwright" install chromium >/dev/null 2>&1 || true
fi
echo "[2/5] MCP project OK ($MCP_ROOT/.venv/bin/python)"

# ---- 3. Shared MCP Chrome ----
if [[ ! -f "$MCP_CHROME/shared.py" ]]; then
  echo "[3/5] WARN: ~/mcps/mcp-chrome/shared.py missing — CDP auth may fail"
else
  echo "[3/5] mcp-chrome OK"
fi

# ---- 4. Wire ~/.cursor/mcp.json ----
python3 - <<PY
import json
from pathlib import Path
mcp_path = Path("$CURSOR_MCP")
root = Path("$MCP_ROOT")
entry = {
    "command": str(root / ".venv" / "bin" / "python"),
    "args": [str(root / "mcp_server.py")],
    "env": {
        "SALESNAV_CDP_PORT": "9222",
        "SALESNAV_SALES_URL": "https://www.linkedin.com/sales/homepage",
        "MCP_CHROME_CDP_PORT": "9222",
    },
}
if mcp_path.exists():
    data = json.loads(mcp_path.read_text())
else:
    data = {"mcpServers": {}}
data.setdefault("mcpServers", {})["linkedin-sales-navigator"] = entry
# Keep user-* alias if Cursor auto-prefixes
mcp_path.parent.mkdir(parents=True, exist_ok=True)
mcp_path.write_text(json.dumps(data, indent=2) + "\n")
print(f"[4/5] mcp.json linkedin-sales-navigator -> {mcp_path}")
PY

# ---- 5. Cross-link MCP skill + smoke ----
LS_SKILL="${SKILLS_DIR:-$HOME/.cursor/skills}/linkedin-sales-navigator"
mkdir -p "$LS_SKILL"
if [[ ! -f "$LS_SKILL/SKILL.md" ]]; then
  cat > "$LS_SKILL/SKILL.md" <<'EOF'
---
name: linkedin-sales-navigator
description: >-
  Query LinkedIn Sales Navigator via MCP. For territory Cloud/CCSP harvests use
  salesnav-territory-harvest.
---
# LinkedIn Sales Navigator MCP
Use salesnav_* tools. For bulk territory harvest see **salesnav-territory-harvest**.
EOF
fi
if ! grep -q "salesnav-territory-harvest" "$LS_SKILL/SKILL.md" 2>/dev/null; then
  cat >> "$LS_SKILL/SKILL.md" <<'EOF'

## Territory Cloud/CCSP harvest
Use skill **salesnav-territory-harvest** (`~/.cursor/skills/salesnav-territory-harvest/SKILL.md`).
EOF
fi
echo "[5/5] Cross-linked linkedin-sales-navigator skill"

mkdir -p "$HOME/mcps/salesnav-territory-harvest/output"
echo "       Output dir: $HOME/mcps/salesnav-territory-harvest/output"

"$MCP_ROOT/.venv/bin/python" -c "import playwright; print('       playwright import OK')" 2>/dev/null \
  || echo "       WARN: playwright import failed — run: $MCP_ROOT/.venv/bin/playwright install chromium"

echo ""
echo "=============================================="
echo " INSTALL COMPLETE"
echo "=============================================="
echo ""
echo "Next:"
echo "  1. Reload MCP servers / restart Cursor"
echo "  2. salesnav_auth → sign in at linkedin.com/sales in MCP Chrome"
echo "  3. salesnav_whoami must show authenticated"
echo "  4. Start harvest:"
echo ""
echo "     $DEST/scripts/install_login_agent.sh \\"
echo "       --accounts /path/to/accounts.json \\"
echo "       --output \$HOME/mcps/salesnav-territory-harvest/output \\"
echo "       --territory-id YOUR_TERR_ID \\"
echo "       --prefix your_prefix"
echo ""
echo "Separate from ZoomInfo — use zoominfo-territory-harvest for ZoomInfo only."
echo ""
