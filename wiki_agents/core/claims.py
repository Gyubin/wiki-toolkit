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
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(sorted(toks[:8])) + (f"|{speaker.lower()}" if speaker else "")


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
    path.write_text(schema.render_doc(meta, f"## Claim\n\n{claim}\n"), encoding="utf-8")
    index.update_index(vault, "claim-index", cid, f"{claim[:60]} — unverified")
    return path


def find_similar_claim(vault: Path, claim_text: str, speaker: str | None = None) -> list[str]:
    key = normalize_key(claim_text, speaker)
    hits = []
    for p in (Path(vault) / "10_Claims").rglob("claim-*.md"):
        meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        if normalize_key(meta.get("claim", ""), meta.get("speaker") or None) == key:
            hits.append(meta["id"])
    return hits


def promote_claim(
    vault: Path, claim_id: str, *, target_status: str,
    evidence_refs: list[str] | None = None, approved_by_human: bool = False,
    date_str: str,
) -> Path:
    schema.validate_status(target_status)
    if target_status == "verified" and not approved_by_human and not evidence_refs:
        raise PermissionError(
            "verified requires human approval or evidence (design principle 9)"
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
    index.update_index(vault, "claim-index", claim_id, f"{meta['claim'][:60]} — {target_status}")
    return dst


def set_claim_status(
    vault: Path, claim_id: str, *, status: str, superseded_by: str | None = None,
    date_str: str,
) -> Path:
    path = promote_claim(
        vault, claim_id, target_status=status, approved_by_human=True, date_str=date_str
    )
    if superseded_by:
        meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
        meta["superseded_by"] = [superseded_by]
        path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    return path


def list_pending(vault: Path) -> list[dict]:
    rows = []
    for p in (Path(vault) / "10_Claims/pending").glob("claim-*.md"):
        meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        rows.append({"id": meta["id"], "claim": meta.get("claim", ""),
                     "claim_type": meta.get("claim_type", ""),
                     "proposed_status": meta.get("proposed_status", "")})
    return sorted(rows, key=lambda r: r["id"])
