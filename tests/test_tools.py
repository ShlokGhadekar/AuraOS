"""
Run with: .venv/bin/pytest tests/test_tools.py -v
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from tools.base import AuraTool, ToolResult
from tools.macos_tools import OpenApp, OpenFile, OpenVSCodeWorkspace, SendNotification, MACOS_TOOLS_BY_NAME
from tools.filesystem_tools import DetectProject, ListRecentFiles, ListProjects, FILESYSTEM_TOOLS_BY_NAME
import tempfile, os

# ── base class ───────────────────────────────────────────────

class DummyTool(AuraTool):
    name = "dummy"
    description = "A test tool"
    parameters_schema = {"type": "object", "properties": {}, "required": []}
    def execute(self, **kwargs) -> ToolResult:
        return self.ok("it worked", output={"x": 1})

def test_tool_result_ok():
    t = DummyTool()
    r = t.execute()
    assert r.success is True
    assert r.tool_name == "dummy"
    assert r.output == {"x": 1}

def test_tool_result_fail():
    t = DummyTool()
    r = t.fail("something broke")
    assert r.success is False
    assert "something broke" in r.error

def test_timed_execute():
    t = DummyTool()
    r = t.timed_execute()
    assert r.success is True
    assert r.duration_ms >= 0

def test_to_llm_spec():
    t = DummyTool()
    spec = t.to_llm_spec()
    assert spec["name"] == "dummy"
    assert "description" in spec
    assert "input_schema" in spec

def test_registry_contains_all_tools():
    assert "open_app" in MACOS_TOOLS_BY_NAME
    assert "open_file" in MACOS_TOOLS_BY_NAME
    assert "open_vscode_workspace" in MACOS_TOOLS_BY_NAME
    assert "send_notification" in MACOS_TOOLS_BY_NAME
    assert "detect_project" in FILESYSTEM_TOOLS_BY_NAME
    assert "list_recent_files" in FILESYSTEM_TOOLS_BY_NAME
    assert "list_projects" in FILESYSTEM_TOOLS_BY_NAME

# ── open_app ─────────────────────────────────────────────────

def test_open_app_bad_name():
    t = OpenApp()
    r = t.execute(app_name="ThisAppDoesNotExist12345")
    assert r.success is False

def test_open_app_alias_resolution():
    # Aliases resolve correctly — we're just checking the mapping,
    # not actually launching anything
    assert OpenApp.ALIASES["vscode"] == "Visual Studio Code"
    assert OpenApp.ALIASES["chrome"] == "Google Chrome"

# ── open_file ────────────────────────────────────────────────

def test_open_file_missing():
    t = OpenFile()
    r = t.execute(path="/tmp/this_file_does_not_exist_auraos.txt")
    assert r.success is False
    assert "not found" in r.error.lower()

def test_open_file_exists(tmp_path):
    f = tmp_path / "test.txt"
    f.write_text("hello")
    t = OpenFile()
    # We call but don't assert success=True since CI has no display
    r = t.execute(path=str(f))
    # At minimum it should not crash and should find the file
    assert "not found" not in r.error.lower()

# ── open_vscode_workspace ────────────────────────────────────

def test_open_vscode_missing_dir():
    t = OpenVSCodeWorkspace()
    r = t.execute(path="/tmp/this_dir_does_not_exist_auraos_xyz")
    assert r.success is False
    assert "not found" in r.error.lower()

def test_open_vscode_file_not_dir(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("hello")
    t = OpenVSCodeWorkspace()
    r = t.execute(path=str(f))
    assert r.success is False
    assert "not a directory" in r.error.lower()

# ── detect_project ───────────────────────────────────────────

def test_detect_project_not_found():
    t = DetectProject()
    r = t.execute(name_or_path="project_that_definitely_does_not_exist_xyz")
    assert r.success is False

def test_detect_project_by_path(tmp_path):
    # Create a fake Python project
    (tmp_path / "requirements.txt").write_text("fastapi\n")
    (tmp_path / "main.py").write_text("print('hello')")
    (tmp_path / "README.md").write_text("# My Project")

    t = DetectProject()
    r = t.execute(name_or_path=str(tmp_path))
    assert r.success is True
    assert "python" in r.output["project_types"]
    assert r.output["name"] == tmp_path.name

def test_detect_project_fuzzy_match(tmp_path):
    # Create project dir with dashes
    proj = tmp_path / "fake-news-detection"
    proj.mkdir()
    (proj / "README.md").write_text("# Fake News")

    t = DetectProject()
    # Search by fuzzy name (no dashes)
    r = t.execute(name_or_path="fakenewsdetection", search_root=str(tmp_path))
    assert r.success is True
    assert r.output["name"] == "fake-news-detection"

def test_detect_project_top_level(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "README.md").write_text("hi")

    t = DetectProject()
    r = t.execute(name_or_path=str(tmp_path))
    assert "src" in r.output["top_level"]
    assert "tests" in r.output["top_level"]

# ── list_recent_files ────────────────────────────────────────

def test_list_recent_files_missing():
    t = ListRecentFiles()
    r = t.execute(path="/tmp/nonexistent_auraos_dir")
    assert r.success is False

def test_list_recent_files_returns_files(tmp_path):
    for name in ["a.py", "b.py", "c.md"]:
        (tmp_path / name).write_text("content")

    t = ListRecentFiles()
    r = t.execute(path=str(tmp_path), n=10)
    assert r.success is True
    names = [f["name"] for f in r.output["files"]]
    assert "a.py" in names
    assert "b.py" in names

def test_list_recent_files_respects_n(tmp_path):
    for i in range(10):
        (tmp_path / f"file{i}.py").write_text("x")

    t = ListRecentFiles()
    r = t.execute(path=str(tmp_path), n=3)
    assert len(r.output["files"]) <= 3

# ── list_projects ────────────────────────────────────────────

def test_list_projects_missing_root():
    t = ListProjects()
    r = t.execute(search_root="/tmp/nonexistent_root_auraos")
    assert r.success is False

def test_list_projects_finds_dirs(tmp_path):
    (tmp_path / "project-a").mkdir()
    (tmp_path / "project-b").mkdir()
    (tmp_path / "not-a-project.txt").write_text("file")

    t = ListProjects()
    r = t.execute(search_root=str(tmp_path))
    assert r.success is True
    names = [p["name"] for p in r.output["projects"]]
    assert "project-a" in names
    assert "project-b" in names
    assert "not-a-project.txt" not in names