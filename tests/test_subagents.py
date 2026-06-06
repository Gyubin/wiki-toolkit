from wiki_agent import subagents


def test_build_subagents_has_four():
    agents = subagents.build_subagents()
    assert set(agents) == {"ingest", "verify", "answer", "learning"}
    assert "Read" in agents["answer"].tools
    # answer must not be able to Write
    assert "Write" not in (agents["answer"].tools or [])
