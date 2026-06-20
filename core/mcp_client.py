"""
AuraOS · MCP Client
===================
Calls MCP servers from within the agent.
Each server exposes tools via HTTP — this client
routes tool calls to the right server and returns results.

Servers must be running (started via scripts/start.sh).
If a server is down, the call fails gracefully.
"""
import json
import urllib.request
import urllib.error
from config.settings import settings

# Which server handles which tool
TOOL_ROUTING = {
    # Memory server (8103)
    "get_project_context":      settings.port_memory,
    "get_current_snapshot":     settings.port_memory,
    "save_context_snapshot":    settings.port_memory,
    "search_projects_semantic": settings.port_memory,
    "identify_project":         settings.port_memory,
    "list_goals":               settings.port_memory,
    "add_goal":                 settings.port_memory,
    "get_recent_sessions":      settings.port_memory,
    "start_session":         settings.port_memory,
    "end_session":           settings.port_memory,
    "log_tool_call":         settings.port_memory,
    "complete_tool_call":    settings.port_memory,
    "update_session_plan":   settings.port_memory,
    "touch_project":         settings.port_memory,
    "upsert_project": settings.port_memory,

    # Calendar server (8104)
    "get_today_events":         settings.port_calendar,
    "get_upcoming_deadlines":   settings.port_calendar,
    "get_events_for_range":     settings.port_calendar,

    # GitHub server (8105)
    "list_repos":               settings.port_github,
    "get_open_issues":          settings.port_github,
    "get_open_prs":             settings.port_github,
    "get_recent_commits":       settings.port_github,
    "get_repo_info":            settings.port_github,

    # Filesystem server (8101)
    "get_project_from_registry": settings.port_filesystem,
    "list_registry_projects":    settings.port_filesystem,

    # macOS server (8102)
    "launch_app":               settings.port_macos,
    "open_file_with_app":       settings.port_macos,
    "open_vscode_workspace":    settings.port_macos,
    "send_notification":        settings.port_macos,
}


def call_mcp_tool(tool_name: str, params: dict = None) -> dict:
    port = TOOL_ROUTING.get(tool_name)
    if port is None:
        raise ValueError(f"No MCP server registered for tool '{tool_name}'")

    url = f"http://localhost:{port}/tools/{tool_name}"
    # Wrap params in the expected format
    body = json.dumps({"params": params or {}}).encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except urllib.error.URLError as e:
        raise ConnectionError(
            f"MCP server on port {port} unreachable for tool '{tool_name}'. "
            f"Run scripts/start.sh to start all servers. Error: {e}"
        )


def is_server_running(port: int) -> bool:
    """Check if an MCP server is reachable."""
    try:
        urllib.request.urlopen(f"http://localhost:{port}/health", timeout=2)
        return True
    except Exception:
        return False


def server_status() -> dict:
    """Return running status of all MCP servers."""
    return {
        "filesystem": is_server_running(settings.port_filesystem),
        "macos":      is_server_running(settings.port_macos),
        "memory":     is_server_running(settings.port_memory),
        "calendar":   is_server_running(settings.port_calendar),
        "github":     is_server_running(settings.port_github),
    }

def mcp_start_session(raw_input: str, project_id: str = None, intent: str = None) -> dict:
    """Start a session via the memory server (avoids local SQLite write contention)."""
    return call_mcp_tool("start_session", {
        "raw_input": raw_input, "project_id": project_id, "intent": intent,
    })

def mcp_end_session(session_id: str, status: str = "completed", error: str = None) -> dict:
    return call_mcp_tool("end_session", {
        "session_id": session_id, "status": status, "error": error,
    })

def mcp_log_tool_call(session_id: str, tool_name: str, parameters: dict = None) -> dict:
    return call_mcp_tool("log_tool_call", {
        "session_id": session_id, "tool_name": tool_name, "parameters": parameters or {},
    })

def mcp_complete_tool_call(call_id: str, status: str, result: str = None,
                             duration_ms: int = None, error: str = None) -> dict:
    return call_mcp_tool("complete_tool_call", {
        "call_id": call_id, "status": status, "result": result,
        "duration_ms": duration_ms, "error": error,
    })