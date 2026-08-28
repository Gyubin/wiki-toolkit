from wiki_toolkit import schema
from wiki_toolkit.core import sources


def test_create_source_personal(vault):
    path = sources.create_source(
        vault, origin="chatgpt", content="raw conversation text",
        sensitivity="personal", date_str="2026-06-07", seq=1, url="http://x",
    )
    assert path.exists()
    meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["type"] == "source"
    assert meta["id"] == "source-20260607-001"
    assert meta["sensitivity"] == "personal"
    assert "raw conversation text" in body
    log = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "source-20260607-001" in log


def test_create_source_tags_work(vault):
    path = sources.create_source(
        vault, origin="coding_agent", content="company code",
        sensitivity="work", date_str="2026-06-07", seq=2,
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["sensitivity"] == "work"


def test_triage_record(vault):
    sources.create_source(vault, origin="chatgpt", content="raw text " * 30,
                          date_str="2026-06-07", seq=1, url="http://x")
    sources.triage_record(vault, "source-20260607-001", "deep", "2026-06-07")
    log = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "triage" in log and "deep" in log


def test_html_to_markdown():
    md = sources.html_to_markdown("<h1>Title</h1><p>Hello <b>world</b></p>")
    assert "Title" in md
    assert "world" in md


def test_create_source_rejects_botwall_page(vault):
    """웹 앱에만 있던 봇월 검사가 이제 create_source 자체에 걸린다.

    2026-06-07에 x.com 캡처가 JavaScript 차단 페이지를 source로 저장했고,
    그 검사는 /capture 라우트에만 있어서 MCP 경로로 들어오면 안 걸렸다.
    """
    import pytest
    with pytest.raises(ValueError, match="bot-wall"):
        sources.create_source(
            vault, origin="browser",
            content="x.com\nJavaScript is not available.\nWe've detected that...",
            date_str="2026-06-07", seq=9, url="https://x.com/some/status",
        )
    assert not (vault / "00_Inbox/raw/source-20260607-009.md").exists()


def test_botwall_marker_reports_which_marker():
    assert sources.botwall_marker("Attention Required! | Cloudflare") \
        == "Attention Required! | Cloudflare"
    assert sources.botwall_marker("정상적인 본문입니다") is None


def test_create_source_allows_short_pasted_note(vault):
    """길이는 create_source가 막지 않는다. 짧은 메모는 정상이고, lint가 보고한다."""
    path = sources.create_source(
        vault, origin="manual", content="짧은 메모",
        date_str="2026-06-07", seq=8, url="http://x",
    )
    assert path.exists()


def test_update_source_raw_replaces_body_and_keeps_frontmatter(vault):
    """Raw 본문만 갈아끼운다. id/url/captured_at은 그대로여야 한다."""
    p = sources.create_source(
        vault, origin="browser", content="원문 A" * 50,
        date_str="2026-08-27", seq=1, url="http://x",
    )
    sources.update_source_raw(
        vault, "source-20260827-001", content="원문 B" * 50,
        reason="원본 대조 결과 곱슬따옴표를 잘못 옮겨 적었다",
    )
    meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
    assert meta["id"] == "source-20260827-001"
    assert meta["url"] == "http://x"
    assert meta["captured_at"] == "2026-08-27"
    assert meta["origin"] == "browser"
    assert "원문 B" in body
    assert "원문 A" not in body
    log = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "곱슬따옴표를 잘못 옮겨 적었다" in log


def test_update_source_raw_requires_a_reason(vault):
    """캡처를 사후에 바꾸는 일이라 왜가 없으면 나중에 이 vault를 믿을 수 없다."""
    import pytest
    sources.create_source(vault, origin="browser", content="A" * 300,
                          date_str="2026-08-27", seq=1)
    with pytest.raises(ValueError, match="reason"):
        sources.update_source_raw(vault, "source-20260827-001", content="B" * 300,
                                  reason="   ")


def test_update_source_raw_rejects_a_noop(vault):
    import pytest
    sources.create_source(vault, origin="browser", content="A" * 300,
                          date_str="2026-08-27", seq=1)
    with pytest.raises(ValueError, match="unchanged"):
        sources.update_source_raw(vault, "source-20260827-001", content="A" * 300,
                                  reason="바꿀 게 없다")


def test_update_source_raw_rejects_unknown_id(vault):
    import pytest
    with pytest.raises(FileNotFoundError):
        sources.update_source_raw(vault, "source-20990101-001", content="B" * 300,
                                  reason="없는 id")


def test_update_source_raw_rejects_botwall_replacement(vault):
    """되돌린다면서 봇월 페이지를 밀어넣는 것도 막는다."""
    import pytest
    sources.create_source(vault, origin="browser", content="A" * 300,
                          date_str="2026-08-27", seq=1)
    with pytest.raises(ValueError, match="bot-wall"):
        sources.update_source_raw(
            vault, "source-20260827-001",
            content="JavaScript is not available." + "x" * 300,
            reason="재캡처")


def test_find_source_resolves_a_renamed_file_by_frontmatter_id(vault):
    """파일명이 제목으로 바뀌어도 id로 찾을 수 있어야 update_source_raw가 돈다."""
    sources.create_source(vault, origin="browser", content="옛 본문" * 100,
                          date_str="2026-08-27", seq=1, url="http://x")
    raw = vault / "00_Inbox/raw"
    (raw / "source-20260827-001.md").rename(raw / "Expert Parallel Deployment 이해하기.md")
    found = sources.find_source(vault, "source-20260827-001")
    assert found.name == "Expert Parallel Deployment 이해하기.md"
    sources.update_source_raw(vault, "source-20260827-001", content="새 본문" * 100,
                              reason="이름 바뀐 파일에도 써져야 한다")
    assert "새 본문" in found.read_text(encoding="utf-8")


def test_create_source_uses_the_title_as_the_filename(vault):
    """파일명은 사람이 읽고 id는 frontmatter가 든다.

    이걸 안 하면 다음 ingest부터 다시 source-YYYYMMDD-NNN.md가 생겨서 그래프와 파일
    탐색기가 도로 안 읽히는 상태가 된다.
    """
    p = sources.create_source(
        vault, origin="browser", content="본문" * 200, date_str="2026-08-28", seq=1,
        url="http://x", title="Expert Parallel Deployment 이해하기",
    )
    assert p.name == "Expert Parallel Deployment 이해하기.md"
    meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
    assert meta["id"] == "source-20260828-001"


def test_create_source_falls_back_to_the_id_without_a_title(vault):
    p = sources.create_source(vault, origin="browser", content="본문" * 200,
                              date_str="2026-08-28", seq=2)
    assert p.name == "source-20260828-002.md"


def test_create_source_sanitizes_a_title_that_cannot_be_a_filename(vault):
    """제목에 / 나 : 가 들어오면 파일을 못 만들거나 엉뚱한 디렉터리에 쓴다."""
    p = sources.create_source(
        vault, origin="browser", content="본문" * 200, date_str="2026-08-28", seq=3,
        title="Quantization: What INT8/INT4 Really Do\n",
    )
    assert "/" not in p.name and ":" not in p.name
    assert p.name.endswith(".md") and p.parent.name == "raw"


def test_create_source_rejects_a_title_already_taken(vault):
    import pytest
    sources.create_source(vault, origin="browser", content="본문" * 200,
                          date_str="2026-08-28", seq=1, title="같은 제목")
    with pytest.raises(FileExistsError, match="같은 제목"):
        sources.create_source(vault, origin="browser", content="다른 본문" * 200,
                              date_str="2026-08-28", seq=2, title="같은 제목")


def test_triage_record_requires_an_existing_source(vault):
    """id를 한 자리 잘못 치면 없는 source에 대한 triage가 조용히 남는 버그의 재발 방지."""
    import pytest
    with pytest.raises(FileNotFoundError, match="no such source"):
        sources.triage_record(vault, "source-20260607-999", "deep", "2026-06-07")


def test_find_source_rejects_glob_and_traversal(vault):
    """source_id는 rglob 패턴에 합류한다. `*`와 `../`가 파일 조회에 닿으면 안 된다."""
    import pytest
    for bad in ("*", "../outside", "source-*", "source-2026/../x"):
        with pytest.raises(ValueError):
            sources.find_source(vault, bad)


def test_max_sensitivity_inherits_the_highest(vault):
    sources.create_source(vault, origin="browser", content="p " * 200,
                          sensitivity="personal", date_str="2026-08-28", seq=1)
    sources.create_source(vault, origin="browser", content="c " * 200,
                          sensitivity="confidential", date_str="2026-08-28", seq=2)
    both = ["source-20260828-001", "source-20260828-002"]
    assert sources.max_sensitivity(vault, both) == "confidential"
    assert sources.max_sensitivity(vault, both[:1]) == "personal"
    # 없는 id와 id 모양이 아닌 자유 텍스트 출처는 건너뛴다
    assert sources.max_sensitivity(vault, ["자유 텍스트 출처", "source-20260828-009"]) == "personal"
    assert sources.max_sensitivity(vault, None) == "personal"


_LATEXML = (
    '<svg id="A1.p1.pic1" height="45" viewBox="0 0 477 45"><g transform="translate(0,45)">'
    '<foreignObject width="477" height="45"><span>You</span> <span>are</span> '
    '<span>Faraday</span><span>,</span><span>an</span> <span>autonomous</span> '
    '<span>AI</span> <span>researcher</span><span>.</span><span>You</span> '
    '<span>operate</span> <span>inside</span> <span>a</span> <span>container</span>'
    "</foreignObject></g></svg>"
)
_DIAGRAM = (
    '<svg viewBox="0 0 764 348" role="img" aria-label="Diagram of the candidate selector">'
    '<g><path d="M0 0 L10 10"/></g></svg>'
)
_BARE = '<svg viewBox="0 0 10 10"><path d="M0 0 L1 1"/><path d="M2 2 L3 3"/></svg>'


def test_foreign_object_text_is_restored_not_dropped():
    out, report = sources.strip_svg(f"앞\n\n{_LATEXML}\n\n뒤")
    assert "autonomous AI researcher" in out
    assert "viewBox" not in out and "<span" not in out
    assert "앞" in out and "뒤" in out
    assert [r["kind"] for r in report] == ["restored"]
    assert report[0]["after"] < report[0]["before"]


def test_restored_text_is_marked_so_quotes_are_known_to_be_reflowed():
    out, _ = sources.strip_svg(_LATEXML)
    assert sources.SVG_RESTORED_OPEN in out
    assert sources.SVG_RESTORED_CLOSE in out


def test_diagram_falls_back_to_aria_label():
    out, report = sources.strip_svg(_DIAGRAM)
    assert out == "[그림: Diagram of the candidate selector]"
    assert [r["kind"] for r in report] == ["label"]


def test_svg_with_neither_text_nor_label_is_dropped_with_its_size():
    out, report = sources.strip_svg(_BARE)
    assert out == f"[svg 생략: {len(_BARE)}자]"
    assert [r["kind"] for r in report] == ["dropped"]


def test_content_without_svg_is_untouched():
    body = "# 제목\n\n본문 <span>인라인</span> 계속\n"
    out, report = sources.strip_svg(body)
    assert out == body
    assert report == []


def test_every_svg_in_a_document_is_handled():
    out, report = sources.strip_svg(f"a{_LATEXML}b{_DIAGRAM}c{_BARE}d")
    assert "<svg" not in out
    assert [r["kind"] for r in report] == ["restored", "label", "dropped"]


_CHART = (
    '<svg role="application" width="653" height="280"><g><text x="1" y="2">Draft position'
    '</text><text x="3" y="4">Recall@1 (%)</text><path d="M0 0 L1 1"/></g></svg>'
)


def test_chart_without_aria_label_keeps_its_axis_text():
    out, report = sources.strip_svg(_CHART)
    assert out == "[그림 텍스트: Draft position Recall@1 (%)]"
    assert [r["kind"] for r in report] == ["axes"]


def test_create_source_strips_svg_automatically(vault):
    body = f"앞\n\n{_LATEXML}\n\n뒤"
    path = sources.create_source(
        vault, origin="browser", content=body, date_str="2026-08-28", seq=1)
    _, raw = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert "<svg" not in raw
    assert "autonomous AI researcher" in raw   # 내용은 남는다
    assert sources.SVG_RESTORED_OPEN in raw    # 재배치됐다는 표시도 남는다


def test_create_source_logs_what_the_svg_pass_removed(vault):
    sources.create_source(
        vault, origin="browser", content=f"앞{_LATEXML}뒤",
        date_str="2026-08-28", seq=1)
    log = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "svg 1개 정리 [restored 1]" in log


def test_create_source_without_svg_logs_nothing_extra(vault):
    sources.create_source(
        vault, origin="chatgpt", content="그냥 텍스트", date_str="2026-08-28", seq=1)
    log = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "svg" not in log


def test_update_source_raw_strips_svg_so_restore_does_not_bring_it_back(vault):
    """되돌리기는 커밋된 원본 클립을 다시 넘기는 것이라 svg가 들어 있다."""
    sources.create_source(
        vault, origin="browser", content="첫 캡처", date_str="2026-08-28", seq=1)
    path = sources.update_source_raw(
        vault, "source-20260828-001", content=f"원본{_LATEXML}복원",
        reason="원본 클립에서 되돌림")
    _, raw = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert "<svg" not in raw
    assert "autonomous AI researcher" in raw
