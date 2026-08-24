"""파이프라인 "다음에 할 일" 계산 (사람이 단계를 외우지 않아도 되게 하는 장치)."""
from wiki_agents.core import claims, learning, pipeline, wiki

TODAY = "2026-08-25"


def _claim(vault, text, seq):
    return claims.create_claim(vault, claim=text, claim_type="technical_fact",
                               source_refs=["source-20260825-001"],
                               date_str="2026-08-25", seq=seq)


def test_empty_vault_has_no_next_step(vault):
    assert pipeline.next_step(vault, TODAY) is None


def test_unstructured_inbox_comes_first(vault):
    """ingest 안 된 클립이 있으면 그게 최우선. pending이 있어도 뒤 단계는 말하지 않는다."""
    (vault / "00_Inbox/browser-clips/clip.md").write_text(
        "---\ntitle: 클립\ntags: [clippings]\n---\n\n본문\n", encoding="utf-8")
    _claim(vault, "파이썬 GIL은 병렬성을 제한한다", 1)
    step = pipeline.next_step(vault, TODAY)
    assert "ingest" in step and "1개" in step


def test_pending_claims_are_announced(vault):
    for i in range(3):
        _claim(vault, f"주장 {i}", i + 1)
    step = pipeline.next_step(vault, TODAY)
    assert "pending claim 3개" in step


def test_verified_claim_without_wiki_page_is_announced(vault):
    p = _claim(vault, "fastembed는 multilingual e5 중 large만 지원한다", 1)
    cid = p.stem
    claims.promote_claim(vault, cid, target_status="verified",
                         evidence_refs=["core/search.py:20"], date_str=TODAY)
    step = pipeline.next_step(vault, TODAY)
    assert "wiki page" in step and "1개" in step
    assert pipeline.vault_state(vault, TODAY)["verified_unlinked"] == [cid]


def test_wiki_page_clears_the_verified_claim(vault):
    p = _claim(vault, "fastembed는 large만 지원한다", 1)
    cid = p.stem
    claims.promote_claim(vault, cid, target_status="verified",
                         evidence_refs=["core/search.py:20"], date_str=TODAY)
    wiki.create_wiki_page(vault, name="임베딩 모델", page_type="concept",
                          body="본문", claim_refs=[cid], date_str=TODAY)
    assert pipeline.vault_state(vault, TODAY)["verified_unlinked"] == []
    assert pipeline.next_step(vault, TODAY) is None


def test_due_reviews_are_last(vault):
    """앞 단계가 다 비어야 복습 안내가 나온다."""
    learning.create_learning_item(vault, topic="e5 임베딩", skill_area="검색",
                                  date_str=TODAY, seq=1)
    step = pipeline.next_step(vault, TODAY)
    assert step is not None and "복습" in step
    # pending이 생기면 복습보다 앞선다
    _claim(vault, "새 주장", 1)
    assert "pending claim" in pipeline.next_step(vault, TODAY)


def test_state_counts_are_ids_not_files(vault):
    _claim(vault, "주장 하나", 1)
    s = pipeline.vault_state(vault, TODAY)
    assert s["pending_claims"] == ["claim-20260825-001"]
    assert s["verified_claims"] == [] and s["wiki_pages"] == []
