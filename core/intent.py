"""
AuraOS · Intent Classifier (Groq)
"""
import json
from groq import Groq
from config.settings import settings

client = Groq(api_key=settings.groq_api_key)

INTENTS = {
    "continue_project":  "User wants to resume work on a specific project",
    "open_project":      "User wants to open a project without context restoration",
    "daily_planning":    "User wants to know what to work on today",
    "dsa_session":       "User wants to start a DSA / LeetCode study session",
    "open_app":          "User wants to open a specific application",
    "open_file":         "User wants to open a specific file",
    "github_query":      "User is asking about GitHub repos, issues, or PRs",
    "calendar_query":    "User is asking about their schedule or deadlines",
    "memory_query":      "User is asking about past sessions or what they worked on",
    "general_task":      "Multi-step task that doesn't fit above categories",
    "unknown":           "Cannot determine intent",
}

SYSTEM = """You are the intent classifier for AuraOS, an AI-powered personal computing environment.

Classify the user's input into exactly one intent from this list:
{intents}

Respond with ONLY a JSON object — no explanation, no markdown fences:
{{
  "intent": "<intent_key>",
  "confidence": <0.0-1.0>,
  "project_hint": "<project name if mentioned, else null>",
  "reasoning": "<one sentence>"
}}""".format(intents="\n".join(f"- {k}: {v}" for k, v in INTENTS.items()))


def classify_intent(user_input: str) -> dict:
    try:
        response = client.chat.completions.create(
            model=settings.classifier_model,
            messages=[
                {"role": "system", "content": SYSTEM},
                {"role": "user",   "content": user_input},
            ],
            max_tokens=200,
            temperature=0.1,
        )
        raw = response.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        return json.loads(raw.strip())
    except Exception as e:
        return {
            "intent": "general_task",
            "confidence": 0.0,
            "project_hint": None,
            "reasoning": f"Classification failed: {e}",
        }