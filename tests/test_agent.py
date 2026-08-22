from wiki_agents import agent, permissions


def test_build_options(vault):
    opts = agent.build_options(vault)
    assert opts.model  # WIKI_MODEL env로 오버라이드 가능, 하드코딩 리터럴 검증은 하지 않는다
    assert str(vault) == str(opts.cwd)
    assert "wiki" in opts.mcp_servers
    assert "mcp__wiki__create_claim" in opts.allowed_tools
    assert set(opts.agents) == {"ingest", "verify", "answer", "learning", "wrap", "lint"}
    assert opts.can_use_tool is not None


def test_main_agent_has_no_raw_write_or_exec(vault):
    # 구조화 쓰기는 mcp__wiki__* 도구로만: Write/Edit/Bash는 게이트 전체를 우회한다
    opts = agent.build_options(vault)
    assert "Bash" not in opts.allowed_tools
    assert "Write" not in opts.allowed_tools
    assert "Edit" not in opts.allowed_tools


def test_gated_tools_are_not_preapproved(vault):
    # allowed_tools에 들어가면 can_use_tool이 아예 호출되지 않는다 (SDK 0.2.x 동작)
    opts = agent.build_options(vault)
    for name in permissions.GATED_TOOLS:
        assert name not in opts.allowed_tools


def test_model_env_override(vault, monkeypatch):
    monkeypatch.setenv("WIKI_MODEL", "claude-test-model")
    opts = agent.build_options(vault)
    assert opts.model == "claude-test-model"
    for a in opts.agents.values():
        assert a.model == "claude-test-model"
