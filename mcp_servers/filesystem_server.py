"""
AuraOS · Filesystem MCP Server
Port: 8101

Exposes: detect_project, list_recent_files, list_projects
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import yaml
import uvicorn
from mcp.server.fastmcp import FastMCP

from tools.filesystem_tools import DetectProject, ListRecentFiles, ListProjects
from memory.episodic import EpisodicMemory
from config.settings import settings

mcp = FastMCP("aura-filesystem", port=settings.port_filesystem)
mem = EpisodicMemory(settings.db_path)

detect   = DetectProject()
recent   = ListRecentFiles()
lsproj   = ListProjects()


def _load_yaml_projects() -> list[dict]:
    path = settings.projects_yaml
    if not path.exists():
        return []
    with open(path) as f:
        data = yaml.safe_load(f)
    return data.get("projects", [])


def _sync_projects_to_db():
    """Sync projects.yaml → SQLite on server start."""
    for p in _load_yaml_projects():
        mem.upsert_project(
            id=p["id"],
            name=p["name"],
            path=p["path"],
            description=p.get("description"),
            github_repo=p.get("github_repo"),
            tags=p.get("tags", []),
        )


@mcp.tool()
def detect_project(name_or_path: str, search_root: str = None) -> str:
    """
    Detect a project by name or path. Returns type, structure,
    recent files, and git info. Call this first when the user
    mentions a project by name.
    """
    kwargs = {"name_or_path": name_or_path}
    if search_root:
        kwargs["search_root"] = search_root
    result = detect.execute(**kwargs)
    return json.dumps({"success": result.success, "output": result.output, "error": result.error})


@mcp.tool()
def list_recent_files(path: str, n: int = 10) -> str:
    """
    List the most recently modified files in a project directory.
    """
    result = recent.execute(path=path, n=n)
    return json.dumps({"success": result.success, "output": result.output, "error": result.error})


@mcp.tool()
def list_projects(search_root: str = None) -> str:
    """
    List all projects found in ~/Documents/ or the specified root.
    """
    kwargs = {}
    if search_root:
        kwargs["search_root"] = search_root
    result = lsproj.execute(**kwargs)
    return json.dumps({"success": result.success, "output": result.output, "error": result.error})


@mcp.tool()
def get_project_from_registry(project_id: str) -> str:
    """
    Get a project's full details from the AuraOS registry (SQLite).
    """
    project = mem.get_project(project_id)
    if not project:
        return json.dumps({"success": False, "error": f"Project '{project_id}' not in registry"})
    from dataclasses import asdict
    return json.dumps({"success": True, "output": asdict(project)})


@mcp.tool()
def list_registry_projects() -> str:
    """
    List all projects registered in AuraOS (from SQLite, not filesystem scan).
    """
    projects = mem.list_projects()
    from dataclasses import asdict
    return json.dumps({"success": True, "output": [asdict(p) for p in projects]})


if __name__ == "__main__":
    _sync_projects_to_db()
    print(f"[filesystem-server] starting on port {settings.port_filesystem}")
    mcp.run(transport="sse")
