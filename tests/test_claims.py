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


def test_set_claim_status_rejects_verified(vault):
    _make(vault)
    with pytest.raises(ValueError):
        claims.set_claim_status(
            vault, "claim-20260607-001", status="verified", date_str="2026-06-07",
        )


def test_create_claim_refuses_overwrite(vault):
    _make(vault, seq=1)
    with pytest.raises(FileExistsError):
        _make(vault, seq=1, text="다른 내용의 claim")


def test_korean_claims_are_not_all_duplicates(vault):
    _make(vault, seq=1, text="파이썬 GIL은 스레드 병렬성을 제한한다")
    _make(vault, seq=2, text="한국어 형태소 분석은 공백 분리로 충분하지 않다")
    hits = claims.find_similar_claim(vault, "완전히 무관한 세 번째 주장이다")
    assert hits == []


def test_korean_duplicate_still_detected(vault):
    _make(vault, seq=1, text="파이썬 GIL은 스레드 병렬성을 제한한다")
    hits = claims.find_similar_claim(vault, "파이썬 GIL은 스레드 병렬성을 제한한다")
    assert hits == ["claim-20260607-001"]


def test_index_lines_contain_no_em_dash(vault):
    _make(vault, seq=1)
    text = (vault / "06_Metadata/indexes/claim-index.md").read_text(encoding="utf-8")
    assert "—" not in text
