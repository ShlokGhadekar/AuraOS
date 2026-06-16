"""
AuraOS · Session Summarizer (Groq)
"""
import json
from groq import Groq
from memory.working import WorkingMemory
from config.settings import settings

client = Groq(api_key=settings.groq_api_key)

SYSTEM = """You are the session summarizer for AuraOS.

Given this session data, extract a concise context snapshot.
Respond with ONLY a JSON object — no explanation, no markdown fences:
{
  "current_goal": "<what the user is trying to achieve, or null>",
  "last_action": "<what was done this session, one sentence>",
  "next_step": "<most logical next action, or null>",
  "open_questions": ["<unresolved question>"],
  "relevant_files": ["<relative file path>"],
  "blockers": ["<anything blocking progress>"],
  "summary": "<2-3 sentence human-readable summary>"
}

Be specific: 'Implemented TF-IDF baseline' not 'worked on project'.
If a field has no data, use null or []."""


def summarize_session(wm: WorkingMemory) -> dict | None:
    if not wm.active_project_id:
        return None
    if len(wm.conversation) < 2:
        return None

    data = wm.to_snapshot_dict()
    transcript = f"""Project: {data['project_id']}
User request: {data['raw_input']}
Intent: {data['intent']}
Tools executed: {', '.join(data['completed_tools']) or 'none'}
Tool results:
{json.dumps(data['tool_results'], indent=2, default=str)[:2000]}
Previous snapshot:
{json.dumps(data['loaded_snapshot'], indent=2, default=str)[:500] if data['loaded_snapshot'] else 'none'}"""

    try:
        response = client.chat.completions.create(
            model=settings.classifier_model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": transcript},
            ],
            max_tokens=500,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw.strip())
        for key in ("open_questions", "relevant_files", "blockers"):
            if not isinstance(result.get(key), list):
                result[key] = []
        return result
    except Exception as e:
        return {
            "summary": f"Session: {data['raw_input']}",
            "last_action": ", ".join(data["completed_tools"]) or "no tools executed",
            "current_goal": None,
            "next_step": None,
            "open_questions": [],
            "relevant_files": [],
            "blockers": [f"Summarizer error: {e}"],
        }