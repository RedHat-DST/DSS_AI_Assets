#!/usr/bin/env bash
set -euo pipefail

LABEL="com.linkedin.territory-harvest"
PLIST_DST="$HOME/Library/LaunchAgents/com.linkedin.territory-harvest.plist"

launchctl bootout "gui/$(id -u)/$LABEL" 2>/dev/null || true
rm -f "$PLIST_DST"
echo "Removed harvest schedule ($LABEL)"
