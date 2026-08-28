import pytest

from wiki_toolkit import schema
from wiki_toolkit.core import wiki


def test_create_wiki_page(vault):
    path = wiki.create_wiki_page(
        vault, name="useEffect timing", page_type="concept",
        body="## Verified Knowledge\n\nRuns after paint.\n",
        claim_refs=["claim-20260607-001"], date_str="2026-06-07",
    )
    assert path.exists()
    assert path.parent.name == "Concepts"
    meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["type"] == "concept"
    assert meta["claim_refs"] == ["claim-20260607-001"]
    wi = (vault / "06_Metadata/indexes/wiki-index.md").read_text(encoding="utf-8")
    assert "useEffect timing" in wi


def test_create_wiki_page_rejects_unknown_type(vault):
    with pytest.raises(ValueError):
        wiki.create_wiki_page(
            vault, name="x", page_type="bogus", body="b",
            claim_refs=[], date_str="2026-06-07",
        )


def test_korean_page_names_get_distinct_slugs(vault):
    p1 = wiki.create_wiki_page(
        vault, name="스레드 병렬성", page_type="concept", body="b",
        claim_refs=[], date_str="2026-08-22",
    )
    p2 = wiki.create_wiki_page(
        vault, name="형태소 분석", page_type="concept", body="b",
        claim_refs=[], date_str="2026-08-22",
    )
    assert p1 != p2
    assert p1.stem != "page" and p2.stem != "page"


def test_create_wiki_page_refuses_silent_overwrite(vault):
    wiki.create_wiki_page(
        vault, name="useEffect timing", page_type="concept", body="원본",
        claim_refs=[], date_str="2026-08-22",
    )
    with pytest.raises(FileExistsError):
        wiki.create_wiki_page(
            vault, name="useEffect timing", page_type="concept", body="덮어쓰기",
            claim_refs=[], date_str="2026-08-22",
        )
    path = wiki.create_wiki_page(
        vault, name="useEffect timing", page_type="concept", body="명시적 갱신",
        claim_refs=[], date_str="2026-08-22", overwrite=True,
    )
    assert "명시적 갱신" in path.read_text(encoding="utf-8")


def test_update_wiki_page_adds_claim_refs(vault):
    path = wiki.create_wiki_page(
        vault, name="useEffect timing", page_type="concept",
        body="b", claim_refs=["claim-20260607-001"], date_str="2026-06-07",
    )
    wiki.update_wiki_page(path, add_claim_refs=["claim-20260607-002"])
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert "claim-20260607-002" in meta["claim_refs"]


def test_update_wiki_page_bumps_updated_and_keeps_the_body(vault):
    """refs만 갱신해도 본문이 살아야 하고, updated는 갱신돼야 한다.

    본문의 조용한 손실이 이 프로젝트의 공인된 핵심 실패 유형인데, 이 보존 계약은
    claim/source의 update에는 테스트가 있고 페이지에는 없었다.
    """
    p = wiki.create_wiki_page(vault, name="RRF 융합", page_type="concept",
                              body="본문은 그대로 남아야 한다\n", claim_refs=[],
                              date_str="2026-08-01")
    wiki.update_wiki_page(p, add_claim_refs=["claim-20260828-001"], status="reviewed",
                          date_str="2026-08-28")
    meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
    assert "본문은 그대로 남아야 한다" in body
    assert str(meta["updated"]) == "2026-08-28"
    assert str(meta["created"]) == "2026-08-01"
    assert meta["status"] == "reviewed"
