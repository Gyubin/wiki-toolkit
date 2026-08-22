from wiki_agents.core import claims, search

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


def test_tokenize_korean_bigrams():
    assert search.tokenize("한국어 검색") == ["한국", "국어", "검색"]
    assert search.tokenize("밥") == ["밥"]
    assert search.tokenize("BM25 한글토큰") == ["bm25", "한글", "글토", "토큰"]


def _zero_embed(texts):
    return [[0.0] for _ in texts]


def test_korean_query_matches_lexically(vault):
    claims.create_claim(vault, claim="파이썬 GIL은 병렬성을 제한한다",
                        claim_type="technical_fact", source_refs=["s"],
                        date_str="2026-01-01", seq=1)
    claims.create_claim(vault, claim="git commit message style",
                        claim_type="technical_fact", source_refs=["s"],
                        date_str="2026-01-02", seq=1)
    # 임베딩이 전혀 도움이 안 되는 상태에서도 BM25가 한글 질의를 맞춰야 한다
    idx = search.build_index(vault, embed_fn=_zero_embed)
    results = idx.query("파이썬 병렬성", k=1)
    assert results and "파이썬" in results[0]["title"]


def test_e5_prefixes_are_applied(vault):
    claims.create_claim(vault, claim="react hook effect timing",
                        claim_type="technical_fact", source_refs=["s"],
                        date_str="2026-01-01", seq=1)
    seen: list[str] = []

    def recording_embed(texts):
        seen.extend(texts)
        return fake_embed(texts)

    idx = search.build_index(vault, embed_fn=recording_embed)
    idx.query("react hook", k=1)
    assert all(t.startswith("passage: ") or t.startswith("query: ") for t in seen)
    assert any(t.startswith("query: ") for t in seen)


def test_root_level_docs_are_indexed(vault):
    (vault / "design-doc.md").write_text("# 설계\n\nvector search design\n",
                                         encoding="utf-8")
    paths = {d["path"] for d in search.iter_docs(vault)}
    assert "design-doc.md" in paths
    assert not any("06_Metadata" in p for p in paths)


def test_index_cache_rebuilds_when_vault_changes(vault):
    cache = search.IndexCache(vault, embed_fn=fake_embed)
    assert cache.get().query("react hook", k=1) == []
    claims.create_claim(vault, claim="react hook effect timing",
                        claim_type="technical_fact", source_refs=["s"],
                        date_str="2026-01-01", seq=1)
    results = cache.get().query("react hook", k=1)
    assert results and "react" in results[0]["title"]


def test_vec_cache_avoids_reembedding(vault, tmp_path):
    claims.create_claim(vault, claim="react hook effect timing",
                        claim_type="technical_fact", source_refs=["s"],
                        date_str="2026-01-01", seq=1)
    calls: list[int] = []

    def counting_embed(texts):
        calls.append(len(list(texts)))
        return fake_embed(texts)

    cache_path = tmp_path / "cache" / "vecs.json"
    search.build_index(vault, embed_fn=counting_embed,
                       vec_cache=search.VecCache(cache_path))
    first = sum(calls)
    assert first >= 1
    calls.clear()
    search.build_index(vault, embed_fn=counting_embed,
                       vec_cache=search.VecCache(cache_path))
    assert sum(calls) == 0  # 문서가 그대로면 디스크 캐시로 임베딩 호출 0회
