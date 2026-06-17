"""
AuraOS · GitHub MCP Server
Port: 8105
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import urllib.request
import urllib.error
import uvicorn
from fastapi import FastAPI
from pydantic import BaseModel
from typing import Any

from config.settings import settings
import ssl
import certifi

# Permanent fix for macOS Python SSL certificate verification
ssl._create_default_https_context = lambda: ssl.create_default_context(cafile=certifi.where())
app = FastAPI(title="AuraOS GitHub Server")
BASE = "https://api.github.com"


class ToolRequest(BaseModel):
    params: dict[str, Any] = {}


def _gh(endpoint: str) -> tuple[bool, Any]:
    if not settings.github_token:
        return False, "GITHUB_TOKEN not set in .env"
    
    ctx = ssl.create_default_context(cafile=certifi.where())
    
    req = urllib.request.Request(
        f"{BASE}{endpoint}",
        headers={
            "Authorization": f"Bearer {settings.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
            return True, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return False, f"GitHub API error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Network error: {e.reason}"


@app.get("/health")
def health():
    return {"status": "ok", "server": "github"}


@app.post("/tools/list_repos")
def list_repos(req: ToolRequest):
    ok, data = _gh("/user/repos?sort=pushed&per_page=20&type=owner")
    if not ok:
        return {"success": False, "error": data}
    repos = [
        {
            "name": r["name"], "full_name": r["full_name"],
            "description": r.get("description"), "language": r.get("language"),
            "open_issues": r["open_issues_count"], "pushed_at": r["pushed_at"],
            "url": r["html_url"],
        }
        for r in data
    ]
    return {"success": True, "output": repos}


@app.post("/tools/get_open_issues")
def get_open_issues(req: ToolRequest):
    repo = req.params.get("repo")
    ok, data = _gh(f"/repos/{repo}/issues?state=open&per_page=20")
    if not ok:
        return {"success": False, "error": data}
    issues = [
        {
            "number": i["number"], "title": i["title"],
            "labels": [l["name"] for l in i.get("labels", [])],
            "created": i["created_at"], "url": i["html_url"],
        }
        for i in data if "pull_request" not in i
    ]
    return {"success": True, "output": issues}


@app.post("/tools/get_open_prs")
def get_open_prs(req: ToolRequest):
    repo = req.params.get("repo")
    ok, data = _gh(f"/repos/{repo}/pulls?state=open&per_page=10")
    if not ok:
        return {"success": False, "error": data}
    prs = [
        {
            "number": p["number"], "title": p["title"],
            "author": p["user"]["login"], "created": p["created_at"],
            "url": p["html_url"],
        }
        for p in data
    ]
    return {"success": True, "output": prs}


@app.post("/tools/get_recent_commits")
def get_recent_commits(req: ToolRequest):
    repo = req.params.get("repo")
    n = req.params.get("n", 10)
    ok, data = _gh(f"/repos/{repo}/commits?per_page={n}")
    if not ok:
        return {"success": False, "error": data}
    commits = [
        {
            "sha": c["sha"][:7],
            "message": c["commit"]["message"].splitlines()[0],
            "author": c["commit"]["author"]["name"],
            "date": c["commit"]["author"]["date"],
        }
        for c in data
    ]
    return {"success": True, "output": commits}


@app.post("/tools/get_repo_info")
def get_repo_info(req: ToolRequest):
    repo = req.params.get("repo")
    ok, data = _gh(f"/repos/{repo}")
    if not ok:
        return {"success": False, "error": data}
    return {"success": True, "output": {
        "name": data["name"], "description": data.get("description"),
        "language": data.get("language"), "stars": data["stargazers_count"],
        "open_issues": data["open_issues_count"],
        "default_branch": data["default_branch"],
        "pushed_at": data["pushed_at"], "url": data["html_url"],
    }}


if __name__ == "__main__":
    print(f"[github-server] starting on port {settings.port_github}")
    uvicorn.run(app, host="127.0.0.1", port=settings.port_github, log_level="warning")