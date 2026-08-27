from wiki_agents import schema
from wiki_agents.core import sources


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
