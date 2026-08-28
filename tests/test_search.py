import json

import httpx
import pytest

from wiki_toolkit.core import claims, search, sources, wiki

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


def test_a_poison_doc_becomes_bm25_only_instead_of_killing_the_index(monkeypatch):
    """토큰 상한을 넘는 문서 하나가 인덱스 빌드 전체를 죽이면, 캐시에 못 들어가서
    이후 모든 검색이 같은 지점에서 죽는다. 0 벡터로 강등해 BM25 전용으로 살린다."""
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("WIKI_EMBED_PROVIDER", raising=False)
    monkeypatch.delenv("WIKI_EMBED_DIM", raising=False)

    def handler(request):
        body = json.loads(request.content)
        if any("POISON" in t for t in body["input"]):
            return httpx.Response(400, json={"error": "input too long"})
        rows = [{"index": i, "embedding": [1.0, 2.0]}
                for i, _ in enumerate(body["input"])]
        return httpx.Response(200, json={"data": rows})

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    vecs = search._openai_embedder()(["정상 문서", "POISON " * 200])
    assert vecs[0] == [1.0, 2.0]
    assert vecs[1] == [0.0, 0.0]


def test_an_oversized_doc_is_salvaged_by_halving(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "k")
    monkeypatch.delenv("WIKI_EMBED_PROVIDER", raising=False)
    monkeypatch.delenv("WIKI_EMBED_DIM", raising=False)

    def handler(request):
        body = json.loads(request.content)
        if any(len(t) > 5000 for t in body["input"]):
            return httpx.Response(400, json={"error": "input too long"})
        rows = [{"index": i, "embedding": [float(len(t))]}
                for i, t in enumerate(body["input"])]
        return httpx.Response(200, json={"data": rows})

    monkeypatch.setattr(search, "_openai_client", lambda: _mock_client(handler))
    vecs = search._openai_embedder()(["short", "x" * 20000])
    assert vecs[0] == [5.0]
    assert 0 < vecs[1][0] <= 5000  # 반으로 줄여가며 살렸다


def test_vec_cache_filename_includes_the_dimension(monkeypatch):
    """차원을 바꾸면 새 캐시를 써야 한다. 안 그러면 문서는 구 차원, 쿼리는 새 차원이
    되어 행렬곱에서 죽는다 (감사에서 재현)."""
    monkeypatch.delenv("WIKI_EMBED_PROVIDER", raising=False)
    monkeypatch.delenv("WIKI_EMBED_MODEL", raising=False)
    monkeypatch.delenv("WIKI_EMBED_DIM", raising=False)
    base = search._default_vec_cache().path.name
    monkeypatch.setenv("WIKI_EMBED_DIM", "256")
    dimmed = search._default_vec_cache().path.name
    assert base != dimmed and "256" in dimmed


def test_pre_ingest_clip_is_not_sent_to_the_remote_embedder():
    """민감도는 ingest 때 부여된다. 그 전의 클립은 태그가 없어서 confidential 차단에
    안 걸리므로, 원격 차단 맥락에서는 id 없는 Inbox 문서를 보내지 않는다."""
    docs = [
        {"ref": "clip.md", "title": "클립", "text": "은밀한 회사 문서 내용",
         "path": "00_Inbox/raw/clip.md", "sensitivity": "", "pre_ingest": True},
        {"ref": "note", "title": "노트", "text": "공개 노트",
         "path": "03_Resources/note.md", "sensitivity": "personal", "pre_ingest": False},
    ]
    seen = []

    def embed(texts):
        seen.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    idx = search.SearchIndex(docs, embed, prefixes=("", ""),
                             skip_sensitivities=("confidential",))
    assert seen == ["공개 노트"]                 # 클립 본문은 원격으로 안 나갔다
    out = idx.query("은밀한 회사")
    assert "clip.md" in {r["ref"] for r in out}  # BM25로는 여전히 찾힌다


def test_index_cache_degrades_to_bm25_when_embedding_fails(vault):
    """vault 변경 + 임베딩 장애가 로컬 BM25까지 죽이면 안 된다."""
    (vault / "03_Resources/Concepts/rrf.md").write_text(
        "---\ntype: concept\nname: RRF\n---\n\nRRF는 순위 융합이다\n", encoding="utf-8")

    def boom(texts):
        raise search.EmbeddingUnavailable("network down")

    cache = search.IndexCache(vault, embed_fn=boom)
    idx = cache.get()
    assert idx.degraded is True
    out = idx.query("순위 융합")
    assert out and out[0]["ref"] == "RRF"


def test_query_time_outage_degrades_to_bm25():
    """웜 캐시면 빌드는 API 없이 성공하고, 첫 원격 호출이 쿼리 임베딩이다.
    거기서 죽으면 "장애 시 BM25 강등"이 제일 흔한 상태에서 안 지켜진다."""
    calls = {"n": 0}

    def flaky(texts):
        calls["n"] += 1
        if calls["n"] > 1:
            raise search.EmbeddingUnavailable("network down")
        return [[1.0, 0.0] for _ in texts]

    docs = [{"ref": "a", "title": "문서", "text": "순위 융합 이야기",
             "path": "x.md", "sensitivity": ""}]
    idx = search.SearchIndex(docs, flaky, prefixes=("", ""))
    out = idx.query("순위 융합")
    assert out and out[0]["ref"] == "a"       # BM25 결과는 나온다
    assert idx.query_degraded is True
    # 임베딩이 회복되면 플래그도 내려간다
    calls["n"] = -10
    idx.query("순위 융합")
    assert idx.query_degraded is False


def test_pre_ingest_block_is_wired_through_iter_docs(vault, monkeypatch, tmp_path):
    """iter_docs의 pre_ingest 표시가 빠지면 차단이 통째로 풀린다. 손으로 만든 docs가
    아니라 실제 vault 경로로 끝까지 고정한다."""
    monkeypatch.setenv("WIKI_EMBED_PROVIDER", "openai")
    monkeypatch.setenv("WIKI_EMBED_CACHE", str(tmp_path))
    monkeypatch.delenv("WIKI_EMBED_SEND_SENSITIVE", raising=False)
    (vault / "00_Inbox/browser-clips/clip.md").write_text(
        "---\ntitle: 클립\nurl: http://x\n---\n\n은밀한 회사 문서 내용\n", encoding="utf-8")
    sent: list[str] = []

    def recording(texts):
        sent.extend(texts)
        return [[1.0, 0.0] for _ in texts]

    monkeypatch.setattr(search, "_default_embedder", lambda: recording)
    search.build_index(vault)
    assert not any("은밀한" in t for t in sent)


def test_embed_input_is_capped(vault):
    """상한 없이 보내면 8k 토큰 넘는 문서 하나가 HTTP 400으로 빌드를 죽인다."""
    docs = [{"ref": "big", "title": "긴 문서", "text": "가" * 20000,
             "path": "x.md", "sensitivity": ""}]
    got: list[str] = []

    def embed(texts):
        got.extend(texts)
        return [[1.0] for _ in texts]

    search.SearchIndex(docs, embed, prefixes=("", ""))
    assert got and all(len(t) <= search._EMBED_MAX_CHARS for t in got)


def test_embed_cache_override_expands_tilde(monkeypatch):
    """.env에서 온 값은 셸을 거치지 않아 ~가 그대로 남는다. 안 펼치면 cwd에
    문자 그대로 '~' 디렉터리가 생긴다."""
    from pathlib import Path
    monkeypatch.setenv("WIKI_EMBED_CACHE", "~/some-cache")
    p = search._embed_cache_dir()
    assert "~" not in p
    assert p == str(Path.home() / "some-cache")


def test_id_is_in_indexed_text(vault):
    """frontmatter는 parse_doc이 벗겨내므로 head가 id를 안 넣으면 색인에 id가 아예 없다.

    2026-08-28 실측: id 문자열이 자기 문서의 색인 텍스트에 등장하는 문서가 source 0/5,
    claim 0/90이었다. 질의 수준 테스트는 동점 시 길이 정규화 우연으로 통과할 수 있어서
    (실제로 구현 전에 통과했다) 색인 텍스트를 직접 본다.
    """
    claims.create_claim(vault, claim="라우터가 토큰을 배분한다", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-02", seq=1)
    texts = {d["ref"]: d["text"] for d in search.iter_docs(vault)}
    assert "claim-20260102-001" in texts["claim-20260102-001"]


def test_id_query_finds_the_doc(vault):
    """id는 frontmatter에만 있어서 예전에는 색인 텍스트에 아예 없었다.

    2026-08-28 실측: id 문자열이 자기 문서의 색인 텍스트에 등장하는 문서가 source 0/5,
    claim 0/90이라 id 질의가 rank 11~49로 밀렸다. head에 id를 넣어 고친다.
    """
    # 대상을 파일 순서상 뒤(더 늦은 날짜)에 두고, 실제 vault처럼 같은 날짜와 seq를 가진
    # 반대 종류 문서(source-20260102-001)도 넣는다. 날짜와 seq 토큰을 공유하는 문서가
    # 있으면 정확 일치가 1위를 놓칠 수 있어(2026-08-28 실측 81/95) top-3 진입까지만
    # 보장한다. rank-1 보장이 필요해지면 exact-ref 단축 경로를 재검토한다 (spec 참조).
    claims.create_claim(vault, claim="git commit message style", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-01", seq=1)
    claims.create_claim(vault, claim="라우터가 토큰을 배분한다", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-02", seq=1)
    sources.create_source(vault, origin="browser", date_str="2026-01-02", seq=1,
                          content="같은 날짜와 seq를 가진 source 문서 " * 5)
    idx = search.build_index(vault, embed_fn=_zero_embed)
    refs = [r["ref"] for r in idx.query("claim-20260102-001", k=8)]
    assert "claim-20260102-001" in refs[:3]


def test_alias_query_finds_wiki_page(vault):
    """한글 제목 페이지를 영문 원어로 찾는 경로: aliases frontmatter가 색인에 들어가야 한다."""
    wiki.create_wiki_page(vault, name="전문가 혼합", page_type="concept",
                          body="라우터가 토큰을 배분한다", claim_refs=[],
                          date_str="2026-01-01", aliases=["mixture of experts"])
    wiki.create_wiki_page(vault, name="다른 페이지", page_type="concept",
                          body="experts라는 단어가 본문에 있다 mixture", claim_refs=[],
                          date_str="2026-01-01")
    idx = search.build_index(vault, embed_fn=_zero_embed)
    results = idx.query("mixture of experts", k=3)
    assert results and results[0]["title"] == "전문가 혼합"
