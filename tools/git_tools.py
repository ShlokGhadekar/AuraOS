"""
AuraOS · Git Tools
==================
Local git operations for end-of-day wrap and project kickoff.
"""
import subprocess
from pathlib import Path
from tools.base import AuraTool, ToolResult


def _git(args: list[str], cwd: str) -> tuple[int, str, str]:
    result = subprocess.run(
        ["git"] + args,
        capture_output=True, text=True,
        cwd=str(Path(cwd).expanduser()), timeout=30,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


class GitStatus(AuraTool):
    name = "git_status"
    description = "Get git status of a project directory."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Project directory path"}
        },
        "required": ["path"],
    }
    is_reversible = True
    category = "git"

    def execute(self, path: str) -> ToolResult:
        code, out, err = _git(["status", "--short"], path)
        if code != 0:
            return self.fail(error=f"git status failed: {err}")
        changed = [l for l in out.splitlines() if l.strip()]
        return self.ok(
            message=f"{len(changed)} changed files",
            output={"changed_files": changed, "clean": len(changed) == 0},
        )


class GitCommit(AuraTool):
    name = "git_commit"
    description = "Stage all changes and commit with a message."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path":    {"type": "string"},
            "message": {"type": "string", "description": "Commit message"},
        },
        "required": ["path", "message"],
    }
    requires_confirmation = True
    is_reversible = False
    category = "git"

    def execute(self, path: str, message: str) -> ToolResult:
        # Stage all
        code, _, err = _git(["add", "-A"], path)
        if code != 0:
            return self.fail(error=f"git add failed: {err}")
        # Commit
        code, out, err = _git(["commit", "-m", message], path)
        if code != 0:
            if "nothing to commit" in err or "nothing to commit" in out:
                return self.ok(message="Nothing to commit — working tree clean")
            return self.fail(error=f"git commit failed: {err}")
        return self.ok(
            message=f"Committed: {message}",
            output={"message": message, "output": out},
        )


class GitInitAndPush(AuraTool):
    name = "git_init_and_push"
    description = "Initialize a git repo and push to a remote."
    parameters_schema = {
        "type": "object",
        "properties": {
            "path":   {"type": "string"},
            "remote": {"type": "string", "description": "Remote URL"},
        },
        "required": ["path", "remote"],
    }
    is_reversible = False
    category = "git"

    def execute(self, path: str, remote: str) -> ToolResult:
        for args in [["init"], ["add", "-A"], ["commit", "-m", "Initial commit"]]:
            code, _, err = _git(args, path)
            if code != 0 and "nothing to commit" not in err:
                return self.fail(error=f"git {args[0]} failed: {err}")
        code, _, err = _git(["remote", "add", "origin", remote], path)
        code, _, err = _git(["push", "-u", "origin", "main"], path)
        if code != 0:
            return self.fail(error=f"git push failed: {err}")
        return self.ok(message=f"Pushed to {remote}")


GIT_TOOLS = [GitStatus(), GitCommit(), GitInitAndPush()]
GIT_TOOLS_BY_NAME = {t.name: t for t in GIT_TOOLS}