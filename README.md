# AuraOS

> An AI-powered command layer for macOS — a personal agent with persistent memory, planning, and real computer control, built on MCP (Model Context Protocol).

AuraOS sits between you and your Mac. Press a hotkey, type what you want in plain English, and it plans a sequence of real actions — recalling full context from your last work session, checking your calendar and GitHub issues, creating new repos, automating focus routines, controlling a real browser — and executes them with a streaming, transparent UI that shows its plan before it runs.

It is not a chatbot wrapper. It's an agent with persistent cross-session memory, a modular multi-server tool architecture, and genuine write access to real systems: filesystem, git, GitHub, macOS Calendar, and a browser.

---

## What it actually does

"continue my fake news project"

→ recalls last session's goal, blockers, and next step from memory

→ pulls open GitHub issues and recent commits for the repo

→ opens the right folder in VS Code with the right files
"what should I work on today?"

→ reads today's calendar via a native Swift/EventKit bridge

→ reads active goals from memory

→ synthesizes a prioritized plan — not just a list of events
"create a new project called task-tracker"

→ creates the GitHub repo

→ scaffolds starter files (README, .gitignore, entry point)

→ pushes the initial commit

→ registers it in AuraOS's memory

→ opens it in VS Code

"open an issue on auraos about the SQLite bug"

→ resolves the project's repo from memory

→ drafts and files the issue — behind an explicit confirmation gate
"start dsa session"

→ opens LeetCode in a controlled browser, VS Code, notes, and a timer

in a single command
"search leetcode for dynamic programming patterns"

→ drives a real, visible browser via Playwright — not a hidden headless call

---

## Architecture

AuraOS is built as a set of independent MCP servers behind a planning agent, not a monolith.
<img width="1536" height="1024" alt="d7a7fc46692a8cd95d4a4ad6cc7ebc874a071e2e39767281f9d0fb715b9d2aea" src="https://github.com/user-attachments/assets/359d18b0-a362-4cf3-aea9-410733fbceff" />

**Memory is three-tiered, deliberately:**
- **Working memory** — in-process state for the current session only
- **Episodic memory** (SQLite) — session history, structured context snapshots (goal, last action, next step, blockers, open questions), goals
- **Semantic memory** (ChromaDB) — local vector search, so "that NLP thing" correctly resolves to the right registered project without exact name matching

**Single-writer SQLite discipline.** Originally, every MCP server opened its own SQLite connection. Under concurrent writes (multiple workflow steps logging tool calls in quick succession) this caused intermittent `database is locked` failures — a real distributed-systems problem, not a typo. The fix: every write now routes through one dedicated memory server over HTTP; every other process only reads. Lock errors disappeared permanently once writes were serialized through a single owner, rather than papered over with retries.

**Workflows are data, not code.** DSA study sessions, deep work mode, end-of-day wrap-up, and project kickoff are YAML-defined step sequences with variable substitution between steps (e.g. a created GitHub repo's clone URL automatically flows into the next step that pushes to it). Adding a new automated routine requires no changes to the agent core.

**Native macOS integration where the standard tooling fails.** `icalBuddy`, the common Python-side calendar tool, has no reliable permission flow on modern macOS. AuraOS ships a small compiled Swift/EventKit CLI bridge instead — the same API Apple's own Calendar app uses — for both reading and creating events.

**Real browser control, not `open` shelling out.** Browser tasks run through a persistent Playwright-controlled Chromium instance, lazily started and bound correctly to its own async event loop, supporting navigation, search, form-filling, and page-text extraction — not just launching a default-browser tab.

---

## Stack

- **Agent reasoning:** Groq (Llama 3.x) — intent classification, planning, session summarization
- **Tool protocol:** MCP (Model Context Protocol) — six independent FastAPI servers
- **Memory:** SQLite (episodic, single-writer) + ChromaDB (semantic, local embeddings)
- **Calendar:** native Swift/EventKit CLI bridge (read + write)
- **Browser:** Playwright (Chromium)
- **UI:** Electron floating overlay, global-hotkey triggered, live-streaming agent output
- **Backend:** Python, FastAPI, asyncio

---

## Design decisions worth knowing about

- **MCP servers as separate processes**, not one backend — fault isolation (a GitHub outage doesn't affect calendar access), and each domain is independently testable and replaceable.
- **Plan-then-execute, not a blind ReAct loop.** Every multi-step task shows its plan before running. Write operations — git commits, GitHub issues/PRs, repo creation — sit behind an explicit confirmation gate.
- **Local-first.** No telemetry, no cloud sync of personal data. Memory lives on-disk in SQLite and ChromaDB. The only network calls are to the LLM provider and the services you explicitly use (GitHub, Calendar).
- **Streaming over blocking.** Tool calls stream progress as they happen — you see "Opening VS Code..." within milliseconds, not after a silent multi-second plan-then-execute block.

---

## Setup

```bash
git clone https://github.com/ShlokGhadekar/AuraOS.git
cd AuraOS

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium

cd electron-overlay
npm install
cd ..
```

Add your keys to `.env`:
GROQ_API_KEY=...
GITHUB_TOKEN=...

Compile the calendar bridge once:
```bash
swiftc scripts/calendar_bridge.swift -o scripts/calendar_bridge
```
The first run will prompt for Calendar access in System Settings → Privacy & Security.

Configure your projects in `config/projects.yaml`, then:
```bash
bash scripts/start.sh        # starts all 6 MCP servers + core API + hotkey daemon
cd electron-overlay && npm start
```

Press **Cmd+Shift+Space** anywhere on macOS to invoke AuraOS.

---

## Status

Actively developed.

**Working:** project context restoration with cross-session memory, daily planning synthesis, calendar read/write, GitHub read/write (issues, PRs, repo creation), git automation, YAML-defined workflow automation (DSA sessions, deep work, end-of-day, project kickoff), real browser control (navigate, search, fill forms, read pages).

**Next:** screen-aware control (vision-based UI interaction for apps with no API surface).

---

## License

MIT
