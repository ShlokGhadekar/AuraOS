"""
AuraOS · macOS MCP Server
Port: 8102

Exposes: open_app, open_file, open_vscode_workspace, send_notification
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import uvicorn
from mcp.server.fastmcp import FastMCP

from tools.macos_tools import OpenApp, OpenFile, OpenVSCodeWorkspace, SendNotification
from config.settings import settings

mcp = FastMCP("aura-macos", port=settings.port_macos)

open_app   = OpenApp()
open_file  = OpenFile()
open_vscode = OpenVSCodeWorkspace()
notify     = SendNotification()


@mcp.tool()
def launch_app(app_name: str) -> str:
    """
    Launch or focus a macOS application by name.
    Examples: 'Visual Studio Code', 'Terminal', 'Safari', 'Notion'.
    Handles common aliases: 'vscode', 'chrome', 'iterm'.
    """
    result = open_app.execute(app_name=app_name)
    return json.dumps({"success": result.success, "message": result.message, "error": result.error})


@mcp.tool()
def open_file_with_app(path: str, app_name: str = None) -> str:
    """
    Open a file with its default app, or a specified one.
    Use for PDFs, images, markdown notes, Jupyter notebooks, etc.
    """
    kwargs = {"path": path}
    if app_name:
        kwargs["app_name"] = app_name
    result = open_file.execute(**kwargs)
    return json.dumps({"success": result.success, "message": result.message, "error": result.error})


@mcp.tool()
def open_vscode_workspace(path: str, files: list = None, new_window: bool = True) -> str:
    """
    Open a project directory in VS Code.
    Optionally open specific files immediately.
    Always use this (not launch_app) when opening a coding project.
    """
    kwargs = {"path": path, "new_window": new_window}
    if files:
        kwargs["files"] = files
    result = open_vscode.execute(**kwargs)
    return json.dumps({"success": result.success, "message": result.message,
                       "output": result.output, "error": result.error})


@mcp.tool()
def send_notification(title: str, message: str, subtitle: str = "") -> str:
    """
    Send a macOS system notification. Use to signal task completion
    or surface important information to the user.
    """
    result = notify.execute(title=title, message=message, subtitle=subtitle)
    return json.dumps({"success": result.success, "message": result.message, "error": result.error})


if __name__ == "__main__":
    print(f"[macos-server] starting on port {settings.port_macos}")
    mcp.run(transport="sse")
