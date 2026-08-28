"""Raw capture (sources), triage records, and URL/html conversion."""
from __future__ import annotations

import re
from html import unescape
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


# 파일 시스템이 못 받거나 경로를 갈라놓는 문자들. 제목을 파일명으로 쓰려면 먼저 걷어낸다.
_UNSAFE_IN_NAME = re.compile(r'[/\\:*?"<>|\x00-\x1f]')


def source_filename(source_id: str, title: str | None) -> str:
    """사람이 읽을 파일명. 제목이 없거나 다 걷어내고 남는 게 없으면 id로 돌아간다.

    파일명은 사람이 읽고 id는 frontmatter가 든다. Obsidian의 그래프 뷰와 파일 탐색기,
    빠른 전환은 전부 파일명을 보여주기 때문에, source-20260827-004 같은 이름이면
    무엇에 대한 글인지 열어봐야 안다.
    """
    if not title:
        return f"{source_id}.md"
    clean = _UNSAFE_IN_NAME.sub(" ", title)
    clean = " ".join(clean.split()).strip(". ")[:120]
    return f"{clean}.md" if clean else f"{source_id}.md"


def create_source(
    vault: Path, *, origin: str, content: str, sensitivity: str = "personal",
    date_str: str, seq: int, url: str | None = None, subdir: str = "raw",
    title: str | None = None,
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
    path = Path(vault) / "00_Inbox" / subdir / source_filename(sid, title)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(
            f"{path.name} already exists; pick a different title (or a fresh seq)")
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.append_log(vault, "ingest-log", f"captured {sid} from {origin} [{sensitivity}]")
    return path


def find_source(vault: Path, source_id: str) -> Path:
    """파일명이 id인 경우를 먼저 보고, 없으면 frontmatter의 `id`로 찾는다.

    source 파일명은 사람이 읽을 제목으로 바뀔 수 있다 (그래야 Obsidian 그래프와 파일
    탐색기에서 읽힌다). 파일명으로만 찾으면 그 순간 update_source_raw가 파일을 못 찾는다.
    """
    schema.validate_doc_id(source_id, "source")
    base = Path(vault) / "00_Inbox"
    for p in base.rglob(f"{source_id}.md"):
        return p
    for p in base.rglob("*.md"):
        try:
            meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: S112 - 깨진 파일은 lint의 몫
            continue
        if meta.get("id") == source_id:
            return p
    raise FileNotFoundError(f"no such source: {source_id} (searched 00_Inbox)")


def max_sensitivity(vault: Path, source_ids: list[str] | None) -> str:
    """참조된 source들 중 가장 민감한 값. claim이 source의 민감도를 상속할 때 쓴다.

    claim은 원문 인용을 verbatim으로 담으므로, confidential source에서 나온 claim이
    personal로 태어나면 그 인용문이 임베딩 API로 나간다 (감사 발견). 없는 id나
    id 모양이 아닌 자유 텍스트 출처는 건너뛴다.
    """
    rank = {s: i for i, s in enumerate(schema.SENSITIVITIES)}
    best = "personal"
    for sid in source_ids or []:
        try:
            meta, _ = schema.parse_doc(
                find_source(vault, str(sid)).read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError, OSError):
            continue
        s = str(meta.get("sensitivity") or "personal")
        if rank.get(s, 0) > rank[best]:
            best = s
    return best


def update_source_raw(vault: Path, source_id: str, *, content: str, reason: str) -> Path:
    """`## Raw` 본문만 교체한다. frontmatter는 건드리지 않는다.

    Raw 본문은 캡처 원본과 같아야 하는데, 모델이 원문을 도구 인자로 다시 타이핑하는
    과정에서 조용히 뒤틀린다. 2026-08-27에 클립 4개(119KB)를 인제스트하면서 곱슬따옴표
    18개를 곧은 따옴표로 바꿔 적었고, 한 곳은 단어를 바꿨다("푸시할 뻔함" ->
    "푸시할 뻔했음"). 원본 바이트가 남아 있으면 이 함수로 되돌린다.

    `reason`이 필수인 이유: 캡처를 사후에 바꾸는 일이라 로그에 왜가 없으면 나중에
    이 vault를 믿을 수 없다. 되돌린 것인지 덮어쓴 것인지 구별이 안 된다.
    """
    if not reason.strip():
        raise ValueError(
            "update_source_raw needs a reason (why this capture is being rewritten)")
    if not content.strip():
        raise ValueError("refusing to blank a source body")
    marker = botwall_marker(content)
    if marker is not None:
        raise ValueError(
            f"replacement looks like a bot-wall page (found {marker!r}); not saved.")
    path = find_source(vault, source_id)
    meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
    new_body = f"## Raw\n\n{content}\n"
    if new_body == body:
        raise ValueError(f"{source_id} raw body is unchanged; nothing to write")
    path.write_text(schema.render_doc(meta, new_body), encoding="utf-8")
    index.append_log(
        vault, "ingest-log",
        f"raw body rewritten for {source_id}: {len(body)} -> {len(new_body)} chars "
        f"({reason.strip()})")
    return path


def triage_record(vault: Path, source_id: str, decision: str, date_str: str) -> None:
    if decision not in ("drop", "keep-as-link", "deep"):
        raise ValueError(f"unknown triage decision: {decision}")
    # id를 한 자리 잘못 치면 없는 source에 대한 triage가 조용히 남고, 진짜 source는
    # triage 없이 지나간다. 이를 잡는 소비자가 없으므로 여기서 존재를 확인한다.
    find_source(vault, source_id)
    index.append_log(vault, "ingest-log", f"triage {source_id} -> {decision}")


def html_to_markdown(html: str) -> str:
    return markdownify(html, heading_style="ATX").strip()


# arxiv의 LaTeXML HTML과 일부 블로그는 그림과 코드 리스팅을 인라인 <svg>로 박아 보낸다.
# 클리퍼는 그 마크업을 그대로 떠 온다. 2026-08-28 실측: arxiv 2608.13331 클립 906KB 중
# 782KB(86%)가 svg 8개였고, 그중 하나는 한 줄이 148,877자였다. 이대로 source로 넣으면
# 본문 대부분이 좌표와 스타일 문자열이 되고, BM25 토큰도 그만큼 쓰레기가 된다.
#
# 그런데 통째로 지우면 안 된다. 그 8개는 논문의 Appendix G(프롬프트 전문)였고 텍스트가
# <foreignObject> 안에 들어 있었다. 반대로 DFlash 2 클립의 svg 4개는 진짜 다이어그램이고
# 대신 aria-label에 설명이 붙어 있었다. 그래서 셋으로 나눠 처리한다.
_SVG_BLOCK = re.compile(r"<svg\b[^>]*>.*?</svg>", re.DOTALL | re.IGNORECASE)
_FOREIGN_OBJECT = re.compile(r"<foreignObject\b[^>]*>(.*?)</foreignObject>",
                             re.DOTALL | re.IGNORECASE)
_ARIA_LABEL = re.compile(r'\baria-label="([^"]*)"', re.IGNORECASE)
_SVG_TEXT_EL = re.compile(r"<text\b[^>]*>(.*?)</text>", re.DOTALL | re.IGNORECASE)
_TAG = re.compile(r"<[^>]+>")
# 이보다 짧게 복원되면 텍스트가 아니라 라벨 조각이다 (축 눈금, 범례 한 글자 등).
_SVG_MIN_TEXT = 40
SVG_RESTORED_OPEN = "<!-- svg 텍스트 복원 시작: 줄바꿈과 띄어쓰기가 원문과 다를 수 있다 -->"
SVG_RESTORED_CLOSE = "<!-- svg 텍스트 복원 끝 -->"


def _svg_inner_text(block: str) -> str:
    """svg 안의 <foreignObject>에서 사람이 읽는 텍스트만 뽑는다.

    LaTeXML은 리스팅 한 줄을 단어 단위 <span>으로 쪼개 넣는데, span 사이의 공백은 살아 있고
    줄바꿈은 마크업에 아예 없다. 그래서 복원된 텍스트는 한 문단으로 이어지고 원문과 글자가
    같아도 배치가 다르다. 인용할 때 이 점을 알아야 하므로 호출부가 마커로 감싼다.
    """
    parts = _FOREIGN_OBJECT.findall(block)
    if not parts:
        return ""
    text = unescape(_TAG.sub("", "\n".join(parts)))
    return " ".join(text.split())


def strip_svg(content: str) -> tuple[str, list[dict]]:
    """인라인 svg를 텍스트나 라벨로 바꾼 본문과, 무엇을 어떻게 바꿨는지의 목록을 돌려준다.

    바꾸기만 하고 판단은 안 한다. 클립을 이 함수에 통과시킬지는 호출부가 정하고, 원본
    바이트는 클립을 먼저 커밋해 git에 남긴다 (CLAUDE.md의 Inbox 처리 순서).
    """
    report: list[dict] = []

    def _replace(m: re.Match[str]) -> str:
        block = m.group()
        text = _svg_inner_text(block)
        if len(text) >= _SVG_MIN_TEXT:
            report.append({"kind": "restored", "before": len(block), "after": len(text)})
            return f"{SVG_RESTORED_OPEN}\n\n{text}\n\n{SVG_RESTORED_CLOSE}"
        label = _ARIA_LABEL.search(block)
        if label and label.group(1).strip():
            out = f"[그림: {label.group(1).strip()}]"
            report.append({"kind": "label", "before": len(block), "after": len(out)})
            return out
        # 차트는 aria-label 없이 축 이름만 <text>로 들고 있는 경우가 많다. 그것만으로도
        # "무엇을 그린 그림인지"는 남으므로 크기 숫자보다 낫다 (DFlash 2 클립의 svg 2개).
        axes = " ".join(" ".join(unescape(_TAG.sub("", t)).split())
                        for t in _SVG_TEXT_EL.findall(block)).strip()
        if axes:
            out = f"[그림 텍스트: {axes}]"
            report.append({"kind": "axes", "before": len(block), "after": len(out)})
            return out
        out = f"[svg 생략: {len(block)}자]"
        report.append({"kind": "dropped", "before": len(block), "after": len(out)})
        return out

    return _SVG_BLOCK.sub(_replace, content), report
