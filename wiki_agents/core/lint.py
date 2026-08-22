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


def _parse(p: Path) -> dict | None:
    try:
        meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        return meta
    except Exception:
        return None


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

    for p in vault.rglob("*.md"):
        rel = str(p.relative_to(vault))
        if rel.startswith((".obsidian", "06_Metadata")):
            continue
        meta = _parse(p)
        if meta is None:
            findings.append(_f("unparseable", "error", rel,
                               "YAML frontmatter cannot be parsed"))
            continue
        mid = meta.get("id")
        if mid:
            id_files.setdefault(str(mid), []).append(rel)
        if not meta:
            if rel.startswith("00_Inbox"):
                findings.append(_f("inbox_unstructured", "info", rel,
                                   "raw clip without source frontmatter; needs ingest"))
            continue
        ra = meta.get("review_after")
        if ra and str(ra) <= today_str:
            findings.append(_f("stale", "warning", meta.get("id", rel),
                               f"review_after {ra} has passed"))

    for mid, files in id_files.items():
        if len(files) > 1:
            findings.append(_f("duplicate_id", "error", mid,
                               "same id in multiple files: " + ", ".join(sorted(files))))

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
