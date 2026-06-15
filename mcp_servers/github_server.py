"""
AuraOS · GitHub MCP Server
Port: 8105

Read-only. Uses GitHub REST API.
Requires GITHUB_TOKEN in .env (classic PAT, repo scope).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import json
import urllib.request
import urllib.error
from mcp.server.fastmcp import FastMCP
from config.settings import settings

mcp = FastMCP("aura-github", port=settings.port_github)

BASE = "https://api.github.com"


def _gh(endpoint: str) -> tuple[bool, dict | str]:
    """Make a GitHub API GET request."""
    if not settings.github_token:
        return False, "GITHUB_TOKEN not set in .env"
    url = f"{BASE}{endpoint}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {settings.github_token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return True, json.loads(resp.read())
    except urllib.error.HTTPError as e:
        return False, f"GitHub API error {e.code}: {e.reason}"
    except urllib.error.URLError as e:
        return False, f"Network error: {e.reason}"


@mcp.tool()
def list_repos() -> str:
    """
    List the authenticated user's GitHub repositories.
    Returns name, description, language, open issues count, last push.
    """
    ok, data = _gh("/user/repos?sort=pushed&per_page=20&type=owner")
    if not ok:
        return json.dumps({"success": False, "error": data})
    repos = [
        {
            "name":         r["name"],
            "full_name":    r["full_name"],
            "description":  r.get("description"),
            "language":     r.get("language"),
            "open_issues":  r["open_issues_count"],
            "pushed_at":    r["pushed_at"],
            "url":          r["html_url"],
        }
        for r in data
    ]
    return json.dumps({"success": True, "output": repos})


@mcp.tool()
def get_open_issues(repo: str) -> str:
    """
    Get open issues for a repo ('owner/repo').
    Use to surface what needs attention when resuming a project.
    """
    ok, data = _gh(f"/repos/{repo}/issues?state=open&per_page=20")
    if not ok:
        return json.dumps({"success": False, "error": data})
    issues = [
        {
            "number":  i["number"],
            "title":   i["title"],
            "labels":  [l["name"] for l in i.get("labels", [])],
            "created": i["created_at"],
            "url":     i["html_url"],
        }
        for i in data
        if "pull_request" not in i   # exclude PRs from issues list
    ]
    return json.dumps({"success": True, "output": issues})


@mcp.tool()
def get_open_prs(repo: str) -> str:
    """
    Get open pull requests for a repo ('owner/repo').
    """
    ok, data = _gh(f"/repos/{repo}/pulls?state=open&per_page=10")
    if not ok:
        return json.dumps({"success": False, "error": data})
    prs = [
        {
            "number":  p["number"],
            "title":   p["title"],
            "author":  p["user"]["login"],
            "created": p["created_at"],
            "url":     p["html_url"],
        }
        for p in data
    ]
    return json.dumps({"success": True, "output": prs})


@mcp.tool()
def get_recent_commits(repo: str, n: int = 10) -> str:
    """
    Get the N most recent commits on the default branch.
    Use to understand what was last worked on in a project.
    """
    ok, data = _gh(f"/repos/{repo}/commits?per_page={n}")
    if not ok:
        return json.dumps({"success": False, "error": data})
    commits = [
        {
            "sha":     c["sha"][:7],
            "message": c["commit"]["message"].splitlines()[0],
            "author":  c["commit"]["author"]["name"],
            "date":    c["commit"]["author"]["date"],
        }
        for c in data
    ]
    return json.dumps({"success": True, "output": commits})


@mcp.tool()
def get_repo_info(repo: str) -> str:
    """
    Get metadata for a repo ('owner/repo'): description, language,
    stars, open issues, default branch.
    """
    ok, data = _gh(f"/repos/{repo}")
    if not ok:
        return json.dumps({"success": False, "error": data})
    info = {
        "name":            data["name"],
        "description":     data.get("description"),
        "language":        data.get("language"),
        "stars":           data["stargazers_count"],
        "open_issues":     data["open_issues_count"],
        "default_branch":  data["default_branch"],
        "pushed_at":       data["pushed_at"],
        "url":             data["html_url"],
    }
    return json.dumps({"success": True, "output": info})


if __name__ == "__main__":
    print(f"[github-server] starting on port {settings.port_github}")
    mcp.run(transport="sse")
