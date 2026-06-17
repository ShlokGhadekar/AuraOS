"""
AuraOS · Planner (Groq)
"""
import json
from groq import Groq
from config.settings import settings

client = Groq(api_key=settings.groq_api_key)

AVAILABLE_TOOLS = """
FILESYSTEM TOOLS:
- detect_project(name_or_path) → project type, structure, recent files, git info
- list_recent_files(path, n=10) → recently modified files
- list_projects() → all projects in ~/Documents/

MACOS TOOLS:
- launch_app(app_name) → open any macOS application
- open_vscode_workspace(path, files=[], new_window=True) → open project in VS Code
- open_file_with_app(path, app_name=None) → open a file
- send_notification(title, message) → macOS notification

MEMORY TOOLS:
- get_project_context(project_id) → snapshot + sessions + goals for a project
- get_current_snapshot(project_id) → current_goal, last_action, next_step, blockers
- identify_project(user_input) → fuzzy match user input to a project_id
- search_projects_semantic(query) → find projects by natural language
- list_goals(project_id=None) → active goals

CALENDAR TOOLS:
- get_today_events() → today's calendar events
- get_upcoming_deadlines(days_ahead=14) → upcoming deadlines

GITHUB TOOLS:
- list_repos() → user's GitHub repos
- get_open_issues(repo) → open issues for owner/repo
- get_recent_commits(repo, n=10) → recent commits
"""

SYSTEM = """You are the task planner for AuraOS, an AI-powered personal computing environment on macOS.

Available tools:
{tools}

Rules:
1. Use the minimum tools needed — don't over-plan
2. Always load memory context BEFORE opening apps
3. For 'continue_project': identify_project → get_project_context → detect_project → open_vscode_workspace
4. For 'daily_planning': get_today_events → list_goals → synthesize_daily_plan
5. For destructive steps, set requires_confirmation=true
6. Never fabricate project paths — use detect_project to find them
7. For 'daily_planning' the LAST step must always be 'synthesize_daily_plan' with no params — this renders the final answer to the user

Respond with ONLY a JSON array — no explanation, no markdown fences:
[
  {{
    "step": 1,
    "tool": "<tool_name>",
    "params": {{}},
    "reason": "<why this step, one sentence>",
    "requires_confirmation": false,
    "status": "pending"
  }}
]""".format(tools=AVAILABLE_TOOLS)


def build_plan(user_input: str, intent: dict, context: dict = None) -> list[dict]:
    try:
        user_message = f"""User input: "{user_input}"

Intent: {intent.get('intent')} (confidence: {intent.get('confidence', 0):.0%})
Project hint: {intent.get('project_hint') or 'none'}
Context: {json.dumps(context or {}, indent=2, default=str)[:1500]}

Build the minimal plan to fulfill this request."""

        response = client.chat.completions.create(
            model=settings.planner_model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": user_message},
            ],
            max_tokens=1000,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        plan = json.loads(raw.strip())
        for i, step in enumerate(plan):
            step.setdefault("step", i + 1)
            step.setdefault("status", "pending")
            step.setdefault("requires_confirmation", False)
            step.setdefault("reason", "")
        return plan
    except Exception as e:
        return [{
            "step": 1,
            "tool": "general_task",
            "params": {"input": user_input},
            "reason": f"Plan generation failed ({e}), falling back",
            "requires_confirmation": False,
            "status": "pending",
        }]


def format_plan_for_display(plan: list[dict]) -> str:
    lines = ["📋 Plan:"]
    for step in plan:
        confirm = " ⚠️  (needs confirmation)" if step.get("requires_confirmation") else ""
        lines.append(f"  {step['step']}. {step['tool']}{confirm}")
        if step.get("reason"):
            lines.append(f"     → {step['reason']}")
    return "\n".join(lines)