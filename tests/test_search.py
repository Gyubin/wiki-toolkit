from wiki_agent.core import claims, search

_VOCAB = ["python", "typed", "react", "hook", "effect", "git", "commit", "search", "vector"]


def fake_embed(texts):
    return [[1.0 if w in set(search.tokenize(t)) else 0.0 for w in _VOCAB] for t in texts]


def test_tokenize():
    assert search.tokenize("React useEffect!!") == ["react", "useeffect"]


def test_iter_docs_scopes(vault):
    claims.create_claim(vault, claim="react hook effect timing", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-01", seq=1)
    (vault / "06_Metadata/notes.md").write_text("should be excluded", encoding="utf-8")
    paths = {d["path"] for d in search.iter_docs(vault)}
    assert any("10_Claims" in p for p in paths)
    assert not any("06_Metadata" in p for p in paths)


def test_query_ranks_relevant_top(vault):
    claims.create_claim(vault, claim="react hook effect timing", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-01", seq=1)
    claims.create_claim(vault, claim="git commit message style", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-02", seq=1)
    idx = search.build_index(vault, embed_fn=fake_embed)
    results = idx.query("react hook", k=2)
    assert results
    assert "react" in results[0]["title"].lower()
    assert {"ref", "title", "score", "snippet"} <= set(results[0])


def test_empty_query_returns_empty(vault):
    idx = search.build_index(vault, embed_fn=fake_embed)
    assert idx.query("", k=5) == []
