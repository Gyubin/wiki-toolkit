"""Claim lifecycle: create (unverified), dedup, promote (gated), status changes."""
from __future__ import annotations

import re
from pathlib import Path

from .. import schema
from . import index

_STATUS_DIR = {
    "unverified": "pending", "verified": "verified", "attributed": "attributed",
    "disputed": "disputed", "rejected": "rejected", "outdated": "outdated",
    "deprecated": "outdated", "partially_true": "pending",
    "accepted_for_now": "pending", "opinion": "attributed",
}


def _find_file(vault: Path, claim_id: str) -> Path:
    for sub in set(_STATUS_DIR.values()):
        p = Path(vault) / "10_Claims" / sub / f"{claim_id}.md"
        if p.exists():
            return p
    raise FileNotFoundError(claim_id)


def normalize_key(text: str, speaker: str | None = None) -> str:
    toks = re.findall(r"[a-z0-9]+|[가-힣]+", text.lower())
    key = " ".join(sorted(toks[:8])) if toks else text.strip().lower()
    return key + (f"|{speaker.lower()}" if speaker else "")


def create_claim(
    vault: Path, *, claim: str, claim_type: str, source_refs: list[str],
    date_str: str, seq: int, proposed_status: str | None = None,
    speaker: str | None = None, sensitivity: str = "personal",
) -> Path:
    schema.validate_claim_type(claim_type)
    cid = schema.make_id("claim", date_str, seq)
    meta = {
        "type": "claim", "id": cid, "claim_type": claim_type,
        "status": "unverified", "proposed_status": proposed_status or "",
        "claim": claim, "speaker": speaker or "", "source_refs": source_refs,
        "evidence_refs": [], "sensitivity": sensitivity,
        "created": date_str, "updated": date_str,
    }
    path = Path(vault) / "10_Claims/pending" / f"{cid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raise FileExistsError(f"{cid} already exists; pick a fresh seq")
    path.write_text(schema.render_doc(meta, f"## Claim\n\n{claim}\n"), encoding="utf-8")
    index.update_index(vault, "claim-index", cid, f"{claim[:60]} - unverified")
    return path


def find_similar_claim(vault: Path, claim_text: str, speaker: str | None = None) -> list[str]:
    key = normalize_key(claim_text, speaker)
    hits = []
    for p in (Path(vault) / "10_Claims").rglob("claim-*.md"):
        meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        if not meta.get("id") or not meta.get("claim"):
            continue  # 손상 파일 하나가 전체 조회를 죽이면 안 된다 (lint가 보고한다)
        if normalize_key(meta["claim"], meta.get("speaker") or None) == key:
            hits.append(meta["id"])
    return hits


def promote_claim(
    vault: Path, claim_id: str, *, target_status: str,
    evidence_refs: list[str] | None = None, date_str: str,
) -> Path:
    """verified는 evidence_refs가 유일한 통로다 (원칙 9).

    예전에는 `approved_by_human=True`로도 통과할 수 있었고, 그 플래그를 넘기는 곳은
    웹 앱의 `/claims/{id}/approve` 하나였다. 웹 앱을 지우면서 같이 뺐다. 그 플래그는
    파일에 아무것도 안 남겼기 때문에(프론트매터 키 13개 어디에도 안 들어갔다) 결과물은
    `evidence_refs: []`인 verified였고, lint가 `verified_without_evidence`로 잡았다.
    즉 "사람이 승인했다"는 기록이 아니라 게이트를 끄는 스위치였다.

    사람 판단으로 승격하고 싶으면 그 판단 자체를 evidence_refs에 적는다.
    예: evidence_refs=["2026-08-25 본인 확인: 원문 3문단과 대조"]
    """
    schema.validate_status(target_status)
    if target_status == "verified" and not evidence_refs:
        raise PermissionError(
            "verified requires evidence_refs (design principle 9)"
        )
    src = _find_file(vault, claim_id)
    meta, body = schema.parse_doc(src.read_text(encoding="utf-8"))
    meta["status"] = target_status
    meta["updated"] = date_str
    if evidence_refs:
        meta["evidence_refs"] = evidence_refs
    if target_status == "verified":
        meta["last_verified"] = date_str
    dst_dir = Path(vault) / "10_Claims" / _STATUS_DIR[target_status]
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{claim_id}.md"
    dst.write_text(schema.render_doc(meta, body), encoding="utf-8")
    if dst != src:
        src.unlink()
    index.update_index(vault, "claim-index", claim_id, f"{meta['claim'][:60]} - {target_status}")
    return dst


def set_claim_status(
    vault: Path, claim_id: str, *, status: str, superseded_by: str | None = None,
    date_str: str,
) -> Path:
    if status == "verified":
        raise ValueError("verified must go through promote_claim (evidence_refs)")
    # 여기 오는 status는 verified가 아니므로 promote_claim의 게이트에 안 걸린다.
    path = promote_claim(vault, claim_id, target_status=status, date_str=date_str)
    if superseded_by:
        meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
        meta["superseded_by"] = [superseded_by]
        path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    return path


def list_pending(vault: Path) -> list[dict]:
    rows = []
    for p in (Path(vault) / "10_Claims/pending").glob("claim-*.md"):
        meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        if not meta.get("id"):
            continue  # 손상 파일 하나가 목록 전체를 죽이면 안 된다 (lint가 보고한다)
        rows.append({"id": meta["id"], "claim": meta.get("claim", ""),
                     "claim_type": meta.get("claim_type", ""),
                     "proposed_status": meta.get("proposed_status", "")})
    return sorted(rows, key=lambda r: r["id"])
