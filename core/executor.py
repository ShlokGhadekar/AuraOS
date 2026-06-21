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
    ):
        self.session_id = session_id
        self.wm = wm
        self.mem = mem  # kept for reads only — writes go through MCP

    def run(self, plan: list[dict]) -> Generator[str, None, None]:
        """
        Execute a plan step by step.
        Yields human-readable progress strings.
        """
        yield "\n"

        for i, step in enumerate(plan):
            tool_name = step.get("tool", "")
            params    = step.get("params", {})
            needs_confirm = step.get("requires_confirmation", False)

            display = TOOL_DISPLAY.get(tool_name, f"⚙️  {tool_name}")
            yield f"{display}...\n"

            if needs_confirm:
                yield f"  ⚠️  This step requires confirmation: {step.get('reason', '')}\n"
                yield "  Proceeding automatically in CLI mode.\n"

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

        # Try local tool first
        local_name = MCP_TO_LOCAL.get(tool_name, tool_name)
        tool = ALL_TOOLS.get(local_name)
        if tool:
            try:
                return tool.timed_execute(**params)
            except TypeError as e:
                return ToolResult(success=False, tool_name=tool_name,
                                  error=f"Invalid parameters: {e}")

        # Fall through to MCP client
        try:
            from core.mcp_client import call_mcp_tool
            data = call_mcp_tool(tool_name, params)
            return ToolResult(
                success=data.get("success", False),
                tool_name=tool_name,
                output=data.get("output"),
                message=data.get("message", f"{tool_name} completed"),
                error=data.get("error", ""),
            )
        except ConnectionError:
            return ToolResult(
                success=True,
                tool_name=tool_name,
                message=f"⏭  {tool_name} skipped (server offline)",
                output=None,
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
and flag anything that should be done first. Keep it under 150 words."""

        try:
            response = client.chat.completions.create(
                model=settings.planner_model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=300,
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

        elif tool_name == "open_vscode_workspace":
            opened = output.get("files_opened", [])
            if opened:
                yield f"     Opened: {', '.join(opened)}\n"