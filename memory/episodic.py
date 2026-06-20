"""
AuraOS · Episodic Memory
========================
SQLite-backed store for projects, sessions, context snapshots,
tool call audit logs, and goals.

All public methods are synchronous — SQLite doesn't benefit from
async here and the added complexity isn't worth it at this scale.
FastAPI routes that call these should run them in a thread pool
via asyncio.to_thread() if needed.

Design decisions:
  - Returns dataclasses, not raw dicts, so callers get type hints
  - JSON columns are serialized/deserialized transparently
  - No ORM — raw SQL is easier to debug and audit
  - DB path is configurable so tests can use :memory:
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

def _uuid() -> str:
    return str(uuid.uuid4())

def _dumps(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)

def _loads(s: str | None, default=None):
    if s is None:
        return default
    try:
        return json.loads(s)
    except (json.JSONDecodeError, TypeError):
        return default


# ─────────────────────────────────────────────────────────────
# Dataclasses (returned by all public methods)
# ─────────────────────────────────────────────────────────────

@dataclass
class Project:
    id: str
    name: str
    path: str
    description: Optional[str] = None
    github_repo: Optional[str] = None
    tags: list[str] = field(default_factory=list)
    is_active: bool = True
    last_accessed: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


@dataclass
class Session:
    id: str
    raw_input: str
    project_id: Optional[str] = None
    intent: Optional[str] = None
    plan: list[dict] = field(default_factory=list)
    status: str = "running"
    started_at: str = field(default_factory=_now)
    ended_at: Optional[str] = None
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    created_at: str = field(default_factory=_now)


@dataclass
class ContextSnapshot:
    id: str
    project_id: str
    session_id: Optional[str] = None
    current_goal: Optional[str] = None
    last_action: Optional[str] = None
    next_step: Optional[str] = None
    open_questions: list[str] = field(default_factory=list)
    relevant_files: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    summary: Optional[str] = None
    is_current: bool = True
    created_at: str = field(default_factory=_now)


@dataclass
class ToolCall:
    id: str
    session_id: str
    tool_name: str
    parameters: dict = field(default_factory=dict)
    result: Optional[str] = None
    status: str = "pending"
    duration_ms: Optional[int] = None
    error: Optional[str] = None
    executed_at: str = field(default_factory=_now)


@dataclass
class Goal:
    id: str
    title: str
    project_id: Optional[str] = None
    description: Optional[str] = None
    priority: int = 2
    status: str = "active"
    due_date: Optional[str] = None
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)


# ─────────────────────────────────────────────────────────────
# EpisodicMemory
# ─────────────────────────────────────────────────────────────

class EpisodicMemory:
    """
    The long-term episodic store for AuraOS.

    Usage:
        mem = EpisodicMemory()                   # uses default data/auraos.db
        mem = EpisodicMemory(":memory:")          # for tests

        project = mem.upsert_project(...)
        session = mem.start_session(...)
        mem.end_session(session.id, status="completed")
        snapshot = mem.save_snapshot(...)
        snapshot = mem.get_current_snapshot("fake-news-detection")
    """

    SCHEMA_PATH = Path(__file__).parent / "schema.sql"

    def __init__(self, db_path: str | Path = None):
        if db_path is None:
            default = Path(__file__).parent.parent / "data" / "auraos.db"
            default.parent.mkdir(parents=True, exist_ok=True)
            db_path = str(default)

        self.db_path = str(db_path)
        self._conn: sqlite3.Connection = sqlite3.connect(
            self.db_path,
            check_same_thread=False,
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        self._conn.row_factory = sqlite3.Row
        self._apply_schema()

    def _apply_schema(self):
        schema = self.SCHEMA_PATH.read_text()
        self._conn.executescript(schema)
        self._conn.commit()

    def close(self):
        self._conn.close()

    # ── internal ──────────────────────────────────────────────

    def _exec(self, sql: str, params: tuple = (), retries: int = 8) -> sqlite3.Cursor:
        import time as _time
        for attempt in range(retries):
            try:
                return self._conn.execute(sql, params)
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < retries - 1:
                    _time.sleep(0.05 * (2 ** attempt))  # exponential backoff: 50ms, 100ms, 200ms...
                    continue
                raise

    def _commit(self, retries: int = 8):
        import time as _time
        for attempt in range(retries):
            try:
                self._conn.commit()
                return
            except sqlite3.OperationalError as e:
                if "locked" in str(e) and attempt < retries - 1:
                    _time.sleep(0.05 * (2 ** attempt))
                    continue
                raise


    # ── PROJECTS ──────────────────────────────────────────────

    def upsert_project(
        self,
        id: str,
        name: str,
        path: str,
        description: str = None,
        github_repo: str = None,
        tags: list[str] = None,
    ) -> Project:
        """Insert or update a project. Safe to call repeatedly on startup."""
        now = _now()
        self._exec("""
            INSERT INTO projects (id, name, path, description, github_repo, tags, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name        = excluded.name,
                path        = excluded.path,
                description = excluded.description,
                github_repo = excluded.github_repo,
                tags        = excluded.tags,
                updated_at  = excluded.updated_at
        """, (id, name, path, description, github_repo, _dumps(tags or []), now, now))
        self._commit()
        return self.get_project(id)

    def get_project(self, project_id: str) -> Optional[Project]:
        row = self._exec(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
        return self._row_to_project(row) if row else None

    def list_projects(self, active_only: bool = True) -> list[Project]:
        sql = "SELECT * FROM projects"
        if active_only:
            sql += " WHERE is_active = 1"
        sql += " ORDER BY last_accessed DESC NULLS LAST"
        rows = self._exec(sql).fetchall()
        return [self._row_to_project(r) for r in rows]

    def touch_project(self, project_id: str):
        """Update last_accessed timestamp."""
        self._exec(
            "UPDATE projects SET last_accessed = ? WHERE id = ?",
            (_now(), project_id)
        )
        self._commit()

    def _row_to_project(self, row: sqlite3.Row) -> Project:
        d = dict(row)
        d["tags"] = _loads(d.get("tags"), [])
        d["is_active"] = bool(d.get("is_active", 1))
        return Project(**d)


    # ── SESSIONS ──────────────────────────────────────────────

    def start_session(
        self,
        raw_input: str,
        project_id: str = None,
        intent: str = None,
    ) -> Session:
        """Create a new session row and return it."""
        session_id = _uuid()
        now = _now()
        self._exec("""
            INSERT INTO sessions (id, project_id, intent, raw_input, started_at, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (session_id, project_id, intent, raw_input, now, now))
        self._commit()
        return self.get_session(session_id)

    def end_session(
        self,
        session_id: str,
        status: str = "completed",
        error: str = None,
    ) -> Session:
        """Mark a session as finished and compute duration."""
        session = self.get_session(session_id)
        if not session:
            raise ValueError(f"Session {session_id} not found")

        now = _now()
        start = datetime.fromisoformat(session.started_at)
        end = datetime.fromisoformat(now)
        duration_ms = int((end - start).total_seconds() * 1000)

        self._exec("""
            UPDATE sessions
            SET status = ?, ended_at = ?, duration_ms = ?, error = ?
            WHERE id = ?
        """, (status, now, duration_ms, error, session_id))
        self._commit()
        return self.get_session(session_id)

    def update_session_plan(self, session_id: str, plan: list[dict]):
        self._exec(
            "UPDATE sessions SET plan = ? WHERE id = ?",
            (_dumps(plan), session_id)
        )
        self._commit()

    def get_session(self, session_id: str) -> Optional[Session]:
        row = self._exec(
            "SELECT * FROM sessions WHERE id = ?", (session_id,)
        ).fetchone()
        return self._row_to_session(row) if row else None

    def get_recent_sessions(
        self,
        project_id: str = None,
        limit: int = 10,
    ) -> list[Session]:
        if project_id:
            rows = self._exec("""
                SELECT * FROM sessions
                WHERE project_id = ?
                ORDER BY started_at DESC
                LIMIT ?
            """, (project_id, limit)).fetchall()
        else:
            rows = self._exec("""
                SELECT * FROM sessions
                ORDER BY started_at DESC
                LIMIT ?
            """, (limit,)).fetchall()
        return [self._row_to_session(r) for r in rows]

    def _row_to_session(self, row: sqlite3.Row) -> Session:
        d = dict(row)
        d["plan"] = _loads(d.get("plan"), [])
        return Session(**d)


    # ── CONTEXT SNAPSHOTS ─────────────────────────────────────

    def save_snapshot(
        self,
        project_id: str,
        session_id: str = None,
        current_goal: str = None,
        last_action: str = None,
        next_step: str = None,
        open_questions: list[str] = None,
        relevant_files: list[str] = None,
        blockers: list[str] = None,
        summary: str = None,
    ) -> ContextSnapshot:
        """
        Save a new snapshot and retire the previous current one.
        Only one snapshot per project can be is_current=1.
        """
        # Retire old current snapshot
        self._exec("""
            UPDATE context_snapshots
            SET is_current = 0
            WHERE project_id = ? AND is_current = 1
        """, (project_id,))

        snap_id = _uuid()
        now = _now()
        self._exec("""
            INSERT INTO context_snapshots (
                id, project_id, session_id,
                current_goal, last_action, next_step,
                open_questions, relevant_files, blockers,
                summary, is_current, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
        """, (
            snap_id, project_id, session_id,
            current_goal, last_action, next_step,
            _dumps(open_questions or []),
            _dumps(relevant_files or []),
            _dumps(blockers or []),
            summary, now,
        ))
        self._commit()
        return self.get_current_snapshot(project_id)

    def get_current_snapshot(self, project_id: str) -> Optional[ContextSnapshot]:
        row = self._exec("""
            SELECT * FROM context_snapshots
            WHERE project_id = ? AND is_current = 1
        """, (project_id,)).fetchone()
        return self._row_to_snapshot(row) if row else None

    def get_snapshot_history(
        self,
        project_id: str,
        limit: int = 5,
    ) -> list[ContextSnapshot]:
        rows = self._exec("""
            SELECT * FROM context_snapshots
            WHERE project_id = ?
            ORDER BY created_at DESC
            LIMIT ?
        """, (project_id, limit)).fetchall()
        return [self._row_to_snapshot(r) for r in rows]

    def _row_to_snapshot(self, row: sqlite3.Row) -> ContextSnapshot:
        d = dict(row)
        d["open_questions"] = _loads(d.get("open_questions"), [])
        d["relevant_files"] = _loads(d.get("relevant_files"), [])
        d["blockers"]       = _loads(d.get("blockers"), [])
        d["is_current"]     = bool(d.get("is_current", 1))
        return ContextSnapshot(**d)


    # ── TOOL CALLS ────────────────────────────────────────────

    def log_tool_call(
        self,
        session_id: str,
        tool_name: str,
        parameters: dict = None,
    ) -> ToolCall:
        """Create a pending tool call log entry."""
        call_id = _uuid()
        self._exec("""
            INSERT INTO tool_calls (id, session_id, tool_name, parameters, executed_at)
            VALUES (?, ?, ?, ?, ?)
        """, (call_id, session_id, tool_name, _dumps(parameters or {}), _now()))
        self._commit()
        return self.get_tool_call(call_id)

    def complete_tool_call(
        self,
        call_id: str,
        status: str,
        result: str = None,
        duration_ms: int = None,
        error: str = None,
    ):
        self._exec("""
            UPDATE tool_calls
            SET status = ?, result = ?, duration_ms = ?, error = ?
            WHERE id = ?
        """, (status, result, duration_ms, error, call_id))
        self._commit()

    def get_tool_call(self, call_id: str) -> Optional[ToolCall]:
        row = self._exec(
            "SELECT * FROM tool_calls WHERE id = ?", (call_id,)
        ).fetchone()
        return self._row_to_tool_call(row) if row else None

    def get_session_tool_calls(self, session_id: str) -> list[ToolCall]:
        rows = self._exec("""
            SELECT * FROM tool_calls
            WHERE session_id = ?
            ORDER BY executed_at ASC
        """, (session_id,)).fetchall()
        return [self._row_to_tool_call(r) for r in rows]

    def _row_to_tool_call(self, row: sqlite3.Row) -> ToolCall:
        d = dict(row)
        d["parameters"] = _loads(d.get("parameters"), {})
        return ToolCall(**d)


    # ── GOALS ─────────────────────────────────────────────────

    def add_goal(
        self,
        title: str,
        project_id: str = None,
        description: str = None,
        priority: int = 2,
        due_date: str = None,
    ) -> Goal:
        goal_id = _uuid()
        now = _now()
        self._exec("""
            INSERT INTO goals (id, project_id, title, description, priority, due_date, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (goal_id, project_id, title, description, priority, due_date, now, now))
        self._commit()
        return self.get_goal(goal_id)

    def get_goal(self, goal_id: str) -> Optional[Goal]:
        row = self._exec(
            "SELECT * FROM goals WHERE id = ?", (goal_id,)
        ).fetchone()
        return self._row_to_goal(row) if row else None

    def list_goals(
        self,
        project_id: str = None,
        status: str = "active",
    ) -> list[Goal]:
        if project_id:
            rows = self._exec("""
                SELECT * FROM goals
                WHERE project_id = ? AND status = ?
                ORDER BY priority ASC, due_date ASC NULLS LAST
            """, (project_id, status)).fetchall()
        else:
            rows = self._exec("""
                SELECT * FROM goals
                WHERE status = ?
                ORDER BY priority ASC, due_date ASC NULLS LAST
            """, (status,)).fetchall()
        return [self._row_to_goal(r) for r in rows]

    def complete_goal(self, goal_id: str):
        self._exec(
            "UPDATE goals SET status = 'completed', updated_at = ? WHERE id = ?",
            (_now(), goal_id)
        )
        self._commit()

    def _row_to_goal(self, row: sqlite3.Row) -> Goal:
        return Goal(**dict(row))


    # ── CONVENIENCE ───────────────────────────────────────────

    def get_project_context(self, project_id: str) -> dict:
        """
        Return everything the agent needs to answer
        "continue my <project>" in one call.
        """
        project  = self.get_project(project_id)
        snapshot = self.get_current_snapshot(project_id)
        sessions = self.get_recent_sessions(project_id, limit=3)
        goals    = self.list_goals(project_id)

        return {
            "project":        asdict(project) if project else None,
            "snapshot":       asdict(snapshot) if snapshot else None,
            "recent_sessions": [asdict(s) for s in sessions],
            "active_goals":   [asdict(g) for g in goals],
        }