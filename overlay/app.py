"""
AuraOS · Overlay
================
A minimal floating TUI that appears on hotkey press.
Takes user input, streams agent output, then closes.

Uses Textual for the UI — looks clean, supports
streaming text out of the box.
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from textual.app import App, ComposeResult
from textual.widgets import Input, RichLog, Label
from textual.containers import Vertical
from textual import work

from core.agent import Agent


BANNER = "⚡ AuraOS  ·  Cmd+Enter to run  ·  Esc to close"


class AuraOverlay(App):
    """Floating AuraOS input/output overlay."""

    CSS = """
    Screen {
        background: $surface;
        align: center middle;
    }

    #container {
        width: 80;
        height: 30;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }

    #banner {
        color: $text-muted;
        text-align: center;
        margin-bottom: 1;
    }

    #input {
        margin-bottom: 1;
        border: solid $primary;
    }

    #output {
        height: 1fr;
        border: solid $surface-darken-1;
        background: $surface-darken-1;
        padding: 0 1;
    }
    """

    BINDINGS = [
        ("escape",    "quit",  "Close"),
        ("ctrl+c",    "quit",  "Close"),
    ]

    def compose(self) -> ComposeResult:
        with Vertical(id="container"):
            yield Label(BANNER, id="banner")
            yield Input(placeholder="What do you want to do?", id="input")
            yield RichLog(id="output", wrap=True, highlight=True, markup=True)

    def on_mount(self):
        self.query_one("#input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted):
        user_input = event.value.strip()
        if not user_input:
            return
        output = self.query_one("#output", RichLog)
        output.clear()
        inp = self.query_one("#input", Input)
        inp.disabled = True
        self.run_agent(user_input)

    @work(thread=True)
    def run_agent(self, user_input: str):
        output = self.query_one("#output", RichLog)
        agent = Agent()
        try:
            for token in agent.run(user_input):
                # Schedule UI update on the main thread
                self.call_from_thread(output.write, token.rstrip("\n"))
        except Exception as e:
            self.call_from_thread(output.write, f"[red]Error: {e}[/red]")
        finally:
            agent.close()
            inp = self.query_one("#input", Input)
            self.call_from_thread(setattr, inp, "disabled", False)
            self.call_from_thread(inp.focus)


if __name__ == "__main__":
    app = AuraOverlay()
    app.run()