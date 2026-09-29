#!/bin/bash
# AuraOS · Start all servers + overlay

PROJECT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$PROJECT/.venv/bin/python"

echo "Starting AuraOS..."

cd "$PROJECT" || exit 1

# Background jobs ignore Ctrl+C in scripts — kill them explicitly on exit,
# otherwise they keep holding their ports and the next start fails.
trap 'kill $(jobs -p) 2>/dev/null' EXIT

"$PYTHON" mcp_servers/filesystem_server.py &
"$PYTHON" mcp_servers/macos_server.py &
"$PYTHON" mcp_servers/memory_server.py &
"$PYTHON" mcp_servers/calendar_server.py &
"$PYTHON" mcp_servers/github_server.py &
"$PYTHON" mcp_servers/browser_server.py &
"$PYTHON" api/main.py &
sleep 2

echo "All servers started. Press Cmd+Shift+Space to activate AuraOS."

# Only one hotkey listener: both the Electron overlay and the legacy
# Textual daemon bind Cmd+Shift+Space, so running both opens two overlays.
if [ -d "$PROJECT/electron-overlay/node_modules" ]; then
    (cd "$PROJECT/electron-overlay" && npm start)
else
    echo "Electron overlay not installed (cd electron-overlay && npm install) — using terminal overlay."
    "$PYTHON" hotkey/daemon.py
fi
