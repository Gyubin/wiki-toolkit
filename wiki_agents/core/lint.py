"""Deterministic, report-only vault hygiene checks (no LLM)."""
from __future__ import annotations

import re
from pathlib import Path

from .. import schema
from .claims import _STATUS_DIR, normalize_key

_SEV_ORDER = {"error": 0, "warning": 1, "info": 2}

# index 파일 -> 항목 파일이 있어야 하는 루트
_INDEX_ROOTS = {
    "claim-index": "10_Claims",
    "learning-index": "30_Learning",
    "wiki-index": "03_Resources",
}


def _f(check: str, severity: str, ref: str, message: str) -> dict:
    return {"check": check, "severity": severity, "ref": ref, "message": message}


_ID_SHAPED = re.compile(r"^(?:source|claim|session|decision|learning)-\d{8}-\d+$")

# 실패한 캡처는 대개 짧다. 봇월 문구가 있으면 create_source가 아예 막지만, 문구 없이
# 껍데기만 내려오는 경우가 있어서 여기서 보고한다. 짧은 붙여넣기 메모도 걸리므로
# 하드 블록이 아니라 warning이다.
_MIN_SOURCE_CHARS = 200


def _parse(p: Path) -> dict | None:
    """meta dict, 또는 파싱 불가/펜스 손상이면 None.

    parse_doc은 닫는 펜스가 없는 파일을 조용히 ({}, 원문)으로 돌려주므로,
    '---'로 시작하는데 meta가 비면 손상으로 취급해야 한다. 안 그러면 lint는
    침묵하는데 list_pending 같은 소비자는 그 파일에서 죽는 모순이 생긴다.
    """
    try:
        text = p.read_text(encoding="utf-8")
        meta, _ = schema.parse_doc(text)
    except Exception:
        return None
    if not meta and text.startswith("---"):
        return None
    return meta


def run_checks(vault: Path, today_str: str) -> list[dict]:
    vault = Path(vault)
    findings: list[dict] = []
    claim_metas: list[dict] = []
    id_files: dict[str, list[str]] = {}

    for p in (vault / "10_Claims").rglob("claim-*.md"):
        meta = _parse(p)
        if meta is None:
            continue  # 아래 전체 순회에서 unparseable로 보고된다
        claim_metas.append(meta)
        d = p.parent.name
        status = meta.get("status")
        ref = meta.get("id", str(p))
        if status in _STATUS_DIR and _STATUS_DIR[status] != d:
            findings.append(_f("status_folder_mismatch", "error", ref,
                               f"status '{status}' belongs in '{_STATUS_DIR[status]}', "
                               f"found in '{d}'"))
        if not meta.get("source_refs"):
            findings.append(_f("missing_source_refs", "warning", ref, "claim has no source_refs"))
        if status == "verified" and not meta.get("evidence_refs"):
            findings.append(_f("verified_without_evidence", "warning", ref,
                               "verified claim has no evidence_refs (confirm human-approved)"))

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

    for p in (vault / "00_Inbox").rglob("*.md"):
        try:
            meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
        except OSError:
            continue  # 아래 전체 순회에서 unparseable로 보고된다
        if meta.get("type") != "source":
            continue
        size = len(body.strip())
        if size < _MIN_SOURCE_CHARS:
            findings.append(_f("thin_source", "warning",
                               meta.get("id", str(p.relative_to(vault))),
                               f"source body is only {size} chars (under {_MIN_SOURCE_CHARS}); "
                               "a failed capture looks like this"))

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
