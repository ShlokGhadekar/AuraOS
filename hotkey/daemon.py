"""
AuraOS · Hotkey Daemon
======================
Uses pynput's built-in HotKey helper instead of manual
key set tracking — much more reliable on macOS.

Hotkey: Cmd+Shift+Space
"""
import subprocess
import sys
import time
from pathlib import Path
from pynput import keyboard

PROJECT_ROOT = Path(__file__).parent.parent
OVERLAY_SCRIPT = PROJECT_ROOT / "overlay" / "app.py"
PYTHON = sys.executable

overlay_process = None


def launch_overlay():
    global overlay_process
    if overlay_process and overlay_process.poll() is None:
        return
    print("Launching overlay...")
    overlay_process = subprocess.Popen(
        [PYTHON, str(OVERLAY_SCRIPT)],
        cwd=str(PROJECT_ROOT),
    )


def main():
    print("AuraOS daemon running. Press Cmd+Shift+Space to activate.")
    print("Press Ctrl+C to stop.")

    with keyboard.GlobalHotKeys({
        "<cmd>+<shift>+<space>": launch_overlay,
    }) as h:
        h.join()


if __name__ == "__main__":
    main()