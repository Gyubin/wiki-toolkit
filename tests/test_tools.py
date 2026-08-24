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


def test_vault_next_step_tool_present():
    assert "mcp__wiki__vault_next_step" in tools.WIKI_TOOL_NAMES


def _handlers(vault):
    return {t.name: t.handler for t in tools.build_wiki_tools(vault)}


def test_write_tools_append_the_next_step(vault):
    """쓰기 결과에 다음 단계가 붙어야 한다 (프롬프트가 아니라 데이터 경로에 있는 안내)."""
    import asyncio

    h = _handlers(vault)
    out = asyncio.run(h["create_claim"]({
        "claim": "주장", "claim_type": "technical_fact", "source_refs": ["s"]}))
    text = out["content"][0]["text"]
    assert "created" in text
    assert "pending claim 1개" in text


def test_list_pending_appends_the_next_step(vault):
    import asyncio

    h = _handlers(vault)
    asyncio.run(h["create_claim"]({
        "claim": "주장", "claim_type": "technical_fact", "source_refs": ["s"]}))
    text = asyncio.run(h["list_pending"]({}))["content"][0]["text"]
    assert "pending claim 1개" in text


def test_next_step_advances_after_verification(vault):
    """승인하고 나면 안내가 wiki page 단계로 넘어가야 한다."""
    import asyncio

    h = _handlers(vault)
    created = asyncio.run(h["create_claim"]({
        "claim": "주장", "claim_type": "technical_fact", "source_refs": ["s"]}))
    cid = created["content"][0]["text"].split()[1]
    out = asyncio.run(h["promote_claim"]({
        "claim_id": cid, "target_status": "verified", "evidence_refs": ["core/search.py:20"]}))
    assert "wiki page" in out["content"][0]["text"]


def test_vault_next_step_tool_reports_counts(vault):
    import asyncio

    h = _handlers(vault)
    text = asyncio.run(h["vault_next_step"]({}))["content"][0]["text"]
    assert "대기 중인 단계 없음" in text
    assert "pending claim: 0" in text


async def test_write_tool_survives_a_broken_file_elsewhere_in_the_vault(vault):
    """쓰기가 성공했으면 도구는 성공을 보고해야 한다.

    쓰기 뒤에 붙는 "다음: ..." 힌트는 vault 전체를 훑는다. 그 계산이 터지면 파일은
    이미 만들어졌는데 도구는 실패로 보이고, 모델은 다시 써서 중복 claim을 만든다.
    힌트는 부가 정보이므로 무슨 이유로든 못 만들면 조용히 생략한다.
    """
    (vault / "30_Learning/flashcards/learning-20260825-001.md").write_text(
        "---\nfoo: [unclosed\n---\nbody\n", encoding="utf-8")
    h = {t.name: t for t in tools.build_wiki_tools(vault)}
    res = await h["create_claim"].handler({"claim": "테스트 주장", "claim_type": "opinion"})
    assert "created" in res["content"][0]["text"]
    assert list((vault / "10_Claims/pending").glob("claim-*.md"))
