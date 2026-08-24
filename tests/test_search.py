import json

import httpx
import pytest

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


# ---------------------------------------------------------------- OpenAI provider

def _mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler),
                        base_url="https://api.openai.com/v1", timeout=5.0)


def test_provider_defaults_to_openai(monkeypatch):
    monkeypatch.delenv("WIKI_EMBED_PROVIDER", raising=False)
    monkeypatch.delenv("WIKI_EMBED_MODEL", raising=False)
    assert search.embed_provider() == "openai"
    assert search.embed_model_name() == "text-embedding-3-large"
    assert search.embed_prefixes() == ("", "")
    assert search.remote_blocked_sensitivities() == ("confidential",)

    monkeypatch.setenv("WIKI_EMBED_PROVIDER", "local")
    assert search.embed_model_name() == "intfloat/multilingual-e5-large"
    assert search.embed_prefixes() == ("passage: ", "query: ")
    assert search.remote_blocked_sensitivities() == ()  # 로컬은 나갈 데가 없다

    monkeypatch.setenv("WIKI_EMBED_MODEL", "some/other-model")
    assert search.embed_model_name() == "some/other-model"


def test_openai_embedder_requires_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        search._openai_embedder()


def test_openai_embedder_batches_and_restores_order(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k-test")
    monkeypatch.delenv("WIKI_EMBED_PROVIDER", raising=False)
    monkeypatch.delenv("WIKI_EMBED_MODEL", raising=False)
    monkeypatch.delenv("WIKI_EMBED_DIM", raising=False)
    monkeypatch.setattr(search, "_OPENAI_BATCH", 2)
    seen: list[dict] = []

    def handler(request):
        assert request.headers["authorization"] == "Bearer k-test"
        assert request.url.path.endswith("/embeddings")
        body = json.loads(request.content)
        seen.append(body)
        rows = [{"index": i, "embedding": [float(len(t)), 1.0]}
                for i, t in enumerate(body["input"])]
        # API가 순서를 뒤섞어 줘도 index로 복원돼야 한다
        return httpx.Response(200, json={"data": list(reversed(rows))})

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    vecs = search._openai_embedder()(["a", "bb", "ccc"])
    assert [v[0] for v in vecs] == [1.0, 2.0, 3.0]
    assert [len(b["input"]) for b in seen] == [2, 1]  # 배치 크기 2로 쪼갠다
    assert seen[0]["model"] == "text-embedding-3-large"
    assert "dimensions" not in seen[0]


def test_openai_embedder_sends_dimensions_when_set(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setenv("WIKI_EMBED_DIM", "256")
    seen: list[dict] = []

    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    search._openai_embedder()(["x"])
    assert seen[0]["dimensions"] == 256


def test_openai_embedder_retries_then_succeeds(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(search.time, "sleep", lambda _s: None)
    calls: list[int] = []

    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": "rate limit"})
        if len(calls) == 2:
            raise httpx.ConnectError("boom")
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [0.5]}]})

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    assert search._openai_embedder()(["x"]) == [[0.5]]
    assert len(calls) == 3


def test_openai_embedder_raises_readable_error_after_retries(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(search.time, "sleep", lambda _s: None)

    def handler(request):
        return httpx.Response(500, json={"error": "server"})

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    # httpx 예외가 그대로 새어나오면 CLI가 트레이스백을 뱉는다 (httpx.HTTPError는 OSError가 아니다)
    with pytest.raises(RuntimeError, match="HTTP 500"):
        search._openai_embedder()(["x"])


def test_openai_embedder_explains_bad_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-wrong")

    def handler(request):
        return httpx.Response(401, json={"error": "invalid api key"})

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    with pytest.raises(RuntimeError, match="OPENAI_API_KEY"):
        search._openai_embedder()(["x"])
    # 401은 재시도 대상이 아니다: 키가 틀렸는데 네 번 두드릴 이유가 없다


def test_openai_embedder_explains_network_failure(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.setattr(search.time, "sleep", lambda _s: None)

    def handler(request):
        raise httpx.ConnectError("no route to host")

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    with pytest.raises(RuntimeError, match="연결하지 못했다"):
        search._openai_embedder()(["x"])


def test_openai_embedder_rejects_short_response(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    def handler(request):
        return httpx.Response(200, json={"data": [{"index": 0, "embedding": [1.0]}]})

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    with pytest.raises(RuntimeError, match="벡터"):
        search._openai_embedder()(["a", "b"])


def test_openai_embedder_skips_call_for_empty_input(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")

    def handler(request):  # pragma: no cover - 호출되면 테스트 실패
        raise AssertionError("빈 입력으로 API를 부르면 안 된다")

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    assert search._openai_embedder()([]) == []


def test_vec_cache_path_separates_provider_and_model(monkeypatch, tmp_path):
    monkeypatch.setenv("WIKI_EMBED_CACHE", str(tmp_path))
    monkeypatch.delenv("WIKI_EMBED_MODEL", raising=False)
    monkeypatch.setenv("WIKI_EMBED_PROVIDER", "openai")
    remote = search._default_vec_cache().path.name
    monkeypatch.setenv("WIKI_EMBED_PROVIDER", "local")
    local = search._default_vec_cache().path.name
    # 프로바이더를 바꿔도 차원이 다른 벡터가 한 파일에 섞이지 않아야 한다
    assert remote != local and "openai" in remote and "local" in local


def test_no_e5_prefix_on_openai_provider(vault, monkeypatch, tmp_path):
    monkeypatch.setenv("WIKI_EMBED_PROVIDER", "openai")
    monkeypatch.setenv("WIKI_EMBED_CACHE", str(tmp_path))
    claims.create_claim(vault, claim="react hook effect timing", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-01", seq=1)
    seen: list[str] = []

    def recording(texts):
        seen.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(search, "_default_embedder", lambda: recording)
    search.build_index(vault).query("react hook", k=1)
    assert seen and not any(t.startswith(("passage: ", "query: ")) for t in seen)


def _write_sensitive_doc(vault, sensitivity: str, name: str, title: str, body: str):
    (vault / "01_Projects/acme").mkdir(parents=True, exist_ok=True)
    (vault / f"01_Projects/acme/{name}.md").write_text(
        f"---\nid: session-20260825-001\ntype: session\nsensitivity: {sensitivity}\n"
        f"title: {title}\n---\n\n{body}\n", encoding="utf-8")


def test_confidential_body_is_not_sent_but_work_is(vault, monkeypatch, tmp_path):
    monkeypatch.setenv("WIKI_EMBED_PROVIDER", "openai")
    monkeypatch.setenv("WIKI_EMBED_CACHE", str(tmp_path))
    monkeypatch.delenv("WIKI_EMBED_SEND_SENSITIVE", raising=False)
    _write_sensitive_doc(vault, "confidential", "secret-1",
                         "acme secret rollout", "acme secret rollout detail")
    _write_sensitive_doc(vault, "work", "workday-1",
                         "bada deploy notes", "bada deploy notes detail")
    for seq, text in enumerate(["react hook effect timing", "git commit message style",
                                "python gil limits parallelism"], start=1):
        claims.create_claim(vault, claim=text, claim_type="technical_fact",
                            source_refs=["s"], date_str="2026-01-01", seq=seq)
    sent: list[str] = []

    def recording(texts):
        sent.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(search, "_default_embedder", lambda: recording)
    idx = search.build_index(vault)
    assert not any("acme secret" in t for t in sent)   # confidential 본문은 안 나간다
    assert any("bada deploy" in t for t in sent)       # work는 나간다 (사용자 결정)
    assert any("react" in t for t in sent)
    hits = [r["title"].lower() for r in idx.query("acme secret rollout", k=5)]
    assert any("acme" in h for h in hits)              # BM25로는 여전히 찾힌다


def test_send_sensitive_override_lets_confidential_through(vault, monkeypatch, tmp_path):
    monkeypatch.setenv("WIKI_EMBED_PROVIDER", "openai")
    monkeypatch.setenv("WIKI_EMBED_CACHE", str(tmp_path))
    monkeypatch.setenv("WIKI_EMBED_SEND_SENSITIVE", "1")
    _write_sensitive_doc(vault, "confidential", "session-1",
                         "acme rollout notes", "acme rollout internal detail")
    sent: list[str] = []

    def recording(texts):
        sent.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(search, "_default_embedder", lambda: recording)
    search.build_index(vault)
    assert any("acme" in t for t in sent)
