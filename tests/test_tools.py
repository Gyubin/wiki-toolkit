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
