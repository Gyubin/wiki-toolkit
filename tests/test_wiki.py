import pytest
from wiki_agent.core import wiki
from wiki_agent import schema


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


def test_update_wiki_page_adds_claim_refs(vault):
    path = wiki.create_wiki_page(
        vault, name="useEffect timing", page_type="concept",
        body="b", claim_refs=["claim-20260607-001"], date_str="2026-06-07",
    )
    wiki.update_wiki_page(path, add_claim_refs=["claim-20260607-002"])
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert "claim-20260607-002" in meta["claim_refs"]
