"""
AuraOS · Executor
=================
Runs the plan produced by the planner.
Streams progress tokens to the caller as it goes.
Logs every tool call to episodic memory.

Key design decisions:
- Yields strings (progress tokens) via a generator
- Each tool call is logged to SQLite before + after execution
- requires_confirmation steps pause and yield a confirmation prompt
- Tool results are stored in WorkingMemory for the summarizer
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
from config.settings import settings

# All tools the executor knows about
ALL_TOOLS = {**MACOS_TOOLS_BY_NAME, **FILESYSTEM_TOOLS_BY_NAME}

MCP_TO_LOCAL = {
    "launch_app":            "open_app",
    "open_file_with_app":    "open_file",
    "open_vscode_workspace": "open_vscode_workspace",
    "send_notification":     "send_notification",
    "detect_project":        "detect_project",
    "list_recent_files":     "list_recent_files",
    "list_projects":         "list_projects",
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
        self.mem = mem

    def run(self, plan: list[dict]) -> Generator[str, None, None]:
        """
        Execute a plan step by step.
        Yields human-readable progress strings.
        """
        yield "\n"
        total = len(plan)

        for i, step in enumerate(plan):
            tool_name = step.get("tool", "")
            params    = step.get("params", {})
            needs_confirm = step.get("requires_confirmation", False)

            display = TOOL_DISPLAY.get(tool_name, f"⚙️  {tool_name}")
            yield f"{display}...\n"

            # Confirmation gate
            if needs_confirm:
                yield f"  ⚠️  This step requires confirmation: {step.get('reason', '')}\n"
                yield "  Type 'yes' to proceed or 'skip' to skip this step.\n"
                # In CLI mode, we auto-proceed. The overlay will handle this interactively.
                # For now, proceed automatically (Phase 1 scope).

            # Log to episodic memory
            call_log = self.mem.log_tool_call(
                session_id=self.session_id,
                tool_name=tool_name,
                parameters=params,
            )

            # Execute the tool
            start = time.monotonic()
            result = self._execute_tool(tool_name, params)
            duration_ms = int((time.monotonic() - start) * 1000)

            # Update plan step status
            self.wm.mark_step_done(i, result=result.output if result else None) \
                if (result and result.success) \
                else self.wm.mark_step_failed(i, error=result.error if result else "unknown")

            # Log result to episodic memory
            self.mem.complete_tool_call(
                call_log.id,
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
                # Surface key output fields
                if result.output and isinstance(result.output, dict):
                    yield from self._format_output(tool_name, result.output)
            else:
                error = result.error if result else "Tool not found"
                yield f"  ✗ Failed: {error}\n"
                # Non-fatal: continue with remaining steps

        yield "\n✅ Done.\n"

    def _execute_tool(self, tool_name: str, params: dict):
        local_name = MCP_TO_LOCAL.get(tool_name, tool_name)
        tool = ALL_TOOLS.get(local_name)
        if tool is None:
            from tools.base import ToolResult
            # Graceful skip for MCP-only tools
            MCP_ONLY = {
                "get_today_events", "get_upcoming_deadlines",
                "get_project_context", "get_current_snapshot",
                "identify_project", "search_projects_semantic",
                "list_goals", "add_goal", "get_recent_sessions",
                "list_repos", "get_open_issues", "get_recent_commits",
                "get_repo_info", "save_context_snapshot",
            }
            if tool_name in MCP_ONLY:
                return ToolResult(
                    success=True,
                    tool_name=tool_name,
                    message=f"⏭  {tool_name} skipped (MCP server not running)",
                    output=None,
                )
            return ToolResult(
                success=False,
                tool_name=tool_name,
                error=f"Tool '{tool_name}' not found.",
            )
        try:
            return tool.timed_execute(**params)
        except TypeError as e:
            from tools.base import ToolResult
            return ToolResult(
                success=False,
                tool_name=tool_name,
                error=f"Invalid parameters for {tool_name}: {e}",
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