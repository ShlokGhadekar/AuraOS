"""
AuraOS · macOS MCP Server
Port: 8102
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any

from tools.macos_tools import OpenApp, OpenFile, OpenVSCodeWorkspace, SendNotification
from config.settings import settings

app = FastAPI(title="AuraOS macOS Server")

open_app    = OpenApp()
open_file   = OpenFile()
open_vscode = OpenVSCodeWorkspace()
notify      = SendNotification()


class ToolRequest(BaseModel):
    params: dict[str, Any] = {}


@app.get("/health")
def health():
    return {"status": "ok", "server": "macos"}


@app.post("/tools/launch_app")
def launch_app(req: ToolRequest):
    r = open_app.execute(**req.params)
    return {"success": r.success, "message": r.message, "error": r.error}


@app.post("/tools/open_file_with_app")
def open_file_with_app(req: ToolRequest):
    r = open_file.execute(**req.params)
    return {"success": r.success, "message": r.message, "error": r.error}


@app.post("/tools/open_vscode_workspace")
def open_vscode_workspace(req: ToolRequest):
    r = open_vscode.execute(**req.params)
    return {"success": r.success, "message": r.message, "output": r.output, "error": r.error}


@app.post("/tools/send_notification")
def send_notification(req: ToolRequest):
    r = notify.execute(**req.params)
    return {"success": r.success, "message": r.message, "error": r.error}


if __name__ == "__main__":
    print(f"[macos-server] starting on port {settings.port_macos}")
    uvicorn.run(app, host="127.0.0.1", port=settings.port_macos, log_level="warning")