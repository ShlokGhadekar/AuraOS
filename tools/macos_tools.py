"""
AuraOS · macOS Tools
====================
Tools that control macOS — launching apps, opening files,
managing VS Code workspaces.

All tools use the macOS `open` command or `osascript` under the hood.
No Accessibility API required for these — they work with standard
macOS permissions.

Project root default: ~/Documents/
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from tools.base import AuraTool, ToolResult


# ─────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────

def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str, str]:
    """Run a subprocess. Returns (returncode, stdout, stderr)."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout.strip(), result.stderr.strip()
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except FileNotFoundError as e:
        return -1, "", str(e)


def _osascript(script: str) -> tuple[int, str, str]:
    """Run an AppleScript snippet."""
    return _run(["osascript", "-e", script])


def _expand(path: str) -> Path:
    return Path(path).expanduser().resolve()


# ─────────────────────────────────────────────────────────────
# open_app
# ─────────────────────────────────────────────────────────────

class OpenApp(AuraTool):
    """
    Launch a macOS application by name.

    Uses `open -a` which searches /Applications and ~/Applications.
    Safe to call on an already-open app — macOS just brings it to front.
    """

    name = "open_app"
    description = (
        "Launch or focus a macOS application by name. "
        "Use this to open apps like 'Visual Studio Code', 'Terminal', "
        "'Safari', 'Notion', 'Spotify', etc. "
        "If the app is already open, it will be brought to the foreground."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "app_name": {
                "type": "string",
                "description": "The application name as it appears in /Applications, e.g. 'Visual Studio Code'",
            }
        },
        "required": ["app_name"],
    }
    estimated_duration_ms = 1500
    is_reversible = False
    category = "macos"

    # Common name aliases — user might say "vscode", we launch the right thing
    ALIASES: dict[str, str] = {
        "vscode":       "Visual Studio Code",
        "vs code":      "Visual Studio Code",
        "code":         "Visual Studio Code",
        "terminal":     "Terminal",
        "iterm":        "iTerm",
        "iterm2":       "iTerm",
        "chrome":       "Google Chrome",
        "firefox":      "Firefox",
        "safari":       "Safari",
        "notion":       "Notion",
        "slack":        "Slack",
        "discord":      "Discord",
        "spotify":      "Spotify",
        "finder":       "Finder",
        "notes":        "Notes",
        "calendar":     "Calendar",
        "mail":         "Mail",
        "zoom":         "zoom.us",
    }

    def execute(self, app_name: str) -> ToolResult:
        resolved = self.ALIASES.get(app_name.lower(), app_name)
        code, _, err = _run(["open", "-a", resolved])
        if code == 0:
            return self.ok(
                message=f"Opened {resolved}",
                output={"app": resolved},
            )
        return self.fail(
            error=f"Could not open '{resolved}': {err}. "
                  f"Is it installed in /Applications?"
        )


# ─────────────────────────────────────────────────────────────
# open_file
# ─────────────────────────────────────────────────────────────

class OpenFile(AuraTool):
    """
    Open a file with its default application, or a specified one.
    """

    name = "open_file"
    description = (
        "Open a file on disk. Uses the system default app unless `app_name` is specified. "
        "Use this to open PDFs, images, documents, notebooks, etc. "
        "For code files, prefer open_vscode_workspace."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Absolute or ~ path to the file, e.g. '~/Documents/notes.md'",
            },
            "app_name": {
                "type": "string",
                "description": "Optional: application to open with, e.g. 'Visual Studio Code'",
            },
        },
        "required": ["path"],
    }
    estimated_duration_ms = 800
    is_reversible = False
    category = "macos"

    def execute(self, path: str, app_name: str = None) -> ToolResult:
        resolved = _expand(path)
        if not resolved.exists():
            return self.fail(error=f"File not found: {resolved}")

        cmd = ["open"]
        if app_name:
            cmd += ["-a", app_name]
        cmd.append(str(resolved))

        code, _, err = _run(cmd)
        if code == 0:
            return self.ok(
                message=f"Opened {resolved.name}" + (f" in {app_name}" if app_name else ""),
                output={"path": str(resolved), "app": app_name},
            )
        return self.fail(error=f"Failed to open {resolved}: {err}")


# ─────────────────────────────────────────────────────────────
# open_vscode_workspace
# ─────────────────────────────────────────────────────────────

class OpenVSCodeWorkspace(AuraTool):
    """
    Open a project directory in VS Code.

    Uses the `code` CLI. If the `code` command isn't in PATH,
    falls back to `open -a 'Visual Studio Code' <path>`.

    Optionally opens specific files in the editor after launch.
    """

    name = "open_vscode_workspace"
    description = (
        "Open a project folder in Visual Studio Code. "
        "Use this whenever resuming work on a coding project. "
        "Optionally specify files to open immediately in the editor."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "path": {
                "type": "string",
                "description": "Path to the project directory, e.g. '~/Documents/fake-news-detection'",
            },
            "files": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Optional list of file paths (relative to project) to open in the editor",
            },
            "new_window": {
                "type": "boolean",
                "description": "Open in a new VS Code window. Default: true",
            },
        },
        "required": ["path"],
    }
    estimated_duration_ms = 2000
    is_reversible = False
    category = "macos"

    def execute(
        self,
        path: str,
        files: list[str] = None,
        new_window: bool = True,
    ) -> ToolResult:
        project_path = _expand(path)
        if not project_path.exists():
            return self.fail(error=f"Directory not found: {project_path}")
        if not project_path.is_dir():
            return self.fail(error=f"Path is not a directory: {project_path}")

        # Try `code` CLI first
        if self._has_code_cli():
            return self._open_with_cli(project_path, files or [], new_window)
        else:
            return self._open_with_open_command(project_path)

    def _has_code_cli(self) -> bool:
        code, _, _ = _run(["which", "code"])
        return code == 0

    def _open_with_cli(
        self,
        project_path: Path,
        files: list[str],
        new_window: bool,
    ) -> ToolResult:
        cmd = ["code"]
        if new_window:
            cmd.append("--new-window")
        cmd.append(str(project_path))

        for f in files:
            file_path = project_path / f
            if file_path.exists():
                cmd.append(str(file_path))

        code, _, err = _run(cmd, timeout=15)
        if code == 0:
            opened_files = [f for f in files if (project_path / f).exists()]
            return self.ok(
                message=f"Opened {project_path.name} in VS Code"
                        + (f" with {len(opened_files)} file(s)" if opened_files else ""),
                output={
                    "project_path": str(project_path),
                    "files_opened": opened_files,
                    "new_window": new_window,
                },
            )
        return self.fail(error=f"VS Code CLI error: {err}")

    def _open_with_open_command(self, project_path: Path) -> ToolResult:
        """Fallback if `code` CLI not in PATH."""
        code, _, err = _run(["open", "-a", "Visual Studio Code", str(project_path)])
        if code == 0:
            return self.ok(
                message=f"Opened {project_path.name} in VS Code (via open command)",
                output={"project_path": str(project_path)},
                metadata={"cli_available": False},
            )
        return self.fail(
            error=f"Could not open VS Code. "
                  f"Install the 'code' CLI: VS Code → Command Palette → "
                  f"'Shell Command: Install code command in PATH'. Error: {err}"
        )


# ─────────────────────────────────────────────────────────────
# send_notification
# ─────────────────────────────────────────────────────────────

class SendNotification(AuraTool):
    """
    Send a macOS system notification.
    Used by the agent to signal completion of multi-step tasks.
    """

    name = "send_notification"
    description = (
        "Send a macOS notification to the user. "
        "Use this to signal that a long-running task has completed, "
        "or to surface important information."
    )
    parameters_schema = {
        "type": "object",
        "properties": {
            "title": {
                "type": "string",
                "description": "Notification title",
            },
            "message": {
                "type": "string",
                "description": "Notification body text",
            },
            "subtitle": {
                "type": "string",
                "description": "Optional subtitle",
            },
        },
        "required": ["title", "message"],
    }
    estimated_duration_ms = 200
    is_reversible = False
    category = "macos"

    def execute(self, title: str, message: str, subtitle: str = "") -> ToolResult:
        subtitle_part = f'subtitle "{subtitle}"' if subtitle else ""
        script = (
            f'display notification "{message}" '
            f'with title "{title}" '
            f'{subtitle_part}'
        ).strip()

        code, _, err = _osascript(script)
        if code == 0:
            return self.ok(
                message=f"Notification sent: {title}",
                output={"title": title, "message": message},
            )
        return self.fail(error=f"Notification failed: {err}")


# ─────────────────────────────────────────────────────────────
# Registry — all macOS tools in one place
# ─────────────────────────────────────────────────────────────

MACOS_TOOLS: list[AuraTool] = [
    OpenApp(),
    OpenFile(),
    OpenVSCodeWorkspace(),
    SendNotification(),
]

MACOS_TOOLS_BY_NAME: dict[str, AuraTool] = {t.name: t for t in MACOS_TOOLS}

class QuitApps(AuraTool):
    name = "quit_apps"
    description = "Quit one or more macOS applications by name."
    parameters_schema = {
        "type": "object",
        "properties": {
            "apps": {
                "type": "array",
                "items": {"type": "string"},
                "description": "List of app names to quit",
            }
        },
        "required": ["apps"],
    }
    is_reversible = False
    category = "macos"

    def execute(self, apps: list[str]) -> ToolResult:
        quit_results = []
        for app in apps:
            script = f'tell application "{app}" to quit'
            code, _, err = _osascript(script)
            quit_results.append({"app": app, "success": code == 0})
        succeeded = [r["app"] for r in quit_results if r["success"]]
        return self.ok(
            message=f"Quit {len(succeeded)} apps: {', '.join(succeeded)}",
            output={"results": quit_results},
        )


class SetDoNotDisturb(AuraTool):
    name = "set_do_not_disturb"
    description = "Enable or disable macOS Do Not Disturb / Focus mode."
    parameters_schema = {
        "type": "object",
        "properties": {
            "enabled": {
                "type": "boolean",
                "description": "True to enable DND, False to disable",
            }
        },
        "required": ["enabled"],
    }
    is_reversible = True
    category = "macos"

    def execute(self, enabled: bool) -> ToolResult:
        # macOS Sonoma/Sequoia: toggle Focus via shortcuts
        action = "on" if enabled else "off"
        # Use osascript to toggle via System Events
        script = f"""
        tell application "System Events"
            tell process "Control Center"
                -- Focus mode toggle via menu bar
            end tell
        end tell
        """
        # Fallback: use shortcuts app if available
        code, _, err = _run([
            "shortcuts", "run",
            "Enable Do Not Disturb" if enabled else "Disable Do Not Disturb"
        ])
        if code == 0:
            return self.ok(message=f"Do Not Disturb {'enabled' if enabled else 'disabled'}")
        # Non-fatal — DND is nice to have
        return self.ok(
            message=f"DND toggle attempted (manual toggle may be needed)",
            metadata={"manual_required": True},
        )
    
MACOS_TOOLS: list[AuraTool] = [
OpenApp(),
OpenFile(),
OpenVSCodeWorkspace(),
SendNotification(),
QuitApps(),
SetDoNotDisturb(),
]

MACOS_TOOLS_BY_NAME: dict[str, AuraTool] = {t.name: t for t in MACOS_TOOLS}