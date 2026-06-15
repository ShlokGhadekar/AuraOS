"""
AuraOS · Filesystem Tools
==========================
Tools for project detection and file system inspection.

Project root: ~/Documents/

detect_project  — given a name or path, return structured project metadata
list_recent_files — find recently modified files in a project directory
find_project_root — walk up from a path to find the project root
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Optional

from tools.base import AuraTool, ToolResult


# ─────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────

PROJECTS_ROOT = Path("~/Documents").expanduser()

# Files/dirs that signal a project root
PROJECT_MARKERS = {
    "python":     ["pyproject.toml", "setup.py", "requirements.txt", "Pipfile"],
    "node":       ["package.json"],
    "rust":       ["Cargo.toml"],
    "go":         ["go.mod"],
    "java":       ["pom.xml", "build.gradle"],
    "git":        [".git"],
    "docker":     ["Dockerfile", "docker-compose.yml"],
    "notebook":   ["*.ipynb"],
}

# Files worth surfacing when restoring context
RELEVANT_FILE_PATTERNS = [
    "README*", "*.md", "*.py", "*.js", "*.ts", "*.rs",
    "*.ipynb", "*.yaml", "*.yml", "*.toml", "*.env.example",
]

# Directories to always ignore
IGNORE_DIRS = {
    ".git", ".venv", "venv", "node_modules", "__pycache__",
    ".pytest_cache", "dist", "build", ".mypy_cache", ".ruff_cache",
    "*.egg-info", ".DS_Store",
}


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _detect_project_type(path: Path) -> list[str]:
    """Return list of detected project types for a directory."""
    detected = []
    for ptype, markers in PROJECT_MARKERS.items():
        for marker in markers:
            if marker.startswith("*"):
                ext = marker[1:]
                if any(path.rglob(f"*{ext}")):
                    detected.append(ptype)
                    break
            elif (path / marker).exists():
                detected.append(ptype)
                break
    return detected or ["unknown"]


def _get_recent_files(
    directory: Path,
    n: int = 10,
    max_depth: int = 3,
) -> list[dict]:
    """Return the n most recently modified files, recursively up to max_depth."""
    files = []
    try:
        for entry in _walk_limited(directory, max_depth):
            if entry.is_file() and entry.name not in IGNORE_DIRS:
                try:
                    mtime = entry.stat().st_mtime
                    files.append({
                        "path": str(entry.relative_to(directory)),
                        "name": entry.name,
                        "mtime": mtime,
                        "size_bytes": entry.stat().st_size,
                    })
                except (OSError, PermissionError):
                    continue
    except PermissionError:
        return []

    files.sort(key=lambda f: f["mtime"], reverse=True)
    # Remove mtime from output (not useful to the LLM)
    for f in files:
        del f["mtime"]
    return files[:n]


def _walk_limited(directory: Path, max_depth: int):
    """os.walk but stops at max_depth."""
    for root, dirs, files in os.walk(directory):
        depth = len(Path(root).relative_to(directory).parts)
        if depth >= max_depth:
            dirs.clear()
        # Prune ignored dirs in-place
        dirs[:] = [d for d in dirs if d not in IGNORE_DIRS and not d.startswith(".")]
        for f in files:
            yield Path(root) / f


def _has_git(path: Path) -> bool:
    return (path / ".git").exists()


def _get_git_info(path: Path) -> dict:
    """Return basic git info if available."""
    import subprocess
    info = {}
    try:
        result = subprocess.run(
            ["git", "-C", str(path), "log", "--oneline", "-3"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            info["recent_commits"] = result.stdout.strip().splitlines()

        branch = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True, text=True, timeout=5
        )
        if branch.returncode == 0:
            info["branch"] = branch.stdout.strip()
    except Exception:
        pass
    return info


# ─────────────────────────────────────────────────────────────
# detect_project
# ─────────────────────────────────────────────────────────────

class DetectProject(AuraTool):
    """
    Given a project name or path, return structured metadata about it.

    Searches ~/Documents/ by default.
    Returns project type, structure, recent files, and git info.
    This is one of the first tools called when the user says
    "continue my <project>" — it feeds the planner with context
    about what kind of project it is and what's in it.
    """

    name = "detect_project"
    description = (
        "Detect and inspect a project by name or path. "
        "Returns project type (Python/Node/etc), directory structure, "
        "recently modified files, and git branch info. "
        "Use this first when the user mentions a project by name."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "name_or_path": {
                "type": "string",
                "description": (
                    "Project folder name (e.g. 'fake-news-detection') or "
                    "absolute/~ path (e.g. '~/Documents/fake-news-detection')"
                ),
            },
            "search_root": {
                "type": "string",
                "description": "Root directory to search in. Defaults to ~/Documents/",
            },
        },
        "required": ["name_or_path"],
    }
    estimated_duration_ms = 600
    is_reversible = True
    dry_run_supported = False
    category = "filesystem"

    def execute(
        self,
        name_or_path: str,
        search_root: str = None,
    ) -> ToolResult:
        root = Path(search_root).expanduser() if search_root else PROJECTS_ROOT
        project_path = self._resolve_path(name_or_path, root)

        if project_path is None:
            return self.fail(
                error=f"Project '{name_or_path}' not found in {root}. "
                      f"Check the name or add it to projects.yaml."
            )

        if not project_path.is_dir():
            return self.fail(error=f"Path exists but is not a directory: {project_path}")

        project_types = _detect_project_type(project_path)
        recent_files  = _get_recent_files(project_path, n=10)
        has_git       = _has_git(project_path)
        git_info      = _get_git_info(project_path) if has_git else {}

        # Top-level structure (non-hidden, non-ignored dirs and files)
        try:
            top_level = sorted([
                e.name for e in project_path.iterdir()
                if not e.name.startswith(".") and e.name not in IGNORE_DIRS
            ])
        except PermissionError:
            top_level = []

        output = {
            "name":          project_path.name,
            "path":          str(project_path),
            "project_types": project_types,
            "has_git":       has_git,
            "git":           git_info,
            "top_level":     top_level,
            "recent_files":  recent_files,
            "size_files":    len(recent_files),
        }

        type_str = ", ".join(project_types)
        branch = git_info.get("branch", "")
        branch_str = f" (branch: {branch})" if branch else ""
        return self.ok(
            message=f"Found {project_path.name} — {type_str} project{branch_str}",
            output=output,
        )

    def _resolve_path(self, name_or_path: str, root: Path) -> Optional[Path]:
        # Try as direct path first
        direct = Path(name_or_path).expanduser()
        if direct.exists():
            return direct

        # Try as name under root
        candidate = root / name_or_path
        if candidate.exists():
            return candidate

        # Fuzzy: case-insensitive match in root
        if root.exists():
            query = name_or_path.lower().replace("-", "").replace("_", "").replace(" ", "")
            for entry in root.iterdir():
                if entry.is_dir():
                    normalized = entry.name.lower().replace("-", "").replace("_", "").replace(" ", "")
                    if normalized == query or query in normalized:
                        return entry

        return None


# ─────────────────────────────────────────────────────────────
# list_recent_files
# ─────────────────────────────────────────────────────────────

class ListRecentFiles(AuraTool):
    """
    List recently modified files in a project directory.
    Useful for restoring context: "what was I working on?"
    """

    name = "list_recent_files"
    description = (
        "List the most recently modified files in a project directory. "
        "Use this to understand what the user was working on last session. "
        "Returns files sorted by modification time, newest first."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Project directory path",
            },
            "n": {
                "type": "integer",
                "description": "Number of files to return. Default: 10",
            },
            "max_depth": {
                "type": "integer",
                "description": "How deep to search. Default: 3",
            },
        },
        "required": ["path"],
    }
    estimated_duration_ms = 400
    is_reversible = True
    category = "filesystem"

    def execute(self, path: str, n: int = 10, max_depth: int = 3) -> ToolResult:
        project_path = Path(path).expanduser().resolve()
        if not project_path.exists():
            return self.fail(error=f"Directory not found: {project_path}")

        files = _get_recent_files(project_path, n=n, max_depth=max_depth)
        return self.ok(
            message=f"Found {len(files)} recent files in {project_path.name}",
            output={"files": files, "path": str(project_path)},
        )


# ─────────────────────────────────────────────────────────────
# list_projects
# ─────────────────────────────────────────────────────────────

class ListProjects(AuraTool):
    """
    List all detectable projects in the projects root directory.
    Used on startup and for "what projects do I have?" queries.
    """

    name = "list_projects"
    description = (
        "List all projects found in ~/Documents/ (or a specified root). "
        "Returns each project's name, type, and last modified time. "
        "Use this when the user asks what projects are available."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "search_root": {
                "type": "string",
                "description": "Root directory to search. Defaults to ~/Documents/",
            },
        },
        "required": [],
    }
    estimated_duration_ms = 800
    is_reversible = True
    category = "filesystem"

    def execute(self, search_root: str = None) -> ToolResult:
        root = Path(search_root).expanduser() if search_root else PROJECTS_ROOT
        if not root.exists():
            return self.fail(error=f"Search root not found: {root}")

        projects = []
        try:
            for entry in sorted(root.iterdir()):
                if not entry.is_dir():
                    continue
                if entry.name.startswith(".") or entry.name in IGNORE_DIRS:
                    continue
                types = _detect_project_type(entry)
                try:
                    mtime = max(
                        (f.stat().st_mtime for f in _walk_limited(entry, max_depth=1)),
                        default=entry.stat().st_mtime,
                    )
                except (OSError, ValueError):
                    mtime = 0

                projects.append({
                    "name":  entry.name,
                    "path":  str(entry),
                    "types": types,
                    "mtime": mtime,
                })
        except PermissionError as e:
            return self.fail(error=f"Permission denied reading {root}: {e}")

        projects.sort(key=lambda p: p["mtime"], reverse=True)
        for p in projects:
            del p["mtime"]

        return self.ok(
            message=f"Found {len(projects)} projects in {root}",
            output={"projects": projects, "root": str(root)},
        )


# ─────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────

FILESYSTEM_TOOLS: list[AuraTool] = [
    DetectProject(),
    ListRecentFiles(),
    ListProjects(),
]

FILESYSTEM_TOOLS_BY_NAME: dict[str, AuraTool] = {t.name: t for t in FILESYSTEM_TOOLS}