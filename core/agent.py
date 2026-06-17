"""
AuraOS · Agent
==============
Main entry point. Wires together:
  classify → load context → plan → show plan → execute → summarize
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import ssl
import certifi
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
from collections.abc import Generator

from core.intent import classify_intent
from core.planner import build_plan, format_plan_for_display
from core.executor import Executor
from core.summarizer import summarize_session
from memory.episodic import EpisodicMemory
from memory.semantic import SemanticMemory
from memory.working import WorkingMemory
from config.settings import settings


class Agent:
    def __init__(self):
        self.mem = EpisodicMemory(settings.db_path)
        self.sem = SemanticMemory(settings.chroma_path)

    def run(self, user_input: str) -> Generator[str, None, None]:
        wm = WorkingMemory()
        wm.raw_input = user_input
        wm.push_message("user", user_input)

        # ── Stage 1: Classify ──────────────────────────────────
        yield "🔍 Understanding request...\n"
        intent = classify_intent(user_input)
        wm.intent = intent.get("intent")
        yield f"   Intent: {intent.get('intent')} ({intent.get('confidence', 0):.0%})\n"

        # Check if this matches a workflow before planning
        from core.workflow_engine import match_workflow, build_workflow_context, WorkflowExecutor

        workflow = match_workflow(user_input)
        if workflow or intent.get("intent") in ("run_workflow", "dsa_session", "project_kickoff"):
            if not workflow:
                # Try matching by intent name
                from core.workflow_engine import load_workflow
                intent_to_workflow = {
                    "dsa_session":     "dsa_session",
                    "project_kickoff": "project_kickoff",
                    "run_workflow":    None,
                }
                wf_id = intent_to_workflow.get(intent.get("intent"))
                if wf_id:
                    try:
                        workflow = load_workflow(wf_id)
                    except FileNotFoundError:
                        workflow = None

        if workflow:
            yield f"   Workflow: {workflow['name']}\n"

            # Build session
            session = self.mem.start_session(
                raw_input=user_input,
                project_id=wm.active_project_id,
                intent=intent.get("intent"),
            )
            wm.session_id = session.id

            # Build context
            agent_ctx = {
                "active_project_id":   wm.active_project_id or "",
                "active_project_path": "",
            }
            if wm.active_project_id:
                project = self.mem.get_project(wm.active_project_id)
                if project:
                    agent_ctx["active_project_path"] = project.path

            wf_context = build_workflow_context(workflow, user_input, agent_ctx)

            # Execute workflow
            from core.executor import Executor
            executor = Executor(session.id, wm, self.mem)
            wf_executor = WorkflowExecutor(workflow, wf_context, executor)
            yield from wf_executor.run()

            self.mem.end_session(session.id, status="completed")
            return   # Skip normal plan/execute flow    

        # ── Stage 2: Load context ──────────────────────────────
        context = {}
        project_hint = intent.get("project_hint")

        if project_hint:
            yield f"   Project hint: {project_hint}\n"
            project_id = self.sem.identify_project(project_hint) or _slugify(project_hint)
            wm.set_project(project_id)

            # Ensure project exists in SQLite
            if not self.mem.get_project(project_id):
                self.mem.upsert_project(
                    id=project_id,
                    name=project_hint or project_id,
                    path=str(Path.home() / "Documents" / project_id),
                )

            # Load episodic memory context
            ctx = self.mem.get_project_context(project_id)
            if ctx.get("snapshot"):
                wm.set_snapshot(ctx["snapshot"])
                snap = ctx["snapshot"]
                summary = snap.get("summary") or snap.get("current_goal") or "snapshot loaded"
                yield f"   Memory: {summary}\n"
            context = ctx

            # Load GitHub context if repo is registered
            project = self.mem.get_project(project_id)
            if project and project.github_repo:
                yield f"   GitHub: fetching context for {project.github_repo}...\n"
                gh_context = self._load_github_context(project.github_repo)
                if gh_context:
                    context["github"] = gh_context
                    issues_count = len(gh_context.get("open_issues", []))
                    commits_count = len(gh_context.get("recent_commits", []))
                    yield f"   GitHub: {issues_count} open issues · {commits_count} recent commits\n"

        # ── Stage 3: Build plan ────────────────────────────────
        yield "\n🧠 Planning...\n"
        plan = build_plan(user_input, intent, context)
        wm.set_plan(plan)

        # Create session row
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

        # ── Stage 5: Surface loaded context ───────────────────
        if wm.loaded_snapshot:
            yield from self._render_snapshot(wm.loaded_snapshot)

        if context.get("github"):
            yield from self._render_github(context["github"])

        yield "\n▶ Executing...\n"

        # ── Stage 6: Execute ───────────────────────────────────
        executor = Executor(session.id, wm, self.mem)
        yield from executor.run(plan)

        # ── Stage 7: Summarize ─────────────────────────────────
        yield "\n💾 Saving session...\n"
        try:
            summary = summarize_session(wm)
            if summary and wm.active_project_id:
                self.mem.save_snapshot(
                    project_id=wm.active_project_id,
                    session_id=session.id,
                    **summary,
                )
                if summary.get("summary"):
                    self.sem.upsert_snapshot(
                        session.id,
                        f"{wm.active_project_id}: {summary['summary']}",
                        metadata={"project_id": wm.active_project_id},
                    )
                    self.sem.upsert_project(
                        wm.active_project_id,
                        f"{wm.active_project_id}: {summary['summary']}",
                        metadata={"project_id": wm.active_project_id},
                    )
            self.mem.end_session(session.id, status="completed")
            yield "✓ Session saved.\n"
        except Exception as e:
            self.mem.end_session(session.id, status="failed", error=str(e))
            yield f"⚠ Could not save session: {e}\n"

    def _load_github_context(self, repo: str) -> dict:
        try:
            from core.mcp_client import call_mcp_tool
            issues_resp  = call_mcp_tool("get_open_issues", {"repo": repo})
            commits_resp = call_mcp_tool("get_recent_commits", {"repo": repo, "n": 5})
            
            return {
                "repo":           repo,
                "open_issues":    issues_resp.get("output", []) if issues_resp.get("success") else [],
                "recent_commits": commits_resp.get("output", []) if commits_resp.get("success") else [],
            }
        except ConnectionError as e:
            print(f"DEBUG connection error: {e}")
            return {}
        except Exception as e:
            print(f"DEBUG exception: {e}")
            return {}

    def _render_snapshot(self, snapshot: dict) -> Generator[str, None, None]:
        """Surface the loaded memory snapshot to the user before execution."""
        yield "\n📌 Last session context:\n"
        if snapshot.get("current_goal"):
            yield f"   Goal:       {snapshot['current_goal']}\n"
        if snapshot.get("last_action"):
            yield f"   Last:       {snapshot['last_action']}\n"
        if snapshot.get("next_step"):
            yield f"   Next:       {snapshot['next_step']}\n"
        if snapshot.get("blockers"):
            for b in snapshot["blockers"]:
                yield f"   ⚠ Blocker: {b}\n"
        if snapshot.get("open_questions"):
            for q in snapshot["open_questions"]:
                yield f"   ❓ {q}\n"

    def _render_github(self, gh: dict) -> Generator[str, None, None]:
        """Surface GitHub context to the user before execution."""
        yield f"\n🐙 GitHub — {gh['repo']}:\n"
        commits = gh.get("recent_commits", [])
        if commits:
            yield f"   Last commit: {commits[0].get('message', '')} ({commits[0].get('date', '')[:10]})\n"
        issues = gh.get("open_issues", [])
        if issues:
            yield f"   Open issues ({len(issues)}):\n"
            for issue in issues[:3]:
                yield f"     #{issue['number']} {issue['title']}\n"

    def close(self):
        self.mem.close()


def _slugify(text: str) -> str:
    return text.lower().strip().replace(" ", "-").replace("_", "-")