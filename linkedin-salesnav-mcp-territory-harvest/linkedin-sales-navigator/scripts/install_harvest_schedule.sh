#!/usr/bin/env bash
# Install weekday work-hours harvest schedule (macOS launchd).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLIST_SRC="$ROOT/scripts/com.linkedin.territory-harvest.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.linkedin.territory-harvest.plist"
LABEL="com.linkedin.territory-harvest"

chmod +x "$ROOT/scripts/scheduled_harvest.sh"

mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"

# Reload if already loaded
launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
launchctl bootstrap "gui/$(id -u)" "$PLIST_DST"

echo "Installed: $PLIST_DST"
echo "Schedule: Mon–Fri at 09:30, 11:00, 13:00, 15:00 (local time)"
echo "Log: $ROOT/output/scheduled_harvest.log"
echo ""
echo "Before each slot: sign in to Sales Nav in MCP Chrome (port 9222)."
echo "Uninstall: $ROOT/scripts/uninstall_harvest_schedule.sh"
