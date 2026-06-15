"""
AuraOS · Memory Tests
=====================
Tests for all three memory tiers.
All tests use in-memory backends — no files written to disk.

Run with:  pytest tests/test_memory.py -v
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from memory.episodic import EpisodicMemory
from memory.working import WorkingMemory
from memory.semantic import SemanticMemory


# ─────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────

@pytest.fixture
def mem():
    """Fresh in-memory episodic store per test."""
    m = EpisodicMemory(db_path=":memory:")
    yield m
    m.close()

@pytest.fixture
def sem():
    """Fresh in-memory semantic store per test."""
    return SemanticMemory(path=":memory:")

@pytest.fixture
def wm():
    """Fresh working memory per test."""
    return WorkingMemory()

@pytest.fixture
def project(mem):
    """A pre-seeded project."""
    return mem.upsert_project(
        id="fake-news-detection",
        name="Fake News Detection",
        path="~/projects/fake-news-detection",
        description="ML project for classifying misinformation using NLP",
        github_repo="user/fake-news-detection",
        tags=["ml", "nlp", "python"],
    )


# ─────────────────────────────────────────────────────────────
# Tier 2 · Episodic memory
# ─────────────────────────────────────────────────────────────

class TestProjects:
    def test_upsert_and_retrieve(self, mem):
        p = mem.upsert_project(
            id="auraos",
            name="AuraOS",
            path="~/projects/auraos",
            tags=["ai", "python"],
        )
        assert p.id == "auraos"
        assert p.name == "AuraOS"
        assert "ai" in p.tags

    def test_upsert_is_idempotent(self, mem):
        mem.upsert_project(id="p1", name="Project One", path="/p1")
        mem.upsert_project(id="p1", name="Project One Updated", path="/p1")
        p = mem.get_project("p1")
        assert p.name == "Project One Updated"

    def test_list_projects(self, mem, project):
        mem.upsert_project(id="p2", name="Project Two", path="/p2")
        projects = mem.list_projects()
        assert len(projects) == 2

    def test_get_nonexistent(self, mem):
        assert mem.get_project("does-not-exist") is None

    def test_touch_updates_last_accessed(self, mem, project):
        assert project.last_accessed is None
        mem.touch_project(project.id)
        updated = mem.get_project(project.id)
        assert updated.last_accessed is not None


class TestSessions:
    def test_start_and_end_session(self, mem, project):
        s = mem.start_session(
            raw_input="continue my fake news project",
            project_id=project.id,
            intent="continue_project",
        )
        assert s.status == "running"
        assert s.ended_at is None
        assert s.duration_ms is None

        ended = mem.end_session(s.id, status="completed")
        assert ended.status == "completed"
        assert ended.ended_at is not None
        assert ended.duration_ms >= 0

    def test_session_fail(self, mem):
        s = mem.start_session(raw_input="open vscode")
        ended = mem.end_session(s.id, status="failed", error="VS Code not found")
        assert ended.status == "failed"
        assert "VS Code" in ended.error

    def test_update_plan(self, mem):
        s = mem.start_session(raw_input="continue project")
        plan = [
            {"step": 1, "tool": "load_context", "status": "pending"},
            {"step": 2, "tool": "open_vscode",  "status": "pending"},
        ]
        mem.update_session_plan(s.id, plan)
        updated = mem.get_session(s.id)
        assert len(updated.plan) == 2
        assert updated.plan[0]["tool"] == "load_context"

    def test_get_recent_sessions(self, mem, project):
        for i in range(5):
            s = mem.start_session(f"session {i}", project_id=project.id)
            mem.end_session(s.id)

        recent = mem.get_recent_sessions(project.id, limit=3)
        assert len(recent) == 3

    def test_end_nonexistent_session_raises(self, mem):
        with pytest.raises(ValueError):
            mem.end_session("00000000-0000-0000-0000-000000000000")


class TestContextSnapshots:
    def test_save_and_retrieve_snapshot(self, mem, project):
        snap = mem.save_snapshot(
            project_id=project.id,
            current_goal="Improve F1 score",
            last_action="Implemented TF-IDF baseline",
            next_step="Try BERT embeddings",
            open_questions=["Use sentence-transformers or fine-tuned BERT?"],
            relevant_files=["model/baseline.py", "notebooks/eda.ipynb"],
            blockers=[],
            summary="Working on fake news classifier. Baseline done, BERT next.",
        )
        assert snap.is_current is True
        assert snap.current_goal == "Improve F1 score"
        assert len(snap.open_questions) == 1

        retrieved = mem.get_current_snapshot(project.id)
        assert retrieved.id == snap.id

    def test_only_one_current_snapshot(self, mem, project):
        mem.save_snapshot(project_id=project.id, current_goal="Goal 1")
        mem.save_snapshot(project_id=project.id, current_goal="Goal 2")
        mem.save_snapshot(project_id=project.id, current_goal="Goal 3")

        current = mem.get_current_snapshot(project.id)
        assert current.current_goal == "Goal 3"

        history = mem.get_snapshot_history(project.id)
        # All 3 exist, only 1 is current
        assert len(history) == 3
        current_count = sum(1 for s in history if s.is_current)
        assert current_count == 1

    def test_no_snapshot_returns_none(self, mem, project):
        assert mem.get_current_snapshot(project.id) is None

    def test_json_fields_roundtrip(self, mem, project):
        files = ["a.py", "b.py", "c/d.py"]
        questions = ["Question one?", "Question two?"]
        snap = mem.save_snapshot(
            project_id=project.id,
            relevant_files=files,
            open_questions=questions,
        )
        assert snap.relevant_files == files
        assert snap.open_questions == questions


class TestToolCalls:
    def test_log_and_complete(self, mem, project):
        s = mem.start_session("open vscode", project.id)
        call = mem.log_tool_call(
            session_id=s.id,
            tool_name="open_vscode_workspace",
            parameters={"path": "~/projects/fake-news"},
        )
        assert call.status == "pending"
        assert call.parameters["path"] == "~/projects/fake-news"

        mem.complete_tool_call(
            call.id,
            status="success",
            result='{"opened": true}',
            duration_ms=340,
        )
        updated = mem.get_tool_call(call.id)
        assert updated.status == "success"
        assert updated.duration_ms == 340

    def test_get_session_tool_calls(self, mem, project):
        s = mem.start_session("dsa session", project.id)
        for tool in ["load_context", "open_leetcode", "open_vscode"]:
            call = mem.log_tool_call(s.id, tool)
            mem.complete_tool_call(call.id, status="success")

        calls = mem.get_session_tool_calls(s.id)
        assert len(calls) == 3
        assert calls[0].tool_name == "load_context"


class TestGoals:
    def test_add_and_retrieve_goal(self, mem, project):
        g = mem.add_goal(
            title="Achieve 90% F1 on validation set",
            project_id=project.id,
            priority=1,
            due_date="2025-07-01",
        )
        assert g.title == "Achieve 90% F1 on validation set"
        assert g.priority == 1

    def test_list_active_goals(self, mem, project):
        mem.add_goal("Goal A", project_id=project.id)
        mem.add_goal("Goal B", project_id=project.id)
        g = mem.add_goal("Goal C", project_id=project.id)
        mem.complete_goal(g.id)

        active = mem.list_goals(project.id)
        assert len(active) == 2

    def test_global_goals(self, mem):
        mem.add_goal("Read 2 papers per week")  # no project_id
        goals = mem.list_goals()
        assert len(goals) == 1
        assert goals[0].project_id is None


class TestProjectContext:
    def test_get_full_context(self, mem, project):
        s = mem.start_session("continue fake news", project.id)
        mem.end_session(s.id)
        mem.save_snapshot(
            project_id=project.id,
            current_goal="Improve F1",
            next_step="Try BERT",
        )
        mem.add_goal("Hit 90% accuracy", project_id=project.id)

        ctx = mem.get_project_context(project.id)
        assert ctx["project"]["id"] == project.id
        assert ctx["snapshot"]["current_goal"] == "Improve F1"
        assert len(ctx["recent_sessions"]) == 1
        assert len(ctx["active_goals"]) == 1


# ─────────────────────────────────────────────────────────────
# Tier 1 · Working memory
# ─────────────────────────────────────────────────────────────

class TestWorkingMemory:
    def test_initial_state(self, wm):
        assert wm.active_project_id is None
        assert wm.conversation == []
        assert wm.tool_results == {}
        assert wm.plan == []

    def test_conversation_buffer(self, wm):
        wm.push_message("user", "continue my project")
        wm.push_message("assistant", "Loading context...")
        assert len(wm.conversation) == 2
        assert wm.conversation[0]["role"] == "user"

    def test_tool_results(self, wm):
        wm.record_tool_result("open_vscode", {"status": "ok"})
        assert wm.get_tool_result("open_vscode") == {"status": "ok"}
        # Should also append to conversation
        assert any("open_vscode" in m["content"] for m in wm.conversation)

    def test_plan_management(self, wm):
        plan = [
            {"step": 1, "tool": "load_context",  "status": "pending"},
            {"step": 2, "tool": "open_vscode",   "status": "pending"},
            {"step": 3, "tool": "open_terminal", "status": "pending"},
        ]
        wm.set_plan(plan)
        assert len(wm.get_pending_steps()) == 3

        wm.mark_step_done(0, result="context loaded")
        assert len(wm.get_pending_steps()) == 2
        assert wm.plan[0]["status"] == "done"

        wm.mark_step_failed(1, error="VS Code not found")
        assert wm.plan[1]["status"] == "failed"

    def test_scratchpad(self, wm):
        wm.note("detected_project", "fake-news-detection")
        assert wm.recall("detected_project") == "fake-news-detection"
        assert wm.recall("missing_key", default=42) == 42

    def test_to_snapshot_dict(self, wm):
        wm.set_project("fake-news-detection")
        wm.raw_input = "continue my project"
        wm.record_tool_result("open_vscode", {"ok": True})
        d = wm.to_snapshot_dict()
        assert d["project_id"] == "fake-news-detection"
        assert "open_vscode" in d["completed_tools"]

    def test_summary_stats(self, wm):
        wm.set_plan([{"tool": "x", "status": "done"}, {"tool": "y", "status": "pending"}])
        wm.push_message("user", "hello")
        stats = wm.summary_stats()
        assert stats["plan_steps"] == 2
        assert stats["steps_done"] == 1
        assert stats["messages"] == 1


# ─────────────────────────────────────────────────────────────
# Tier 3 · Semantic memory
# ─────────────────────────────────────────────────────────────

class TestSemanticMemory:
    def test_upsert_and_search_project(self, sem):
        sem.upsert_project(
            "fake-news-detection",
            "Fake News Detection: ML project for classifying misinformation "
            "using NLP, BERT, and Python. scikit-learn, transformers.",
            metadata={"path": "~/projects/fake-news"},
        )
        results = sem.search_projects("machine learning fake news NLP")
        assert len(results) >= 1
        assert results[0]["id"] == "fake-news-detection"

    def test_fuzzy_project_match(self, sem):
        sem.upsert_project(
            "fake-news-detection",
            "Fake News Detection: ML classifier for misinformation. Python, BERT.",
            metadata={"path": "~/projects/fake-news"},
        )
        sem.upsert_project(
            "auraos",
            "AuraOS: AI-powered personal computing environment. Python, FastAPI, MCP.",
            metadata={"path": "~/projects/auraos"},
        )

        result = sem.identify_project("that NLP misinformation classifier")
        assert result == "fake-news-detection"

        result2 = sem.identify_project("my AI operating system project")
        assert result2 == "auraos"

    def test_empty_store_returns_empty(self, sem):
        results = sem.search_projects("anything")
        assert results == []

    def test_identify_project_empty(self, sem):
        assert sem.identify_project("some project") is None

    def test_upsert_is_idempotent(self, sem):
        for _ in range(3):
            sem.upsert_project("p1", "Project One description")
        assert sem.stats()["projects"] == 1

    def test_snapshot_search(self, sem):
        sem.upsert_snapshot(
            "snap-001",
            "fake-news-detection 2025-06-14: Working on BERT embeddings. "
            "Tokenizer memory issue is a blocker.",
            metadata={"project_id": "fake-news-detection"},
        )
        results = sem.search_snapshots("BERT tokenizer problem")
        assert len(results) >= 1
        assert "BERT" in results[0]["document"]

    def test_snapshot_filter_by_project(self, sem):
        sem.upsert_snapshot("s1", "fake-news session: BERT work",
                            metadata={"project_id": "fake-news-detection"})
        sem.upsert_snapshot("s2", "auraos session: memory system",
                            metadata={"project_id": "auraos"})

        results = sem.search_snapshots("work done", project_id="auraos")
        assert all(r["metadata"]["project_id"] == "auraos" for r in results)

    def test_stats(self, sem):
        sem.upsert_project("p1", "project one")
        sem.upsert_snapshot("s1", "snapshot one", metadata={"project_id": "p1"})
        stats = sem.stats()
        assert stats["projects"] == 1
        assert stats["snapshots"] == 1
        assert stats["sessions"] == 0