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
