import pytest

from wiki_agents import schema
from wiki_agents.core import claims


def _make(vault, seq=1, text="React useEffect runs after paint"):
    return claims.create_claim(
        vault, claim=text, claim_type="technical_fact",
        source_refs=["source-20260607-001"], date_str="2026-06-07", seq=seq,
    )


def test_create_claim_is_unverified(vault):
    path = _make(vault)
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["status"] == "unverified"
    assert meta["id"] == "claim-20260607-001"
    assert (vault / "10_Claims/pending/claim-20260607-001.md").exists()


def test_create_claim_validates_type(vault):
    with pytest.raises(ValueError):
        claims.create_claim(
            vault, claim="x", claim_type="bogus", source_refs=[],
            date_str="2026-06-07", seq=9,
        )


def test_promote_to_verified_requires_approval_or_evidence(vault):
    _make(vault)
    with pytest.raises(PermissionError):
        claims.promote_claim(
            vault, "claim-20260607-001", target_status="verified",
            date_str="2026-06-07",
        )


def test_promote_with_human_approval(vault):
    _make(vault)
    path = claims.promote_claim(
        vault, "claim-20260607-001", target_status="verified",
        approved_by_human=True, date_str="2026-06-07",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["status"] == "verified"
    assert (vault / "10_Claims/verified/claim-20260607-001.md").exists()
    assert not (vault / "10_Claims/pending/claim-20260607-001.md").exists()


def test_promote_with_evidence(vault):
    _make(vault)
    path = claims.promote_claim(
        vault, "claim-20260607-001", target_status="verified",
        evidence_refs=["repo:src/x.ts:12"], date_str="2026-06-07",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["evidence_refs"] == ["repo:src/x.ts:12"]


def test_find_similar_claim(vault):
    _make(vault, seq=1, text="React useEffect runs after paint")
    _make(vault, seq=2, text="react USEEFFECT runs after paint!!")
    hits = claims.find_similar_claim(vault, "React useEffect runs after paint")
    assert "claim-20260607-001" in hits


def test_list_pending(vault):
    _make(vault, seq=1)
    rows = claims.list_pending(vault)
    assert any(r["id"] == "claim-20260607-001" for r in rows)
