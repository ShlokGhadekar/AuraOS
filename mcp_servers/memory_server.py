"""
AuraOS · Memory MCP Server
Port: 8103

Exposes the three-tier memory system to the agent.
The agent reads and writes context through this server —
it never touches SQLite or ChromaDB directly.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
from dataclasses import asdict
from mcp.server.fastmcp import FastMCP

from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from config.settings import settings

mcp = FastMCP("aura-memory", port=settings.port_memory)
mem = EpisodicMemory(settings.db_path)
sem = SemanticMemory(settings.chroma_path)


@mcp.tool()
def get_project_context(project_id: str) -> str:
    """
    Get full context for a project: snapshot, recent sessions, goals.
    This is the primary tool for restoring context at session start.
    Call this whenever the user says 'continue my <project>'.
    """
    ctx = mem.get_project_context(project_id)
    return json.dumps({"success": True, "output": ctx})


@mcp.tool()
def get_current_snapshot(project_id: str) -> str:
    """
    Get the most recent context snapshot for a project.
    Returns: current_goal, last_action, next_step, open_questions, blockers.
    """
    snap = mem.get_current_snapshot(project_id)
    if not snap:
        return json.dumps({"success": False, "error": f"No snapshot found for '{project_id}'"})
    return json.dumps({"success": True, "output": asdict(snap)})


@mcp.tool()
def save_context_snapshot(
    project_id: str,
    current_goal: str = None,
    last_action: str = None,
    next_step: str = None,
    open_questions: list = None,
    relevant_files: list = None,
    blockers: list = None,
    summary: str = None,
    session_id: str = None,
) -> str:
    """
    Save a context snapshot for a project. Call this at session end
    via the summarizer. Retires the previous current snapshot.
    """
    snap = mem.save_snapshot(
        project_id=project_id,
        session_id=session_id,
        current_goal=current_goal,
        last_action=last_action,
        next_step=next_step,
        open_questions=open_questions or [],
        relevant_files=relevant_files or [],
        blockers=blockers or [],
        summary=summary,
    )
    # Also index in semantic memory for fuzzy recall
    if summary:
        sem.upsert_snapshot(
            snap.id,
            f"{project_id}: {summary}",
            metadata={"project_id": project_id, "snapshot_id": snap.id},
        )
    return json.dumps({"success": True, "output": asdict(snap)})


@mcp.tool()
def search_projects_semantic(query: str, n_results: int = 3) -> str:
    """
    Fuzzy search across all projects by natural language.
    Use when the user refers to a project vaguely:
    'that NLP thing', 'my ML project', 'the React app'.
    """
    results = sem.search_projects(query, n_results=n_results)
    return json.dumps({"success": True, "output": results})


@mcp.tool()
def identify_project(user_input: str) -> str:
    """
    Given raw user input, return the best-matching project_id.
    Returns null if no confident match found.
    Use this before detect_project when the project name is ambiguous.
    """
    project_id = sem.identify_project(user_input)
    return json.dumps({"success": True, "output": {"project_id": project_id}})


@mcp.tool()
def list_goals(project_id: str = None) -> str:
    """
    List active goals, optionally filtered by project.
    Use when answering 'what should I work on today?'
    """
    goals = mem.list_goals(project_id=project_id)
    return json.dumps({"success": True, "output": [asdict(g) for g in goals]})


@mcp.tool()
def add_goal(
    title: str,
    project_id: str = None,
    description: str = None,
    priority: int = 2,
    due_date: str = None,
) -> str:
    """
    Add a new goal. priority: 1=high, 2=medium, 3=low.
    due_date: ISO-8601 date string e.g. '2025-07-01', or omit.
    """
    goal = mem.add_goal(
        title=title,
        project_id=project_id,
        description=description,
        priority=priority,
        due_date=due_date,
    )
    return json.dumps({"success": True, "output": asdict(goal)})


@mcp.tool()
def get_recent_sessions(project_id: str = None, limit: int = 5) -> str:
    """
    Get recent AuraOS sessions, optionally filtered by project.
    """
    sessions = mem.get_recent_sessions(project_id=project_id, limit=limit)
    return json.dumps({"success": True, "output": [asdict(s) for s in sessions]})


if __name__ == "__main__":
    print(f"[memory-server] starting on port {settings.port_memory}")
    mcp.run(transport="sse")
