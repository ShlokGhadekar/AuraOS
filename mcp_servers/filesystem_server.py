"""
AuraOS · Filesystem MCP Server
Port: 8101
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import yaml
import uvicorn
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from typing import Any

from tools.filesystem_tools import DetectProject, ListRecentFiles, ListProjects
from memory.episodic import EpisodicMemory
from config.settings import settings

app = FastAPI(title="AuraOS Filesystem Server")
mem = EpisodicMemory(settings.db_path)

detect  = DetectProject()
recent  = ListRecentFiles()
lsproj  = ListProjects()


class ToolRequest(BaseModel):
    params: dict[str, Any] = {}


def _load_yaml_projects() -> list[dict]:
    path = settings.projects_yaml
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("projects", [])


def _sync_projects_to_db():
    for p in _load_yaml_projects():
        mem.upsert_project(
            id=p["id"],
            name=p["name"],
            path=p["path"],
            description=p.get("description"),
            github_repo=p.get("github_repo"),
            tags=p.get("tags", []),
        )


@app.get("/health")
def health():
    return {"status": "ok", "server": "filesystem"}


@app.post("/tools/detect_project")
def detect_project(req: ToolRequest):
    r = detect.execute(**req.params)
    return {"success": r.success, "output": r.output, "error": r.error, "message": r.message}


@app.post("/tools/list_recent_files")
def list_recent_files(req: ToolRequest):
    r = recent.execute(**req.params)
    return {"success": r.success, "output": r.output, "error": r.error}


@app.post("/tools/list_projects")
def list_projects(req: ToolRequest):
    r = lsproj.execute(**req.params)
    return {"success": r.success, "output": r.output, "error": r.error}


@app.post("/tools/get_project_from_registry")
def get_project_from_registry(req: ToolRequest):
    project_id = req.params.get("project_id")
    project = mem.get_project(project_id)
    if not project:
        return {"success": False, "error": f"Project '{project_id}' not in registry"}
    from dataclasses import asdict
    return {"success": True, "output": asdict(project)}


@app.post("/tools/list_registry_projects")
def list_registry_projects(req: ToolRequest):
    projects = mem.list_projects()
    from dataclasses import asdict
    return {"success": True, "output": [asdict(p) for p in projects]}


if __name__ == "__main__":
    _sync_projects_to_db()
    print(f"[filesystem-server] starting on port {settings.port_filesystem}")
    uvicorn.run(app, host="127.0.0.1", port=settings.port_filesystem, log_level="warning")