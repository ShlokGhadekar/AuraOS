"""
AuraOS · Tool Base Class
========================
Every tool in AuraOS must subclass AuraTool.

The contract enforces:
  - A machine-readable JSON schema for the LLM planner
  - Reversibility and dry-run flags so the executor can gate safely
  - A consistent execute() signature that returns ToolResult
  - Estimated duration for UX (streaming spinners)

Design decision: tools are synchronous. The executor runs them
in asyncio.to_thread() when needed. Keeps tool code simple.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


# ─────────────────────────────────────────────────────────────
# ToolResult — every tool returns one of these
# ─────────────────────────────────────────────────────────────

@dataclass
class ToolResult:
    success: bool
    tool_name: str
    output: Any = None           # structured output (dict, list, str)
    message: str = ""            # human-readable status line for streaming
    error: str = ""              # error detail if success=False
    duration_ms: int = 0
    metadata: dict = field(default_factory=dict)

    def __str__(self) -> str:
        if self.success:
            return self.message or f"✓ {self.tool_name}"
        return f"✗ {self.tool_name}: {self.error}"


# ─────────────────────────────────────────────────────────────
# AuraTool — base class
# ─────────────────────────────────────────────────────────────

class AuraTool(ABC):
    """
    Subclass this for every AuraOS tool.

    Minimal implementation:
        class OpenApp(AuraTool):
            name = "open_app"
            description = "Launch a macOS application by name"
            parameters_schema = {
                "type": "object",
                "properties": {
                    "app_name": {"type": "string", "description": "Application name, e.g. 'Visual Studio Code'"}
                },
                "required": ["app_name"]
            }

            def execute(self, app_name: str) -> ToolResult:
                ...
    """

    # ── Required class attributes ──────────────────────────────

    #: Unique snake_case identifier used in plans and logs
    name: str = ""

    #: Written for the LLM planner — describe WHAT it does and WHEN to use it
    description: str = ""

    #: JSON Schema for parameters — validated before execute() is called
    parameters_schema: dict = field(default_factory=dict)

    # ── Optional class attributes ──────────────────────────────

    #: Rough expected duration — used to show spinners of appropriate length
    estimated_duration_ms: int = 500

    #: If True, executor will ask user confirmation before running
    requires_confirmation: bool = False

    #: If True, this action can be undone (enables undo tracking)
    is_reversible: bool = True

    #: If True, execute(dry_run=True) previews without side effects
    dry_run_supported: bool = False

    #: Human-readable category for display grouping
    category: str = "general"


    # ── Abstract ──────────────────────────────────────────────

    @abstractmethod
    def execute(self, **kwargs) -> ToolResult:
        """
        Run the tool. kwargs are validated against parameters_schema.
        Never raises — catch all exceptions and return ToolResult(success=False).
        """
        ...


    # ── Helpers available to subclasses ───────────────────────

    def _result(
        self,
        success: bool,
        message: str = "",
        output: Any = None,
        error: str = "",
        duration_ms: int = 0,
        metadata: dict = None,
    ) -> ToolResult:
        return ToolResult(
            success=success,
            tool_name=self.name,
            output=output,
            message=message,
            error=error,
            duration_ms=duration_ms,
            metadata=metadata or {},
        )

    def ok(self, message: str, output: Any = None, duration_ms: int = 0, metadata: dict = None) -> ToolResult:
        return self._result(True, message=message, output=output, duration_ms=duration_ms, metadata=metadata)

    def fail(self, error: str, duration_ms: int = 0) -> ToolResult:
        return self._result(False, error=error, duration_ms=duration_ms)

    def timed_execute(self, **kwargs) -> ToolResult:
        """Wraps execute() and fills in duration_ms automatically."""
        start = time.monotonic()
        try:
            result = self.execute(**kwargs)
        except Exception as e:
            result = self.fail(error=str(e))
        result.duration_ms = int((time.monotonic() - start) * 1000)
        return result

    def to_llm_spec(self) -> dict:
        """Return the tool spec in Claude tool-calling format."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.parameters_schema,
        }

    def __repr__(self) -> str:
        return f"<AuraTool:{self.name}>"