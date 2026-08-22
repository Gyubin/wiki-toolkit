from wiki_agents import tools


def test_build_wiki_server(vault):
    server = tools.build_wiki_server(vault)
    assert server is not None  # McpSdkServerConfig


def test_tool_names_list():
    names = tools.WIKI_TOOL_NAMES
    assert "mcp__wiki__create_claim" in names
    assert "mcp__wiki__promote_claim" in names


def test_wrap_tool_names_present():
    names = tools.WIKI_TOOL_NAMES
    assert "mcp__wiki__collect_git_session" in names
    assert "mcp__wiki__create_session_summary" in names
    assert "mcp__wiki__create_decision" in names


def test_search_tool_name_present():
    assert "mcp__wiki__search_wiki" in tools.WIKI_TOOL_NAMES


def test_update_wiki_page_tool_present():
    assert "mcp__wiki__update_wiki_page" in tools.WIKI_TOOL_NAMES


def test_update_wiki_page_is_confined_to_resources(vault):
    import pytest
    p = tools.resolve_wiki_page_path(vault, "03_Resources/Concepts/some-page.md")
    assert p.name == "some-page.md"
    with pytest.raises(ValueError):
        # 클레임 파일 status를 게이트 없이 바꾸는 우회로가 되면 안 된다
        tools.resolve_wiki_page_path(vault, "10_Claims/pending/claim-20260101-001.md")
    with pytest.raises(ValueError):
        tools.resolve_wiki_page_path(vault, "03_Resources/../10_Claims/x.md")
