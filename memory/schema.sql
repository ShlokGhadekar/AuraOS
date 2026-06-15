-- AuraOS · Episodic Memory Schema
-- SQLite · local only · never synced to cloud
--
-- Design rules:
--   1. All timestamps stored as ISO-8601 UTC strings
--   2. JSON blobs for flexible structured data (SQLite supports json_extract)
--   3. No foreign key enforcement (SQLite default) — we enforce in Python
--   4. All tables have created_at + updated_at for auditability

PRAGMA journal_mode=WAL;       -- better concurrent read performance
PRAGMA foreign_keys=ON;


-- ─────────────────────────────────────────
-- PROJECTS
-- The canonical registry of everything AuraOS knows about.
-- Source of truth is config/projects.yaml — this table is
-- populated from it on startup and kept in sync.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS projects (
    id              TEXT PRIMARY KEY,          -- slugified name e.g. "fake-news-detection"
    name            TEXT NOT NULL,             -- display name
    path            TEXT NOT NULL,             -- absolute local path
    description     TEXT,                      -- user-written, fed into context
    github_repo     TEXT,                      -- "owner/repo" or NULL
    tags            TEXT DEFAULT '[]',         -- JSON array of strings
    is_active       INTEGER DEFAULT 1,         -- soft delete
    last_accessed   TEXT,                      -- ISO-8601, updated on every session
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ─────────────────────────────────────────
-- SESSIONS
-- One row per AuraOS interaction session.
-- A session starts when the user invokes the hotkey
-- and ends when the overlay closes or times out.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS sessions (
    id              TEXT PRIMARY KEY,          -- UUID v4
    project_id      TEXT REFERENCES projects(id),
    intent          TEXT,                      -- classified intent e.g. "continue_project"
    raw_input       TEXT NOT NULL,             -- exactly what the user typed
    plan            TEXT DEFAULT '[]',         -- JSON array of planned tool calls
    status          TEXT DEFAULT 'running',    -- running | completed | failed | aborted
    started_at      TEXT NOT NULL DEFAULT (datetime('now')),
    ended_at        TEXT,
    duration_ms     INTEGER,
    error           TEXT,                      -- last error message if status=failed
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ─────────────────────────────────────────
-- CONTEXT SNAPSHOTS
-- The semantic state of a project at the end of a session.
-- This is what gets injected when the user says
-- "continue my fake-news project" — NOT file paths.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS context_snapshots (
    id              TEXT PRIMARY KEY,          -- UUID v4
    project_id      TEXT NOT NULL REFERENCES projects(id),
    session_id      TEXT REFERENCES sessions(id),
    current_goal    TEXT,                      -- "Improve F1 score on validation set"
    last_action     TEXT,                      -- "Implemented TF-IDF, ran baseline"
    next_step       TEXT,                      -- "Try BERT embeddings"
    open_questions  TEXT DEFAULT '[]',         -- JSON array of strings
    relevant_files  TEXT DEFAULT '[]',         -- JSON array of relative paths
    blockers        TEXT DEFAULT '[]',         -- JSON array of strings
    summary         TEXT,                      -- 2-3 sentence human-readable summary
    is_current      INTEGER DEFAULT 1,         -- only one snapshot per project is current
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Only one current snapshot per project at a time
CREATE UNIQUE INDEX IF NOT EXISTS idx_snapshots_current
    ON context_snapshots(project_id)
    WHERE is_current = 1;


-- ─────────────────────────────────────────
-- TOOL CALLS
-- Audit log of every tool execution.
-- Invaluable for debugging and for the summarizer.
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS tool_calls (
    id              TEXT PRIMARY KEY,          -- UUID v4
    session_id      TEXT NOT NULL REFERENCES sessions(id),
    tool_name       TEXT NOT NULL,
    parameters      TEXT DEFAULT '{}',         -- JSON
    result          TEXT,                      -- JSON or plain text
    status          TEXT DEFAULT 'pending',    -- pending | success | failed | skipped
    duration_ms     INTEGER,
    error           TEXT,
    executed_at     TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ─────────────────────────────────────────
-- GOALS
-- User-defined long-term goals, optionally tied to a project.
-- Used by the planner when answering "what should I work on today?"
-- ─────────────────────────────────────────
CREATE TABLE IF NOT EXISTS goals (
    id              TEXT PRIMARY KEY,
    project_id      TEXT REFERENCES projects(id),   -- NULL = global goal
    title           TEXT NOT NULL,
    description     TEXT,
    priority        INTEGER DEFAULT 2,              -- 1=high 2=medium 3=low
    status          TEXT DEFAULT 'active',          -- active | completed | paused
    due_date        TEXT,                           -- ISO-8601 date or NULL
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);


-- ─────────────────────────────────────────
-- INDEXES
-- ─────────────────────────────────────────
CREATE INDEX IF NOT EXISTS idx_sessions_project    ON sessions(project_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started    ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_snapshots_project   ON context_snapshots(project_id);
CREATE INDEX IF NOT EXISTS idx_tool_calls_session  ON tool_calls(session_id);
CREATE INDEX IF NOT EXISTS idx_goals_project       ON goals(project_id);
CREATE INDEX IF NOT EXISTS idx_goals_status        ON goals(status);