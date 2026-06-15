"""
AuraOS · Calendar MCP Server
Port: 8104

Read-only. Uses icalBuddy to query macOS Calendar.
Install icalBuddy: brew install ical-buddy
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import subprocess
from datetime import date, timedelta
from mcp.server.fastmcp import FastMCP
from config.settings import settings

mcp = FastMCP("aura-calendar", port=settings.port_calendar)


def _ical(args: list[str]) -> tuple[bool, str]:
    """Run icalBuddy with args. Returns (success, output)."""
    try:
        result = subprocess.run(
            ["icalBuddy"] + args,
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0, result.stdout.strip()
    except FileNotFoundError:
        return False, "icalBuddy not found. Install with: brew install ical-buddy"
    except subprocess.TimeoutExpired:
        return False, "icalBuddy timed out"


@mcp.tool()
def get_today_events() -> str:
    """
    Get all calendar events for today.
    Use when answering 'what's on my schedule?' or 'what should I work on today?'
    """
    ok, output = _ical(["eventsToday"])
    return json.dumps({
        "success": ok,
        "output": {"date": str(date.today()), "events": output},
        "error": "" if ok else output,
    })


@mcp.tool()
def get_events_for_range(days_ahead: int = 7) -> str:
    """
    Get calendar events for the next N days (default 7).
    Use for planning queries like 'what do I have this week?'
    """
    today = date.today()
    until = today + timedelta(days=days_ahead)
    ok, output = _ical([
        "eventsFrom:" + today.strftime("%Y-%m-%d"),
        "to:" + until.strftime("%Y-%m-%d"),
    ])
    return json.dumps({
        "success": ok,
        "output": {
            "from": str(today),
            "to": str(until),
            "events": output,
        },
        "error": "" if ok else output,
    })


@mcp.tool()
def get_upcoming_deadlines(days_ahead: int = 14) -> str:
    """
    Get reminders/tasks with due dates in the next N days.
    Used to surface deadlines when prioritizing work.
    """
    today = date.today()
    until = today + timedelta(days=days_ahead)
    ok, output = _ical([
        "tasksDueBefore:" + until.strftime("%Y-%m-%d"),
        "+showTaskNotes",
    ])
    return json.dumps({
        "success": ok,
        "output": {"deadlines": output},
        "error": "" if ok else output,
    })


if __name__ == "__main__":
    print(f"[calendar-server] starting on port {settings.port_calendar}")
    mcp.run(transport="sse")
