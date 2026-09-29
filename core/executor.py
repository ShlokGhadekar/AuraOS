"""
AuraOS · Executor
=================
Runs the plan produced by the planner.
Streams progress tokens to the caller as it goes.
Logs every tool call via the memory MCP server (not direct SQLite)
to avoid multi-writer lock contention.
"""
import json
import time
from collections.abc import Generator
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from memory.episodic import EpisodicMemory
from memory.working import WorkingMemory
from tools.macos_tools import MACOS_TOOLS_BY_NAME
from tools.filesystem_tools import FILESYSTEM_TOOLS_BY_NAME
from tools.git_tools import GIT_TOOLS_BY_NAME
from config.settings import settings

# All tools the executor knows about
from tools.scaffold_tools import SCAFFOLD_TOOLS_BY_NAME

ALL_TOOLS = {**MACOS_TOOLS_BY_NAME, **FILESYSTEM_TOOLS_BY_NAME, **GIT_TOOLS_BY_NAME, **SCAFFOLD_TOOLS_BY_NAME}

MCP_TO_LOCAL = {
    "launch_app":            "open_app",
    "open_file_with_app":    "open_file",
    "open_vscode_workspace": "open_vscode_workspace",
    "send_notification":     "send_notification",
    "detect_project":        "detect_project",
    "list_recent_files":     "list_recent_files",
    "list_projects":         "list_projects",
    "quit_apps":             "quit_apps",
    "set_do_not_disturb":    "set_do_not_disturb",
    "git_status":            "git_status",
    "git_commit":            "git_commit",
    "git_init_and_push":     "git_init_and_push",
    "create_directory":   "create_directory",
    "scaffold_project":   "scaffold_project",
    "register_project":   "register_project",
}

# Tools with both a local and an MCP implementation where the MCP one must win.
# open_url has to go to the Playwright browser server so that follow-up steps
# (get_page_text, click_element, fill_form) act on the page it opened; the local
# default-browser tool is only a fallback for when that server is offline.
PREFER_MCP = {"open_url"}

# Word the user adds to a command to approve steps marked requires_confirmation,
# e.g. "wrap up auraos confirm". Without it those steps are skipped.
CONFIRM_WORDS = {"confirm", "confirmed", "--yes"}

# MCP write tools that always need confirmation in LLM-planned steps, even if
# the planner forgot to flag them (local tools use their own class attribute).
MCP_CONFIRM_REQUIRED = {"create_issue", "close_issue", "create_pull_request", "create_github_repo"}


def split_confirmation(user_input: str) -> tuple[str, bool]:
    """Strip confirmation words from the input. Returns (clean_input, confirmed)."""
    words = user_input.split()
    kept = [w for w in words if w.lower().strip(".,!") not in CONFIRM_WORDS]
    return " ".join(kept), len(kept) != len(words)


def skipped_for_confirmation(tool_name: str):
    from tools.base import ToolResult
    return ToolResult(
        success=True,
        tool_name=tool_name,
        message=f"⏸  {tool_name} skipped — needs confirmation (add 'confirm' to your command to run it)",
        metadata={"needs_confirmation": True},
    )


TOOL_DISPLAY = {
    "detect_project":          "🔍 Detecting project",
    "list_recent_files":       "📂 Reading recent files",
    "list_projects":           "📁 Listing projects",
    "launch_app":              "🚀 Launching app",
    "open_vscode_workspace":   "💻 Opening VS Code",
    "open_file_with_app":      "📄 Opening file",
    "send_notification":       "🔔 Sending notification",
    "get_project_context":     "🧠 Loading memory",
    "get_current_snapshot":    "🧠 Reading snapshot",
    "identify_project":        "🔎 Identifying project",
    "get_today_events":        "📅 Checking calendar",
    "get_upcoming_deadlines":  "📅 Checking deadlines",
    "list_goals":              "🎯 Loading goals",
    "list_repos":              "🐙 Fetching repos",
    "get_open_issues":         "🐙 Fetching issues",
    "get_recent_commits":      "🐙 Fetching commits",
    "synthesize_daily_plan":   "🗓  Building your day",
    "quit_apps":               "🔇 Quitting apps",
    "set_do_not_disturb":      "🌙 Setting focus mode",
    "open_url":                "🌐 Opening URL",
    "git_status":              "📊 Checking git status",
    "git_commit":              "💾 Committing changes",
    "save_context_snapshot":   "💾 Saving snapshot",
}


class Executor:
    """
    Runs a plan step by step, streaming progress to the caller.

    Usage:
        executor = Executor(session_id, working_memory, episodic_memory)
        for token in executor.run(plan):
            print(token, end="", flush=True)
    """

    def __init__(
        self,
        session_id: str,
        wm: WorkingMemory,
        mem: EpisodicMemory,
        confirmed: bool = False,
    ):
        self.session_id = session_id
        self.wm = wm
        self.mem = mem  # kept for reads only — writes go through MCP
        self.confirmed = confirmed  # user approved requires_confirmation steps

    def run(self, plan: list[dict]) -> Generator[str, None, None]:
        """
        Execute a plan step by step.
        Yields human-readable progress strings.
        """
        yield "\n"

        for i, step in enumerate(plan):
            tool_name     = step.get("tool", "")
            params        = step.get("params") or {}
            local_tool    = ALL_TOOLS.get(MCP_TO_LOCAL.get(tool_name, tool_name))
            needs_confirm = (
                step.get("requires_confirmation", False)
                or tool_name in MCP_CONFIRM_REQUIRED
                or bool(local_tool and local_tool.requires_confirmation)
            )

            display = TOOL_DISPLAY.get(tool_name, f"⚙️  {tool_name}")
            yield f"{display}...\n"

            if needs_confirm and not self.confirmed:
                self.wm.mark_step_failed(i, error="skipped: needs confirmation")
                yield f"  {skipped_for_confirmation(tool_name).message}\n"
                if step.get("reason"):
                    yield f"     → {step['reason']}\n"
                continue
            if needs_confirm:
                yield "  ⚠️  Confirmed — running.\n"

            # Log to memory via MCP (avoids direct SQLite write contention)
            call_id = self._log_tool_call(tool_name, params)

            # Execute the tool
            start = time.monotonic()
            result = self._execute_tool(tool_name, params)
            duration_ms = int((time.monotonic() - start) * 1000)

            # Update plan step status in working memory (in-process, no DB)
            if result and result.success:
                self.wm.mark_step_done(i, result=result.output)
            else:
                self.wm.mark_step_failed(i, error=result.error if result else "unknown")

            # Complete the tool call log via MCP
            self._complete_tool_call(
                call_id,
                status="success" if (result and result.success) else "failed",
                result=json.dumps(result.output, default=str) if (result and result.output) else None,
                duration_ms=duration_ms,
                error=result.error if (result and not result.success) else None,
            )

            # Store in working memory
            if result:
                self.wm.record_tool_result(tool_name, result.output)

            # Stream result
            if result and result.success:
                yield f"  ✓ {result.message} ({duration_ms}ms)\n"
                if result.output and isinstance(result.output, dict):
                    yield from self._format_output(tool_name, result.output)
                elif result.output and isinstance(result.output, list):
                    yield from self._format_list_output(tool_name, result.output)
            else:
                error = result.error if result else "Tool not found"
                yield f"  ✗ Failed: {error}\n"

        yield "\n✅ Done.\n"

    def _log_tool_call(self, tool_name: str, params: dict) -> str | None:
        """Log a pending tool call via the memory MCP server. Returns call_id or None."""
        try:
            from core.mcp_client import call_mcp_tool
            resp = call_mcp_tool("log_tool_call", {
                "session_id": self.session_id,
                "tool_name": tool_name,
                "parameters": params,
            })
            if resp.get("success"):
                return resp["output"]["id"]
        except Exception:
            pass
        return None

    def _complete_tool_call(
        self,
        call_id: str | None,
        status: str,
        result: str = None,
        duration_ms: int = None,
        error: str = None,
    ):
        """Complete a tool call log via the memory MCP server. No-op if call_id is None."""
        if call_id is None:
            return
        try:
            from core.mcp_client import call_mcp_tool
            call_mcp_tool("complete_tool_call", {
                "call_id": call_id,
                "status": status,
                "result": result,
                "duration_ms": duration_ms,
                "error": error,
            })
        except Exception:
            pass

    def _execute_tool(self, tool_name: str, params: dict):
        from tools.base import ToolResult

        if tool_name == "synthesize_daily_plan":
            return self._synthesize_daily_plan()

        params = params or {}
        local_name = MCP_TO_LOCAL.get(tool_name, tool_name)
        tool = ALL_TOOLS.get(local_name)

        if tool_name in PREFER_MCP:
            result = self._execute_mcp(tool_name, params)
            if not result.metadata.get("server_offline"):
                return result
            # Local tools don't accept MCP-only params like new_tab
            accepted = tool.parameters_schema.get("properties", {})
            params = {k: v for k, v in params.items() if k in accepted}
        elif not tool:
            return self._execute_mcp(tool_name, params)

        try:
            return tool.timed_execute(**params)
        except TypeError as e:
            return ToolResult(success=False, tool_name=tool_name,
                              error=f"Invalid parameters: {e}")

    def _execute_mcp(self, tool_name: str, params: dict):
        from tools.base import ToolResult
        from core.mcp_client import call_mcp_tool

        try:
            data = call_mcp_tool(tool_name, params)
            return ToolResult(
                success=data.get("success", False),
                tool_name=tool_name,
                output=data.get("output"),
                message=data.get("message") or f"{tool_name} completed",
                error=data.get("error", ""),
            )
        except ConnectionError:
            return ToolResult(
                success=True,
                tool_name=tool_name,
                message=f"⏭  {tool_name} skipped (server offline)",
                output=None,
                metadata={"server_offline": True},
            )
        except Exception as e:
            return ToolResult(success=False, tool_name=tool_name, error=str(e))

    def _synthesize_daily_plan(self):
        """Synthesize a daily plan from accumulated tool results."""
        from tools.base import ToolResult
        from groq import Groq
        from config.settings import settings

        events_result = self.wm.get_tool_result("get_today_events")
        goals_result  = self.wm.get_tool_result("list_goals")

        # Workflows (e.g. end_of_day) call this without earlier fetch steps —
        # load the inputs directly so the plan isn't generic.
        if events_result is None:
            events_result = self._execute_mcp("get_today_events", {}).output
        if goals_result is None:
            goals_result = self._execute_mcp("list_goals", {}).output

        events = []
        if isinstance(events_result, dict):
            events = events_result.get("events", [])

        goals = []
        if isinstance(goals_result, list):
            goals = goals_result
        elif isinstance(goals_result, dict):
            goals = goals_result.get("output", [])

        client = Groq(api_key=settings.groq_api_key)

        prompt = f"""You are AuraOS, an AI personal computing environment.

The user asked: "what should I work on today?"

Today's calendar events:
{json.dumps(events, indent=2) if events else "No events today."}

Active goals:
{json.dumps(goals, indent=2) if goals else "No goals set."}

Write a concise, prioritized daily plan for the user. Be specific and actionable.
Format it clearly — lead with the top 3 priorities, note any time blocks from calendar,
and flag anything that should be done first. Keep it under 150 words.
Use plain text with simple "-" bullets: no tables or markdown (it is shown in a text overlay)."""

        try:
            response = client.chat.completions.create(
                model=settings.planner_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=1024,  # headroom: reasoning models spend tokens before answering
                temperature=0.3,
            )
            plan_text = response.choices[0].message.content.strip()
            return ToolResult(
                success=True,
                tool_name="synthesize_daily_plan",
                message=f"\n{'─'*48}\n{plan_text}\n{'─'*48}",
                output={"plan": plan_text},
            )
        except Exception as e:
            return ToolResult(
                success=False,
                tool_name="synthesize_daily_plan",
                error=f"Synthesis failed: {e}",
            )

    def _format_list_output(self, tool_name: str, items: list) -> Generator[str, None, None]:
        """Surface list-returning tools (GitHub, goals) inline, capped at 10 rows."""
        formatters = {
            "list_repos":         lambda r: f"{r['full_name']}" + (f" — {r['description']}" if r.get("description") else ""),
            "get_open_issues":    lambda i: f"#{i['number']} {i['title']}",
            "get_open_prs":       lambda p: f"#{p['number']} {p['title']} ({p['author']})",
            "get_recent_commits": lambda c: f"{c['sha']} {c['message']}",
            "list_goals":         lambda g: f"[P{g.get('priority', '?')}] {g['title']}",
        }
        fmt = formatters.get(tool_name)
        if not fmt:
            return
        for item in items[:10]:
            yield f"     • {fmt(item)}\n"
        if len(items) > 10:
            yield f"     … and {len(items) - 10} more\n"

    def _format_output(self, tool_name: str, output: dict) -> Generator[str, None, None]:
        """Surface useful output fields inline."""
        if tool_name == "detect_project":
            types = ", ".join(output.get("project_types", []))
            branch = output.get("git", {}).get("branch", "")
            yield f"     Project type: {types}"
            if branch:
                yield f" · Branch: {branch}"
            yield "\n"
            commits = output.get("git", {}).get("recent_commits", [])
            if commits:
                yield f"     Last commit: {commits[0]}\n"

        elif tool_name == "list_recent_files":
            files = output.get("files", [])[:5]
            if files:
                yield "     Recent files:\n"
                for f in files:
                    yield f"       • {f['name']}\n"

        elif tool_name in ("open_url", "search_web"):
            if output.get("title"):
                yield f"     Page: {output['title']}\n"

        elif tool_name == "get_page_text":
            lines = [l.strip() for l in output.get("text", "").splitlines() if l.strip()]
            preview = "\n".join(f"     {l}" for l in lines[:40])
            if preview:
                yield f"{preview}\n"
            if len(lines) > 40 or output.get("truncated"):
                yield "     …\n"

        elif tool_name == "open_vscode_workspace":
            opened = output.get("files_opened", [])
            if opened:
                yield f"     Opened: {', '.join(opened)}\n"