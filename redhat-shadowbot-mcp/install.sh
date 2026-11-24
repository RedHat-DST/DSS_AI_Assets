#!/usr/bin/env bash
# Optional non-agent installer. Prefer INSTALL_PROMPT.md in Cursor Agent.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
DEST="${HOME}/mcps/shadowbot-assistant"
SKILL_DEST="${HOME}/.cursor/skills/redhat-shadowbot"
MCP_JSON="${HOME}/.cursor/mcp.json"

if [ -f "$ROOT/mcp/mcp_server.py" ]; then
  SRC="$ROOT/mcp"
elif [ -f "$ROOT/mcp_server.py" ]; then
  SRC="$ROOT"
else
  echo "Cannot find mcp_server.py (looked in $ROOT/mcp and $ROOT)." >&2
  exit 1
fi

if [ -d "$ROOT/skills/redhat-shadowbot" ]; then
  SKILL_SRC="$ROOT/skills/redhat-shadowbot"
else
  echo "Cannot find skills/redhat-shadowbot." >&2
  exit 1
fi

PY=""
for candidate in python3.12 /opt/homebrew/bin/python3.12 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    ver="$("$candidate" -c 'import sys; print("%s.%s" % (sys.version_info.major, sys.version_info.minor))')"
    case "$ver" in
      3.11*|3.12*|3.13*) PY="$candidate"; break ;;
    esac
  fi
done

if [ -z "$PY" ]; then
  echo "Need Python 3.11+ (3.12 recommended). macOS /usr/bin/python3 is too old." >&2
  exit 1
fi

echo "Python: $PY"
mkdir -p "$(dirname "$DEST")"
mkdir -p "${HOME}/.cursor/skills"

echo "Installing MCP -> $DEST"
mkdir -p "$DEST"
RSYNC_EXCLUDES=(
  --exclude '.venv'
  --exclude 'session.json'
  --exclude 'profiles'
  --exclude '__pycache__'
  --exclude '.git'
  --exclude 'share'
)
if command -v rsync >/dev/null 2>&1; then
  rsync -a "${RSYNC_EXCLUDES[@]}" "$SRC/" "$DEST/"
else
  cp -R "$SRC/." "$DEST/"
fi

echo "Installing skill -> $SKILL_DEST"
mkdir -p "$SKILL_DEST"
cp -R "$SKILL_SRC/." "$SKILL_DEST/"

cd "$DEST"
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
fi
.venv/bin/pip install -U pip
.venv/bin/pip install -r requirements.txt
.venv/bin/playwright install chromium

export SHADOWBOT_MCP_JSON="$MCP_JSON"
export SHADOWBOT_PYTHON="$DEST/.venv/bin/python"
export SHADOWBOT_SERVER="$DEST/mcp_server.py"

"$PY" - <<'PY'
import json
import os
from pathlib import Path

mcp_path = Path(os.environ["SHADOWBOT_MCP_JSON"])
mcp_path.parent.mkdir(parents=True, exist_ok=True)
data = {"mcpServers": {}}
if mcp_path.exists():
    try:
        data = json.loads(mcp_path.read_text(encoding="utf-8"))
    except Exception:
        data = {"mcpServers": {}}
data.setdefault("mcpServers", {})
data["mcpServers"]["shadowbot-assistant"] = {
    "command": os.environ["SHADOWBOT_PYTHON"],
    "args": [os.environ["SHADOWBOT_SERVER"]],
}
mcp_path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
print("Updated", mcp_path)
PY

echo
echo "Done."
echo "1. Reload MCP in Cursor Settings → MCP"
echo "2. New chat: Log me into Shadowbot (agent calls shadowbot_auth)"
echo "3. Sign in with your Red Hat associate account + FreeOTP in Chrome."
echo "   Do not paste your password or OTP into chat."
