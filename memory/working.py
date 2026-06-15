"""
AuraOS · Working Memory
=======================
Ephemeral in-process state for a single AuraOS session.
Lives only as long as the Python process — nothing is persisted here.

The session summarizer reads from this at session end
to write a ContextSnapshot to episodic memory.

Design: intentionally simple. A thin wrapper around a dict
with typed accessors so the agent always knows what's available.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class WorkingMemory:
    """
    Holds all mutable state for one AuraOS session.

    Lifecycle:
        wm = WorkingMemory()
        wm.set_project("fake-news-detection")
        wm.push_message("user", "continue my project")
        wm.record_tool_result("open_vscode", {"status": "ok"})
        snapshot_data = wm.to_snapshot_dict()   # feed to summarizer
    """

    # Current project being worked on (may be None if not yet determined)
    active_project_id: Optional[str] = None

    # The raw user input that started this session
    raw_input: str = ""

    # Classified intent from the intent classifier
    intent: Optional[str] = None

    # The plan produced by the planner — list of step dicts
    # [{"step": 1, "tool": "open_vscode", "reason": "...", "params": {...}}, ...]
    plan: list[dict] = field(default_factory=list)

    # Conversation buffer — fed into Claude for multi-turn context
    # [{"role": "user"|"assistant"|"tool", "content": "..."}, ...]
    conversation: list[dict] = field(default_factory=list)

    # Tool results accumulated during this session
    # {"tool_name": result, ...} — last result per tool name
    tool_results: dict[str, Any] = field(default_factory=dict)

    # Session DB id (set once the session row is created)
    session_id: Optional[str] = None

    # Snapshot loaded at session start (from episodic memory)
    loaded_snapshot: Optional[dict] = None

    # Free-form scratchpad for agent reasoning
    scratchpad: dict[str, Any] = field(default_factory=dict)


    # ── Conversation ──────────────────────────────────────────

    def push_message(self, role: str, content: str):
        """Append a message to the conversation buffer."""
        self.conversation.append({"role": role, "content": content})

    def get_conversation(self) -> list[dict]:
        return list(self.conversation)

    def conversation_text(self) -> str:
        """Flat text representation for summarizer prompt."""
        lines = []
        for m in self.conversation:
            prefix = m["role"].upper()
            lines.append(f"{prefix}: {m['content']}")
        return "\n".join(lines)


    # ── Tool results ──────────────────────────────────────────

    def record_tool_result(self, tool_name: str, result: Any):
        self.tool_results[tool_name] = result
        self.push_message("tool", f"[{tool_name}] → {result}")

    def get_tool_result(self, tool_name: str) -> Any:
        return self.tool_results.get(tool_name)


    # ── Project ───────────────────────────────────────────────

    def set_project(self, project_id: str):
        self.active_project_id = project_id

    def set_snapshot(self, snapshot: dict):
        """Store the snapshot loaded at session start."""
        self.loaded_snapshot = snapshot

    def has_project(self) -> bool:
        return self.active_project_id is not None


    # ── Plan ──────────────────────────────────────────────────

    def set_plan(self, plan: list[dict]):
        self.plan = plan

    def get_pending_steps(self) -> list[dict]:
        return [s for s in self.plan if s.get("status") != "done"]

    def mark_step_done(self, step_index: int, result: Any = None):
        if 0 <= step_index < len(self.plan):
            self.plan[step_index]["status"] = "done"
            self.plan[step_index]["result"] = result

    def mark_step_failed(self, step_index: int, error: str):
        if 0 <= step_index < len(self.plan):
            self.plan[step_index]["status"] = "failed"
            self.plan[step_index]["error"] = error


    # ── Scratchpad ────────────────────────────────────────────

    def note(self, key: str, value: Any):
        self.scratchpad[key] = value

    def recall(self, key: str, default: Any = None) -> Any:
        return self.scratchpad.get(key, default)


    # ── Summarizer feed ───────────────────────────────────────

    def to_snapshot_dict(self) -> dict:
        """
        Return everything the session summarizer needs
        to write a ContextSnapshot to episodic memory.
        """
        completed_tools = [
            name for name, result in self.tool_results.items()
            if result is not None
        ]
        return {
            "project_id":       self.active_project_id,
            "session_id":       self.session_id,
            "raw_input":        self.raw_input,
            "intent":           self.intent,
            "plan":             self.plan,
            "conversation":     self.conversation,
            "tool_results":     self.tool_results,
            "completed_tools":  completed_tools,
            "loaded_snapshot":  self.loaded_snapshot,
        }

    def summary_stats(self) -> dict:
        """Quick stats for debugging / display."""
        return {
            "project":        self.active_project_id,
            "intent":         self.intent,
            "plan_steps":     len(self.plan),
            "steps_done":     len([s for s in self.plan if s.get("status") == "done"]),
            "messages":       len(self.conversation),
            "tools_called":   len(self.tool_results),
        }