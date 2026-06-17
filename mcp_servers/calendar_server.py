"""
AuraOS · Calendar MCP Server
Port: 8104
Uses native Swift EventKit bridge instead of icalBuddy.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import subprocess
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any
from datetime import date, timedelta

from config.settings import settings

app = FastAPI(title="AuraOS Calendar Server")
BRIDGE = Path(__file__).parent.parent / "scripts" / "calendar_bridge"


class ToolRequest(BaseModel):
    params: dict[str, Any] = {}


def _bridge(command: str, arg: str = None) -> tuple[bool, Any]:
    cmd = [str(BRIDGE), command]
    if arg:
        cmd.append(arg)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        if result.returncode != 0:
            return False, result.stdout.strip() or result.stderr.strip()
        data = json.loads(result.stdout.strip())
        if isinstance(data, dict) and "error" in data:
            return False, data["error"]
        return True, data
    except FileNotFoundError:
        return False, "Calendar bridge not found. Run: swiftc scripts/calendar_bridge.swift -o scripts/calendar_bridge"
    except subprocess.TimeoutExpired:
        return False, "Calendar bridge timed out"
    except json.JSONDecodeError as e:
        return False, f"Invalid JSON from bridge: {e}"


@app.get("/health")
def health():
    return {"status": "ok", "server": "calendar"}


@app.post("/tools/get_today_events")
def get_today_events(req: ToolRequest):
    ok, data = _bridge("today")
    return {
        "success": ok,
        "output": {"date": str(date.today()), "events": data if ok else []},
        "error": "" if ok else data,
    }


@app.post("/tools/get_events_for_range")
def get_events_for_range(req: ToolRequest):
    days = str(req.params.get("days_ahead", 7))
    ok, data = _bridge("range", days)
    return {
        "success": ok,
        "output": {
            "from": str(date.today()),
            "to": str(date.today() + timedelta(days=int(days))),
            "events": data if ok else [],
        },
        "error": "" if ok else data,
    }


@app.post("/tools/get_upcoming_deadlines")
def get_upcoming_deadlines(req: ToolRequest):
    days = str(req.params.get("days_ahead", 14))
    ok, data = _bridge("range", days)
    return {
        "success": ok,
        "output": {"deadlines": data if ok else []},
        "error": "" if ok else data,
    }


if __name__ == "__main__":
    print(f"[calendar-server] starting on port {settings.port_calendar}")
    uvicorn.run(app, host="127.0.0.1", port=settings.port_calendar, log_level="warning")