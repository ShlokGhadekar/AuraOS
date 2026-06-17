# #!/bin/bash
# # AuraOS · Start all servers + hotkey daemon

# PROJECT="/Users/shlokghadekar/Documents/Projects and stuff/auraos"
# PYTHON="$PROJECT/.venv/bin/python"

# echo "Starting AuraOS..."

# cd "$PROJECT"

# # Start MCP servers in background
# $PYTHON mcp_servers/filesystem_server.py &
# $PYTHON mcp_servers/macos_server.py &
# $PYTHON mcp_servers/memory_server.py &
# $PYTHON mcp_servers/calendar_server.py &
# $PYTHON mcp_servers/github_server.py &

# # Give servers 2 seconds to start
# sleep 2

# # Start hotkey daemon (foreground so Ctrl+C kills everything)
# echo "All servers started. Press Cmd+Shift+Space to activate AuraOS."
# $PYTHON hotkey/daemon.py
#!/bin/bash

PROJECT="/Users/shlokghadekar/Documents/Projects and stuff/auraos"
PYTHON="$PROJECT/.venv/bin/python"

echo "Starting AuraOS..."

cd "$PROJECT" || exit 1

"$PYTHON" mcp_servers/filesystem_server.py &
"$PYTHON" mcp_servers/macos_server.py &
"$PYTHON" mcp_servers/memory_server.py &
"$PYTHON" mcp_servers/calendar_server.py &
"$PYTHON" mcp_servers/github_server.py &

sleep 2

echo "All servers started. Press Cmd+Shift+Space to activate AuraOS."

"$PYTHON" hotkey/daemon.py