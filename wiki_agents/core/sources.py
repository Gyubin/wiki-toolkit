"""Raw capture (sources), triage records, and URL/html conversion."""
from __future__ import annotations

from pathlib import Path

from markdownify import markdownify

from .. import schema
from . import index

# HTTP 200으로 내려오는 봇 차단 페이지는 저장해봐야 쓰레기다 (실제 사고: 2026-06-07 x.com
# 캡처가 JavaScript 차단 페이지를 source로 저장했고 2026-08-22에 지웠다).
# 예전에는 이 검사가 웹 앱의 /capture 라우트에만 있어서 URL을 직접 받아올 때만 걸렸다.
# 지금은 create_source에 있으므로 어느 진입점으로 들어와도 걸린다.
_BOTWALL_MARKERS = (
    "JavaScript is not available",
    "Enable JavaScript and cookies to continue",
    "Attention Required! | Cloudflare",
    "Checking if the site connection is secure",
)


def botwall_marker(content: str) -> str | None:
    """봇 차단 페이지 특유의 문구가 있으면 그 문구를, 없으면 None을 돌려준다."""
    for marker in _BOTWALL_MARKERS:
        if marker in content:
            return marker
    return None


def create_source(
    vault: Path, *, origin: str, content: str, sensitivity: str = "personal",
    date_str: str, seq: int, url: str | None = None, subdir: str = "raw",
) -> Path:
    if sensitivity not in schema.SENSITIVITIES:
        raise ValueError(f"unknown sensitivity: {sensitivity}")
    # 길이는 여기서 막지 않는다. 짧은 붙여넣기 메모는 정상이고, 짧은 캡처는
    # lint의 thin_source가 보고한다 (확실한 것만 하드 블록, 애매한 것은 보고).
    marker = botwall_marker(content)
    if marker is not None:
        raise ValueError(
            f"capture looks like a bot-wall page (found {marker!r}); not saved. "
            "Fetch the real content first, or paste it in by hand."
        )
    sid = schema.make_id("source", date_str, seq)
    meta = {
        "type": "source", "id": sid, "origin": origin,
        "captured_at": date_str, "sensitivity": sensitivity, "url": url or "",
    }
    body = f"## Raw\n\n{content}\n"
    path = Path(vault) / "00_Inbox" / subdir / f"{sid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"{sid} already exists; pick a fresh seq")
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.append_log(vault, "ingest-log", f"captured {sid} from {origin} [{sensitivity}]")
    return path


def triage_record(vault: Path, source_id: str, decision: str, date_str: str) -> None:
    if decision not in ("drop", "keep-as-link", "deep"):
        raise ValueError(f"unknown triage decision: {decision}")
    index.append_log(vault, "ingest-log", f"triage {source_id} -> {decision}")


def html_to_markdown(html: str) -> str:
    return markdownify(html, heading_style="ATX").strip()
