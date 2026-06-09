#!/bin/zsh
set -eu

LABEL="com.xinting.research-pulse"
APP_DIR="/Users/xintinghu/Library/CloudStorage/OneDrive-个人/USTC work/Xinting苦B带学生发bestpaper/Xinting_projects/论文推送/research_pulse"
PLIST_SRC="$APP_DIR/launchd/$LABEL.plist"
PLIST_DST="$HOME/Library/LaunchAgents/$LABEL.plist"
WRAPPER_SRC="$APP_DIR/launchd/run_server_wrapper.sh"
WRAPPER_DST="$HOME/.research_pulse/run_server.sh"
DOMAIN="gui/$(id -u)"

mkdir -p "$HOME/Library/LaunchAgents"
mkdir -p "$HOME/.research_pulse"
cp "$WRAPPER_SRC" "$WRAPPER_DST"
chmod 755 "$WRAPPER_DST"
cp "$PLIST_SRC" "$PLIST_DST"
chmod 644 "$PLIST_DST"
xattr -d com.apple.quarantine "$WRAPPER_DST" "$PLIST_DST" 2>/dev/null || true

launchctl bootout "$DOMAIN" "$PLIST_DST" 2>/dev/null || true
launchctl bootstrap "$DOMAIN" "$PLIST_DST"
launchctl enable "$DOMAIN/$LABEL"
launchctl kickstart -k "$DOMAIN/$LABEL"

echo "Installed and started $LABEL"
echo "Website: http://127.0.0.1:8766"
echo "Logs:"
echo "  $HOME/.research_pulse/server.out.log"
echo "  $HOME/.research_pulse/server.err.log"
