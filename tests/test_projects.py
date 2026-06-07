from wiki_agents import schema
from wiki_agents.core import projects


def test_ensure_project(vault):
    base = projects.ensure_project(vault, "/some/path/MyRepo")
    assert base.name == "myrepo"
    assert (base / "sessions").is_dir()
    assert (base / "decisions").is_dir()
    assert (base / "project-index.md").exists()


def test_create_session_summary(vault):
    p = projects.create_session_summary(
        vault, repo="/x/MyRepo", title="add auth", body="## Goal\n\nx\n",
        date_str="2026-06-07", seq=1,
    )
    assert p.parent.name == "sessions"
    meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
    assert meta["type"] == "session"
    assert meta["repo"] == "myrepo"
    assert meta["sensitivity"] == "work"


def test_create_decision(vault):
    p = projects.create_decision(
        vault, repo="/x/MyRepo", title="use JWT", context="c", decision="d",
        alternatives="a", consequences="q", date_str="2026-06-07", seq=1,
    )
    assert p.parent.name == "decisions"
    meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
    assert meta["type"] == "decision"
    assert "## Context" in body and "## Consequences" in body
