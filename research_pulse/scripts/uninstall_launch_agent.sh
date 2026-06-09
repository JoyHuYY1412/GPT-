#!/bin/zsh
set -eu

LABEL="com.xinting.research-pulse"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
WRAPPER_DST="$HOME/.research_pulse/run_server.sh"
DOMAIN="gui/$(id -u)"

launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
rm -f "$PLIST_DST"
rm -f "$WRAPPER_DST"

echo "Uninstalled $LABEL"
