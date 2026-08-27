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
    assert "검토 안 한 claim 1개" in text


def test_list_pending_appends_the_next_step(vault):
    import asyncio

    h = _handlers(vault)
    asyncio.run(h["create_claim"]({
        "claim": "주장", "claim_type": "technical_fact", "source_refs": ["s"]}))
    text = asyncio.run(h["list_pending"]({}))["content"][0]["text"]
    assert "검토 안 한 claim 1개" in text


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
    assert "아직 검토 안 한 claim: 0" in text


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


async def test_create_claim_tool_passes_quote_through(vault):
    h = {t.name: t for t in tools.build_wiki_tools(vault)}
    await h["create_claim"].handler({
        "claim": "브리지가 호스트 쪽에서 토큰을 붙인다",
        "claim_type": "technical_fact",
        "source_refs": ["source-20260825-001"],
        "quote": "The bridge attaches the OAuth token on the host side.",
    })
    files = list((vault / "10_Claims/pending").glob("claim-*.md"))
    assert len(files) == 1
    body = files[0].read_text(encoding="utf-8")
    assert "## 원문" in body
    assert "> The bridge attaches the OAuth token on the host side." in body


def test_create_claim_advertises_quote_as_optional(vault):
    spec = next(t for t in tools.build_wiki_tools(vault) if t.name == "create_claim")
    props = spec.input_schema["properties"]
    assert "quote" in props
    assert "quote" not in spec.input_schema["required"]


def test_repair_tool_names_present():
    assert "mcp__wiki__update_source_raw" in tools.WIKI_TOOL_NAMES
    assert "mcp__wiki__update_claim_quote" in tools.WIKI_TOOL_NAMES


async def test_create_source_reads_content_from_a_path(vault, tmp_path):
    """큰 클립을 도구 인자로 다시 타이핑하지 않게 하는 통로.

    2026-08-27에 119KB짜리 클립 4개를 문자열로 다시 적다가 곱슬따옴표 18개와
    단어 하나를 바꿔 적었다. 파일에서 읽으면 그 단계가 없어진다.
    """
    clip = tmp_path / "clip.md"
    clip.write_text("원문 그대로 “곱슬” 그리고 harness’s\n" * 20, encoding="utf-8")
    h = {t.name: t for t in tools.build_wiki_tools(vault)}
    await h["create_source"].handler({
        "origin": "browser", "content_path": str(clip), "url": "http://x"})
    written = next((vault / "00_Inbox/raw").glob("source-*.md")).read_text(encoding="utf-8")
    assert "harness’s" in written
    assert "“곱슬”" in written


async def test_create_source_rejects_both_content_and_path(vault, tmp_path):
    import pytest
    clip = tmp_path / "clip.md"
    clip.write_text("본문" * 200, encoding="utf-8")
    h = {t.name: t for t in tools.build_wiki_tools(vault)}
    with pytest.raises(ValueError, match="exactly one"):
        await h["create_source"].handler({
            "origin": "browser", "content": "본문" * 200, "content_path": str(clip)})


async def test_create_source_rejects_neither_content_nor_path(vault):
    import pytest
    h = {t.name: t for t in tools.build_wiki_tools(vault)}
    with pytest.raises(ValueError, match="exactly one"):
        await h["create_source"].handler({"origin": "browser"})


def test_create_source_advertises_content_path_as_optional(vault):
    spec = next(t for t in tools.build_wiki_tools(vault) if t.name == "create_source")
    props = spec.input_schema["properties"]
    assert "content_path" in props
    assert "content_path" not in spec.input_schema["required"]
    assert "content" not in spec.input_schema["required"]


async def test_update_source_raw_tool_reads_a_path(vault, tmp_path):
    h = {t.name: t for t in tools.build_wiki_tools(vault)}
    await h["create_source"].handler({"origin": "browser", "content": "옛 본문" * 100})
    fixed = tmp_path / "fixed.md"
    fixed.write_text("고친 본문 harness’s\n" * 30, encoding="utf-8")
    sid = next((vault / "00_Inbox/raw").glob("source-*.md")).stem
    out = await h["update_source_raw"].handler({
        "source_id": sid, "content_path": str(fixed), "reason": "원본 대조"})
    assert "updated" in out["content"][0]["text"]
    body = (vault / "00_Inbox/raw" / f"{sid}.md").read_text(encoding="utf-8")
    assert "harness’s" in body
    assert "옛 본문" not in body


async def test_update_claim_quote_tool_fixes_a_quote(vault):
    h = {t.name: t for t in tools.build_wiki_tools(vault)}
    created = await h["create_claim"].handler({
        "claim": "주장", "claim_type": "technical_fact",
        "source_refs": ["source-20260827-001"], "quote": "원문 뻔했음"})
    cid = created["content"][0]["text"].split()[1]
    await h["update_claim_quote"].handler({
        "claim_id": cid, "quote": "원문 뻔함", "reason": "원본 대조 결과 단어를 바꿔 적었다"})
    body = next((vault / "10_Claims/pending").glob("claim-*.md")).read_text(encoding="utf-8")
    assert "> 원문 뻔함" in body
    assert "뻔했음" not in body


def test_declared_names_match_the_built_tools(vault):
    """WIKI_TOOL_NAMES와 실제 도구 목록이 갈라지면 안 된다.

    도구를 추가하면서 목록 갱신을 잊으면 Claude Code 쪽 허용 목록에서 빠지는데,
    증상은 "도구가 안 보인다"라서 코드가 아니라 서버가 낡았다고 오진하기 쉽다.
    """
    built = {t.name for t in tools.build_wiki_tools(vault)}
    declared = {n.removeprefix("mcp__wiki__") for n in tools.WIKI_TOOL_NAMES}
    assert built == declared


async def test_update_wiki_page_reads_body_from_a_path(vault, tmp_path):
    """페이지 본문도 파일에서 읽을 수 있어야 한다.

    한 줄 고치려고 4KB짜리 본문을 도구 인자로 다시 타이핑하는 것이 2026-08-27 드리프트
    사고의 원인이었다. source에는 content_path를 열어줬는데 페이지에는 없어서, 링크
    8개를 바꾸는 데 7장을 통째로 다시 적어야 했다.
    """
    h = {t.name: t for t in tools.build_wiki_tools(vault)}
    await h["create_wiki_page"].handler({
        "name": "임베딩 모델", "page_type": "concept", "body": "옛 본문\n"})
    new = tmp_path / "body.md"
    new.write_text("고친 본문 harness’s\n", encoding="utf-8")
    out = await h["update_wiki_page"].handler({
        "path": "03_Resources/Concepts/임베딩-모델.md", "body_path": str(new)})
    assert "updated" in out["content"][0]["text"]
    text = (vault / "03_Resources/Concepts/임베딩-모델.md").read_text(encoding="utf-8")
    assert "고친 본문 harness’s" in text
    assert "옛 본문" not in text


async def test_update_wiki_page_rejects_both_body_and_body_path(vault, tmp_path):
    import pytest
    h = {t.name: t for t in tools.build_wiki_tools(vault)}
    await h["create_wiki_page"].handler({
        "name": "임베딩 모델", "page_type": "concept", "body": "본문\n"})
    f = tmp_path / "body.md"
    f.write_text("본문\n", encoding="utf-8")
    with pytest.raises(ValueError, match="at most one"):
        await h["update_wiki_page"].handler({
            "path": "03_Resources/Concepts/임베딩-모델.md", "body": "x", "body_path": str(f)})
