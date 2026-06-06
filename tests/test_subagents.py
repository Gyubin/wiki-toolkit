from wiki_agent import subagents


def test_build_subagents_has_wrap():
    agents = subagents.build_subagents()
    assert set(agents) == {"ingest", "verify", "answer", "learning", "wrap"}
    assert "Bash" in agents["wrap"].tools
    assert "mcp__wiki__collect_git_session" in agents["wrap"].tools
    # answer still cannot Write
    assert "Write" not in (agents["answer"].tools or [])
