from wiki_agent import subagents


def test_build_subagents_has_lint():
    agents = subagents.build_subagents()
    assert set(agents) == {"ingest", "verify", "answer", "learning", "wrap", "lint"}
    assert "Write" not in (agents["lint"].tools or [])
    assert "Bash" not in (agents["lint"].tools or [])
    assert "Read" in agents["lint"].tools


def test_answer_has_search():
    agents = subagents.build_subagents()
    assert "mcp__wiki__search_wiki" in agents["answer"].tools
