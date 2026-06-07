from wiki_agent import subagents


def test_build_subagents_has_lint():
    agents = subagents.build_subagents()
    assert set(agents) == {"ingest", "verify", "answer", "learning", "wrap", "lint"}
    assert "Write" not in (agents["lint"].tools or [])
    assert "Bash" not in (agents["lint"].tools or [])
    assert "Read" in agents["lint"].tools
