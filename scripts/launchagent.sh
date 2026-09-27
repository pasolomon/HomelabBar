#!/usr/bin/env bash
# Start HomelabBar at login via a per-user LaunchAgent.
#   scripts/launchagent.sh install [path-to-homelabbar]
#   scripts/launchagent.sh uninstall
set -euo pipefail

LABEL="local.homelabbar"
PLIST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG="$HOME/Library/Logs/HomelabBar.log"
DOMAIN="gui/$(id -u)"

case "${1:-}" in
  install)
    exe="${2:-$(command -v homelabbar || true)}"
    [[ -n "$exe" && -x "$exe" ]] || { echo "homelabbar not found; pass its path (e.g. .venv/bin/homelabbar)" >&2; exit 1; }
    exe="$(cd "$(dirname "$exe")" && pwd)/$(basename "$exe")"
    mkdir -p "$(dirname "$PLIST")" "$(dirname "$LOG")"
    cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>$LABEL</string>
  <key>ProgramArguments</key><array><string>$exe</string></array>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><dict><key>SuccessfulExit</key><false/></dict>
  <key>ProcessType</key><string>Interactive</string>
  <key>StandardOutPath</key><string>$LOG</string>
  <key>StandardErrorPath</key><string>$LOG</string>
</dict>
</plist>
EOF
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    launchctl bootstrap "$DOMAIN" "$PLIST"
    echo "installed $PLIST → $exe (log: $LOG)"
    ;;
  uninstall)
    launchctl bootout "$DOMAIN/$LABEL" 2>/dev/null || true
    rm -f "$PLIST"
    echo "removed $LABEL"
    ;;
  *)
    echo "usage: $0 install [path-to-homelabbar] | uninstall" >&2
    exit 2
    ;;
esac
