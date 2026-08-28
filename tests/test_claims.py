import pytest

from wiki_toolkit import schema
from wiki_toolkit.core import claims


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


def test_promote_to_verified_requires_evidence(vault):
    _make(vault)
    with pytest.raises(PermissionError):
        claims.promote_claim(
            vault, "claim-20260607-001", target_status="verified",
            date_str="2026-06-07",
        )


def test_promote_moves_the_file_between_status_folders(vault):
    _make(vault)
    path = claims.promote_claim(
        vault, "claim-20260607-001", target_status="verified",
        evidence_refs=["2026-06-07 본인 확인: 원문과 대조"], date_str="2026-06-07",
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


def test_list_pending_survives_malformed_file(vault):
    _make(vault, seq=1)
    (vault / "10_Claims/pending/claim-20260607-999.md").write_text(
        "---\nbroken, no closing fence", encoding="utf-8")
    rows = claims.list_pending(vault)  # 파일 하나 때문에 전체가 죽으면 안 된다
    assert any(r["id"] == "claim-20260607-001" for r in rows)


def test_find_similar_survives_malformed_file(vault):
    (vault / "10_Claims/pending/claim-20260607-999.md").write_text(
        "---\nbroken, no closing fence", encoding="utf-8")
    assert claims.find_similar_claim(vault, "anything at all") == []


def test_index_lines_contain_no_em_dash(vault):
    _make(vault, seq=1)
    text = (vault / "06_Metadata/indexes/claim-index.md").read_text(encoding="utf-8")
    assert "—" not in text


def test_create_claim_with_quote_embeds_the_source_passage(vault):
    """claim만 열어도 왜 그 주장이 나왔는지 보여야 한다.

    claim 텍스트는 정리된 한국어이고 원문은 대개 영어라, 원문을 같이 두지 않으면
    Verify할 때 원문을 다시 열어야 한다. 안 열면 미묘하게 비튼 claim이 그대로 통과한다.
    """
    path = claims.create_claim(
        vault, claim="샌드박스 안에는 수명이 긴 자격증명을 두지 않는다.",
        claim_type="decision", source_refs=["source-20260607-001"],
        date_str="2026-06-07", seq=1,
        quote="Credentials cannot live where the agent lives.",
    )
    body = path.read_text(encoding="utf-8")
    assert "## 원문" in body
    assert "> Credentials cannot live where the agent lives." in body


def test_quote_blockquote_survives_blank_lines(vault):
    """빈 줄에 '>'를 안 붙이면 markdown blockquote가 거기서 끊긴다."""
    path = claims.create_claim(
        vault, claim="두 겹으로 호출자를 확인한다.", claim_type="technical_fact",
        source_refs=["source-20260607-001"], date_str="2026-06-07", seq=2,
        quote="First an IP allowlist.\n\nThen a short-lived JWT.",
    )
    _, body = schema.parse_doc(path.read_text(encoding="utf-8"))
    quoted = body.split("## 원문", 1)[1].strip().splitlines()
    assert quoted, "인용 절이 비었다"
    assert all(ln.startswith(">") for ln in quoted), quoted


def test_create_claim_without_quote_is_byte_identical_to_before(vault):
    """quote를 안 주면 예전 본문 그대로여야 한다 (기존 claim 18개 회귀 방지)."""
    path = claims.create_claim(
        vault, claim="원문 없는 주장", claim_type="opinion",
        source_refs=["s"], date_str="2026-06-07", seq=3,
    )
    _, body = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert body == "## Claim\n\n원문 없는 주장\n"


def test_quote_survives_a_status_change(vault):
    path = claims.create_claim(
        vault, claim="상태가 바뀌어도 원문은 남는다", claim_type="observation",
        source_refs=["s"], date_str="2026-06-07", seq=4,
        quote="the original wording",
    )
    cid = path.stem
    moved = claims.promote_claim(vault, cid, target_status="attributed",
                                 date_str="2026-06-08")
    assert "> the original wording" in moved.read_text(encoding="utf-8")


def test_update_claim_quote_replaces_only_the_quote(vault):
    """claim 문장과 status는 그대로 두고 ## 원문만 바꾼다."""
    claims.create_claim(vault, claim="주장 문장", claim_type="technical_fact",
                        source_refs=["source-20260827-001"], date_str="2026-08-27", seq=1,
                        quote="원문 뻔했음")
    p = claims.update_claim_quote(
        vault, "claim-20260827-001", quote="원문 뻔함",
        reason="원본 대조 결과 단어를 바꿔 적었다", date_str="2026-08-28")
    meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
    assert meta["claim"] == "주장 문장"
    assert meta["status"] == "unverified"
    assert meta["updated"] == "2026-08-28"
    assert "> 원문 뻔함" in body
    assert "뻔했음" not in body
    assert "## Claim\n\n주장 문장" in body


def test_update_claim_quote_adds_one_when_absent(vault):
    claims.create_claim(vault, claim="인용 없던 주장", claim_type="opinion",
                        source_refs=["s"], date_str="2026-08-27", seq=1)
    p = claims.update_claim_quote(vault, "claim-20260827-001", quote="뒤늦게 붙인 원문",
                                  reason="원문을 찾았다", date_str="2026-08-27")
    body = p.read_text(encoding="utf-8")
    assert "## 원문" in body
    assert "> 뒤늦게 붙인 원문" in body


def test_update_claim_quote_keeps_a_promoted_claim_where_it_is(vault):
    """인용문 수정이 status를 되돌리거나 파일을 옮기면 안 된다."""
    claims.create_claim(vault, claim="승격된 주장", claim_type="person_claim",
                        source_refs=["s"], date_str="2026-08-27", seq=1, quote="old")
    claims.promote_claim(vault, "claim-20260827-001", target_status="attributed",
                         date_str="2026-08-27")
    p = claims.update_claim_quote(vault, "claim-20260827-001", quote="new",
                                  reason="원본 대조", date_str="2026-08-27")
    assert p.parent.name == "attributed"
    meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
    assert meta["status"] == "attributed"


def test_update_claim_quote_requires_reason_and_content(vault):
    claims.create_claim(vault, claim="주장", claim_type="opinion", source_refs=["s"],
                        date_str="2026-08-27", seq=1, quote="q")
    with pytest.raises(ValueError, match="reason"):
        claims.update_claim_quote(vault, "claim-20260827-001", quote="새 인용",
                                  reason="", date_str="2026-08-27")
    with pytest.raises(ValueError, match="quote"):
        claims.update_claim_quote(vault, "claim-20260827-001", quote="  ",
                                  reason="이유는 있다", date_str="2026-08-27")


def test_unblockquote_is_the_inverse_of_blockquote():
    text = "첫 줄\n\n셋째 줄"
    assert claims.unblockquote(claims.blockquote(text)) == text
