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


def test_tokenize_korean_unigrams_and_bigrams():
    # 한 글자 질의("밥")도 문서와 매치되려면 unigram이 함께 있어야 한다
    assert search.tokenize("한국어 검색") == ["한", "국", "어", "한국", "국어", "검", "색", "검색"]
    assert search.tokenize("밥") == ["밥"]
    assert search.tokenize("BM25 한글") == ["bm25", "한", "글", "한글"]


def test_single_char_korean_query_matches(vault):
    claims.create_claim(vault, claim="밥솥으로 밥을 짓는다", claim_type="observation",
                        source_refs=["s"], date_str="2026-01-01", seq=1)
    idx = search.build_index(vault, embed_fn=_zero_embed)
    results = idx.query("밥", k=1)
    assert results and "밥솥" in results[0]["title"]


def _zero_embed(texts):
    return [[0.0] for _ in texts]


def test_korean_query_matches_lexically(vault):
    claims.create_claim(vault, claim="파이썬 GIL은 병렬성을 제한한다",
                        claim_type="technical_fact", source_refs=["s"],
                        date_str="2026-01-01", seq=1)
    claims.create_claim(vault, claim="git commit message style",
                        claim_type="technical_fact", source_refs=["s"],
                        date_str="2026-01-02", seq=1)
    # rank_bm25는 문서 2개 코퍼스에서 df=1 토큰의 idf가 정확히 0이라 (ln(1.5/1.5))
    # 세 번째 문서가 있어야 BM25 신호가 생긴다
    claims.create_claim(vault, claim="react state management notes",
                        claim_type="technical_fact", source_refs=["s"],
                        date_str="2026-01-03", seq=1)
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


def test_rrf_ties_do_not_leak_file_order(vault):
    # BM25 유일 매치 문서는 임베딩이 죽어 있어도(전부 0) 파일 순서와 무관하게 1위여야 한다
    for seq, text in enumerate(
            ["alpha topic", "beta topic", "gamma topic", "react hook effect"], start=1):
        claims.create_claim(vault, claim=text, claim_type="technical_fact",
                            source_refs=["s"], date_str="2026-01-01", seq=seq)
    idx = search.build_index(vault, embed_fn=_zero_embed)
    results = idx.query("react hook", k=4)
    assert "react" in results[0]["title"]


def test_semantic_only_query_uses_cosine_order(vault):
    # 질의 토큰이 어떤 문서에도 없으면(BM25 전부 0) 코사인 순위가 그대로 순위가 돼야 한다
    claims.create_claim(vault, claim="ordinary note one", claim_type="observation",
                        source_refs=["s"], date_str="2026-01-01", seq=1)
    claims.create_claim(vault, claim="special concept target", claim_type="observation",
                        source_refs=["s"], date_str="2026-01-01", seq=2)

    def sem_embed(texts):
        return [[1.0, 0.0] if ("special" in t or "질의어" in t) else [0.0, 1.0]
                for t in texts]

    idx = search.build_index(vault, embed_fn=sem_embed)
    results = idx.query("무관한 질의어", k=2)
    assert "special" in results[0]["title"]


def test_fingerprint_survives_broken_symlink(vault):
    (vault / "03_Resources/Concepts/dangling.md").symlink_to(vault / "no-such-target.md")
    search.vault_fingerprint(vault)  # 예외 없이 통과해야 한다
    idx = search.build_index(vault, embed_fn=_zero_embed)
    assert idx.query("anything", k=1) == []


def test_vec_cache_ignores_poisoned_file(tmp_path):
    p = tmp_path / "vecs.json"
    p.write_text('[1, 2, 3]', encoding="utf-8")  # dict가 아닌 valid JSON
    cache = search.VecCache(p)
    assert cache.get("x") is None
    p.write_text('{"k": "not-a-vector", "ok": [1.0, 2.0]}', encoding="utf-8")
    cache = search.VecCache(p)
    assert cache.get("x") is None  # 오염 항목은 로드에서 걸러진다


def test_vec_cache_dim_mismatch_self_heals(vault, tmp_path):
    claims.create_claim(vault, claim="react hook effect timing",
                        claim_type="technical_fact", source_refs=["s"],
                        date_str="2026-01-01", seq=1)
    cache_path = tmp_path / "vecs.json"

    def one_dim_embed(texts):
        return [[1.0] for _ in texts]

    search.build_index(vault, embed_fn=one_dim_embed, vec_cache=search.VecCache(cache_path))
    claims.create_claim(vault, claim="git commit style", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-02", seq=1)
    # 캐시에는 1차원 벡터, 새 문서는 9차원: 크래시 대신 전체 재임베딩으로 복구해야 한다
    idx = search.build_index(vault, embed_fn=fake_embed, vec_cache=search.VecCache(cache_path))
    assert idx.query("react hook", k=1)


def test_all_symbol_docs_do_not_crash_bm25(vault):
    (vault / "03_Resources/Concepts/symbols.md").write_text(
        "---\nname: symbols\n---\n\n☆☆☆ ★★★\n", encoding="utf-8")
    idx = search.build_index(vault, embed_fn=_zero_embed)
    assert idx.query("아무거나", k=1) == [] or idx.query("아무거나", k=1)


def test_empty_vault_does_not_load_embedder(vault, monkeypatch):
    def boom():
        raise AssertionError("embedder must not be loaded for an empty vault")

    monkeypatch.setattr(search, "_default_embedder", boom)
    idx = search.build_index(vault)  # 문서 0개: 2.2GB 모델을 로드하면 안 된다
    assert idx.query("anything", k=3) == []
    cache = search.IndexCache(vault)
    assert cache.get().query("anything", k=3) == []


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
