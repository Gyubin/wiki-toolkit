"""Deterministic, report-only vault hygiene checks (no LLM)."""
from __future__ import annotations

import re
from pathlib import Path

from .. import schema
from .claims import _STATUS_DIR, extract_quote, has_written_evidence, normalize_key

_SEV_ORDER = {"error": 0, "warning": 1, "info": 2}

# index 파일 -> 항목 파일이 있어야 하는 루트
_INDEX_ROOTS = {
    "claim-index": "10_Claims",
    "learning-index": "30_Learning",
    "wiki-index": "03_Resources",
}


def _f(check: str, severity: str, ref: str, message: str) -> dict:
    return {"check": check, "severity": severity, "ref": ref, "message": message}


_ID_SHAPED = schema.ID_SHAPED  # id 모양의 단일 출처는 schema다

# 실패한 캡처는 대개 짧다. 봇월 문구가 있으면 create_source가 아예 막지만, 문구 없이
# 껍데기만 내려오는 경우가 있어서 여기서 보고한다. 짧은 붙여넣기 메모도 걸리므로
# 하드 블록이 아니라 warning이다.
_MIN_SOURCE_CHARS = 200

# 인용문 안에서 "여기를 건너뛰었다"를 나타내는 표시. quote_not_in_source는 이 기준으로
# 쪼개 조각별로 원문에서 찾는다.
_ELISION = "(...)"


def _norm_ws(s: str) -> str:
    """공백만 접는다. 줄바꿈 위치는 인용문 판정 대상이 아니다."""
    return re.sub(r"\s+", " ", s).strip()


def _parse_full(p: Path) -> tuple[dict, str] | None:
    """(meta, body), 또는 파싱 불가/펜스 손상이면 None.

    parse_doc은 닫는 펜스가 없는 파일을 조용히 ({}, 원문)으로 돌려주므로,
    '---'로 시작하는데 meta가 비면 손상으로 취급해야 한다. 안 그러면 lint는
    침묵하는데 list_pending 같은 소비자는 그 파일에서 죽는 모순이 생긴다.

    **파싱 경로는 여기 하나뿐이어야 한다.** run_checks 안에서 schema.parse_doc을 직접
    부르면 이 방어를 우회한다. 실제로 그렇게 했다가 깨졌다: thin_source 검사가
    parse_doc을 직접 부르면서 OSError만 잡았는데, 제목에 콜론이 든 Web Clipper 클립
    하나가 yaml.ScannerError로 lint 전체를 죽였다. 그것도 unparseable을 보고하는
    아래 순회보다 먼저 돌아서, 보고 대신 트레이스백이 나갔다.
    """
    try:
        text = p.read_text(encoding="utf-8")
        meta, body = schema.parse_doc(text)
    except Exception:
        return None
    if not meta and text.startswith("---"):
        return None
    return meta, body


def _parse(p: Path) -> dict | None:
    """meta만 필요할 때. 파싱 불가면 None."""
    parsed = _parse_full(p)
    return None if parsed is None else parsed[0]


def run_checks(vault: Path, today_str: str) -> list[dict]:
    vault = Path(vault)
    findings: list[dict] = []
    claim_metas: list[dict] = []
    id_files: dict[str, list[str]] = {}

    quoted: list[tuple[str, list[str], str]] = []  # (claim ref, source_refs, 인용문)

    for p in (vault / "10_Claims").rglob("claim-*.md"):
        parsed = _parse_full(p)
        if parsed is None:
            continue  # 아래 전체 순회에서 unparseable로 보고된다
        meta, claim_body = parsed
        claim_metas.append(meta)
        quote = extract_quote(claim_body)
        if quote:
            quoted.append((meta.get("id", str(p)), list(meta.get("source_refs") or []), quote))
        d = p.parent.name
        status = meta.get("status")
        ref = meta.get("id", str(p))
        if status in _STATUS_DIR and _STATUS_DIR[status] != d:
            findings.append(_f("status_folder_mismatch", "error", ref,
                               f"status '{status}' belongs in '{_STATUS_DIR[status]}', "
                               f"found in '{d}'"))
        if not meta.get("source_refs"):
            findings.append(_f("missing_source_refs", "warning", ref, "claim has no source_refs"))
        if status == "verified" and not has_written_evidence(meta.get("evidence_refs")):
            # 게이트(promote_claim)와 같은 판정을 쓴다. truthiness만 보면 [""]가
            # 게이트를 통과했을 때 여기도 침묵해서 안전망이 같이 뚫린다.
            findings.append(_f("verified_without_evidence", "warning", ref,
                               "verified claim has no written evidence_refs"))

    groups: dict[str, list[str]] = {}
    for meta in claim_metas:
        key = normalize_key(meta.get("claim", ""), meta.get("speaker") or None)
        groups.setdefault(key, []).append(meta.get("id", "?"))
    for ids in groups.values():
        if len(ids) > 1:
            findings.append(_f("duplicate_claim", "warning", ", ".join(sorted(ids)),
                               "claims share a normalized key (possible duplicate)"))

    for p in (vault / "03_Resources").rglob("*.md"):
        meta = _parse(p)
        if meta and meta.get("type") in schema.WIKI_PAGE_TYPES and not meta.get("claim_refs"):
            findings.append(_f("orphan_wiki", "info", meta.get("name", str(p)),
                               "wiki page has no claim_refs"))

    source_bodies: dict[str, str] = {}
    inbox_source_urls: set[str] = set()  # ingest 끝난 클립 원본 판정용 (pipeline과 같은 기준)
    for p in (vault / "00_Inbox").rglob("*.md"):
        parsed = _parse_full(p)
        if parsed is None:
            continue  # 아래 전체 순회에서 unparseable로 보고된다
        meta, body = parsed
        if meta.get("id") and meta.get("url"):
            inbox_source_urls.add(str(meta["url"]))
        if meta.get("type") != "source":
            continue
        if meta.get("id"):
            source_bodies[str(meta["id"])] = _norm_ws(body)
        size = len(body.strip())
        if size < _MIN_SOURCE_CHARS:
            findings.append(_f("thin_source", "warning",
                               meta.get("id", str(p.relative_to(vault))),
                               f"source body is only {size} chars (under {_MIN_SOURCE_CHARS}); "
                               "a failed capture looks like this"))

    # claim의 인용문이 그 source의 Raw 본문에 문자 그대로 있는지 본다.
    #
    # 계약(prompts/ingest.md)은 인용문을 "copied verbatim"으로 요구하는데, 그걸 지켰는지
    # 보는 검사가 없었다. 2026-08-27에 클립 4개를 인제스트하면서 곱슬따옴표 18개와 단어
    # 하나를 바꿔 적었고, claim 72개 중 6개의 인용문이 원본에 없는 문자열이 됐다. 그때
    # 돌린 확인은 "인용문 블록이 있는가"였어서 전부 통과했다.
    for ref, refs, quote in quoted:
        bodies = [source_bodies[r] for r in refs if r in source_bodies]
        if not bodies:
            continue  # source가 vault에 없으면 판정 불가 (dangling_ref가 보고한다)
        hay = " ".join(bodies)
        missing = [seg for seg in (_norm_ws(x) for x in quote.split(_ELISION))
                   if seg and seg not in hay]
        if missing:
            findings.append(_f("quote_not_in_source", "warning", ref,
                               f"quote is not verbatim in {', '.join(refs)}; "
                               f"first unmatched: {missing[0][:60]!r}"))

    all_refs: list[tuple[str, str]] = []  # (참조하는 문서 ref, 참조되는 id)
    for p in vault.rglob("*.md"):
        rel = str(p.relative_to(vault))
        if rel.startswith((".obsidian", "06_Metadata")):
            continue
        meta = _parse(p)
        if meta is None:
            findings.append(_f("unparseable", "error", rel,
                               "YAML frontmatter cannot be parsed (or fence is broken)"))
            continue
        mid = meta.get("id")
        if mid:
            # session/decision id는 프로젝트별 스코프라 프로젝트가 다르면 중복이 아니다
            scope = rel.split("/")[1] if rel.startswith("01_Projects/") else ""
            id_files.setdefault(f"{mid}|{scope}", []).append(rel)
        # Web Clipper 유입물은 자체 frontmatter(title 등)는 있어도 wiki 스키마(id)가 없다
        if rel.startswith("00_Inbox") and not mid:
            clip_url = str((meta or {}).get("url") or (meta or {}).get("source") or "")
            if clip_url and clip_url in inbox_source_urls:
                findings.append(_f("inbox_ingested_leftover", "info", rel,
                                   "clip already ingested (url matches a source); "
                                   "delete the original (git rm)"))
            else:
                findings.append(_f("inbox_unstructured", "info", rel,
                                   "raw clip without source schema (no id); needs ingest"))
        if not meta:
            continue
        for field in ("source_refs", "evidence_refs", "claim_refs"):
            for ref in meta.get(field) or []:
                all_refs.append((str(mid or rel), str(ref)))
        ra = meta.get("review_after")
        if ra and str(ra) <= today_str:
            findings.append(_f("stale", "warning", meta.get("id", rel),
                               f"review_after {ra} has passed"))

    for key, files in id_files.items():
        if len(files) > 1:
            findings.append(_f("duplicate_id", "error", key.split("|")[0],
                               "same id in multiple files: " + ", ".join(sorted(files))))

    known_ids = {key.split("|")[0] for key in id_files}
    for holder, ref in all_refs:
        # id 모양의 참조만 판정한다 (URL이나 자유 텍스트 출처는 판단 불가)
        if _ID_SHAPED.match(ref) and ref not in known_ids:
            findings.append(_f("dangling_ref", "warning", holder,
                               f"references {ref}, which does not exist in the vault"))

    for indexname, root in _INDEX_ROOTS.items():
        idx = vault / "06_Metadata/indexes" / f"{indexname}.md"
        if not idx.exists():
            continue
        stems = {q.stem for q in (vault / root).rglob("*.md")}
        for ln in idx.read_text(encoding="utf-8").splitlines():
            m = re.match(r"- \[([^\]]+)\]", ln)
            if m and m.group(1) not in stems:
                findings.append(_f("index_dangling", "warning", m.group(1),
                                   f"{indexname} entry has no file under {root}"))

    findings.sort(key=lambda f: (_SEV_ORDER.get(f["severity"], 9), f["check"]))
    return findings
