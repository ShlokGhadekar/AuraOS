"""
AuraOS · Agent
==============
The main entry point. Wires together:
  classify → plan → show plan → execute → summarize

Usage:
    agent = Agent()
    for token in agent.run("continue my fake news project"):
        print(token, end="", flush=True)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from collections.abc import Generator

from core.intent import classify_intent
from core.planner import build_plan, format_plan_for_display
from core.executor import Executor
from core.summarizer import summarize_session
from memory.episodic import EpisodicMemory
from memory.working import WorkingMemory
from config.settings import settings


class Agent:
    """
    One Agent instance per AuraOS session.
    Create a new one for each user invocation.
    """

    def __init__(self):
        self.mem = EpisodicMemory(settings.db_path)

    def run(self, user_input: str) -> Generator[str, None, None]:
        """
        Main agent loop. Yields streaming tokens.

        Stages:
          1. Classify intent (fast, Haiku)
          2. Load relevant context from memory
          3. Build plan (Sonnet)
          4. Show plan to user
          5. Execute plan (streaming)
          6. Summarize session and save snapshot
        """
        wm = WorkingMemory()
        wm.raw_input = user_input
        wm.push_message("user", user_input)

        # ── Stage 1: Classify ──────────────────────────────────
        yield "🔍 Understanding request...\n"
        intent = classify_intent(user_input)
        wm.intent = intent.get("intent")
        yield f"   Intent: {intent.get('intent')} ({intent.get('confidence', 0):.0%})\n"

        # ── Stage 2: Load context ──────────────────────────────
        context = {}
        project_hint = intent.get("project_hint")

        if project_hint:
            yield f"   Project hint: {project_hint}\n"
            # Try to match to a registered project
            from memory.semantic import SemanticMemory
            sem = SemanticMemory(settings.chroma_path)
            
            project_id = sem.identify_project(project_hint) or _slugify(project_hint)
            wm.set_project(project_id)

# Ensure project exists in SQLite so session FK doesn't fail
            if not self.mem.get_project(project_id):
                self.mem.upsert_project(
                    id=project_id,
                    name=project_hint or project_id,
                    path=str(Path.home() / "Documents" / project_id),
                )

            ctx = self.mem.get_project_context(project_id)
            if ctx.get("snapshot"):
                wm.set_snapshot(ctx["snapshot"])
                snap = ctx["snapshot"]
                yield f"   Memory: {snap.get('summary') or snap.get('current_goal') or 'snapshot loaded'}\n"
            context = ctx

        # ── Stage 3: Build plan ────────────────────────────────
        yield "\n🧠 Planning...\n"
        plan = build_plan(user_input, intent, context)
        wm.set_plan(plan)

        # Create session row in DB
        session = self.mem.start_session(
            raw_input=user_input,
            project_id=wm.active_project_id,
            intent=wm.intent,
        )
        wm.session_id = session.id
        self.mem.update_session_plan(session.id, plan)

        if wm.active_project_id:
            self.mem.touch_project(wm.active_project_id)

        # ── Stage 4: Show plan ─────────────────────────────────
        yield "\n" + format_plan_for_display(plan) + "\n"
        yield "\n▶ Executing...\n"

        # ── Stage 5: Execute ───────────────────────────────────
        executor = Executor(session.id, wm, self.mem)
        yield from executor.run(plan)

        # ── Stage 6: Summarize ─────────────────────────────────
        yield "\n💾 Saving session...\n"
        try:
            summary = summarize_session(wm)
            if summary and wm.active_project_id:
                self.mem.save_snapshot(
                    project_id=wm.active_project_id,
                    session_id=session.id,
                    **summary,
                )
                # Index in semantic memory
                from memory.semantic import SemanticMemory
                sem = SemanticMemory(settings.chroma_path)
                if summary.get("summary"):
                    sem.upsert_snapshot(
                        session.id,
                        f"{wm.active_project_id}: {summary['summary']}",
                        metadata={"project_id": wm.active_project_id},
                    )
                    sem.upsert_project(
                        wm.active_project_id,
                        f"{wm.active_project_id}: {summary['summary']}",
                        metadata={"project_id": wm.active_project_id},
                    )
            self.mem.end_session(session.id, status="completed")
            yield "✓ Session saved.\n"
        except Exception as e:
            self.mem.end_session(session.id, status="failed", error=str(e))
            yield f"⚠ Could not save session: {e}\n"

    def close(self):
        self.mem.close()


def _slugify(text: str) -> str:
    """Quick slug for project hints that don't match a known project."""
    return text.lower().strip().replace(" ", "-").replace("_", "-")