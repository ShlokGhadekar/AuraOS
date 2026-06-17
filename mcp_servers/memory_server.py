"""
AuraOS · Memory MCP Server
Port: 8103
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
from dataclasses import asdict

from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from config.settings import settings

app = FastAPI(title="AuraOS Memory Server")
mem = EpisodicMemory(settings.db_path)
sem = SemanticMemory(settings.chroma_path)


class ToolRequest(BaseModel):
    params: dict[str, Any] = {}


@app.get("/health")
def health():
    return {"status": "ok", "server": "memory"}


@app.post("/tools/get_project_context")
def get_project_context(req: ToolRequest):
    ctx = mem.get_project_context(req.params.get("project_id"))
    return {"success": True, "output": ctx}


@app.post("/tools/get_current_snapshot")
def get_current_snapshot(req: ToolRequest):
    snap = mem.get_current_snapshot(req.params.get("project_id"))
    if not snap:
        return {"success": False, "error": "No snapshot found"}
    return {"success": True, "output": asdict(snap)}


@app.post("/tools/save_context_snapshot")
def save_context_snapshot(req: ToolRequest):
    p = req.params
    snap = mem.save_snapshot(
        project_id=p.get("project_id"),
        session_id=p.get("session_id"),
        current_goal=p.get("current_goal"),
        last_action=p.get("last_action"),
        next_step=p.get("next_step"),
        open_questions=p.get("open_questions", []),
        relevant_files=p.get("relevant_files", []),
        blockers=p.get("blockers", []),
        summary=p.get("summary"),
    )
    if p.get("summary") and p.get("project_id"):
        sem.upsert_snapshot(
            snap.id,
            f"{p['project_id']}: {p['summary']}",
            metadata={"project_id": p["project_id"]},
        )
    return {"success": True, "output": asdict(snap)}


@app.post("/tools/search_projects_semantic")
def search_projects_semantic(req: ToolRequest):
    results = sem.search_projects(
        req.params.get("query", ""),
        n_results=req.params.get("n_results", 3),
    )
    return {"success": True, "output": results}


@app.post("/tools/identify_project")
def identify_project(req: ToolRequest):
    project_id = sem.identify_project(req.params.get("user_input", ""))
    return {"success": True, "output": {"project_id": project_id}}


@app.post("/tools/list_goals")
def list_goals(req: ToolRequest):
    goals = mem.list_goals(project_id=req.params.get("project_id"))
    return {"success": True, "output": [asdict(g) for g in goals]}


@app.post("/tools/add_goal")
def add_goal(req: ToolRequest):
    p = req.params
    goal = mem.add_goal(
        title=p.get("title"),
        project_id=p.get("project_id"),
        description=p.get("description"),
        priority=p.get("priority", 2),
        due_date=p.get("due_date"),
    )
    return {"success": True, "output": asdict(goal)}


@app.post("/tools/get_recent_sessions")
def get_recent_sessions(req: ToolRequest):
    sessions = mem.get_recent_sessions(
        project_id=req.params.get("project_id"),
        limit=req.params.get("limit", 5),
    )
    return {"success": True, "output": [asdict(s) for s in sessions]}


if __name__ == "__main__":
    print(f"[memory-server] starting on port {settings.port_memory}")
    uvicorn.run(app, host="127.0.0.1", port=settings.port_memory, log_level="warning")