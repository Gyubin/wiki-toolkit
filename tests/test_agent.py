from wiki_agent import agent


def test_build_options(vault):
    opts = agent.build_options(vault)
    assert opts.model == "claude-opus-4-8"
    assert str(vault) == str(opts.cwd)
    assert "wiki" in opts.mcp_servers
    assert "mcp__wiki__create_claim" in opts.allowed_tools
    assert set(opts.agents) == {"ingest", "verify", "answer", "learning", "wrap", "lint"}
    assert opts.can_use_tool is not None
