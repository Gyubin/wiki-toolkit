# semantic search — Design (Spec)

> 상태: 합의 완료(brainstorming), 구현 계획 대기
> 날짜: 2026-06-07
> 기반: phase 1 + wrap-feature + wiki-lint 구현 완료. 설계 §3.7(retrieval) "BM25 + semantic embedding + reranking".

## Context

`/answer-from-wiki`와 일반 탐색은 지금 Read/Grep/Glob(어휘 일치)에 의존한다. 동의어·패러프레이즈로
물으면 못 찾는다. 의미 기반 검색을 추가해 "비슷한 뜻"의 claim/위키/세션/학습 문서를 찾는다.

설계상 문서 1000개 전엔 보류 권장이었으나, 사용자가 당겨서 구현하기로 결정했다.

**보안(중요):** 통합 vault에는 work/confidential이 섞여 있다. 따라서 **vault 본문을 외부 임베딩 API로
보내지 않는다.** 임베딩은 **로컬 모델(fastembed, ONNX)** 로만 만든다. 데이터는 로컬을 벗어나지 않는다.

## Goals (v1)

1. **하이브리드 검색** — BM25(어휘) + 로컬 임베딩(의미)을 **RRF**로 융합, `core/search.py`.
2. **임베더 주입 가능** — 테스트는 결정론적 가짜 임베더로 모델 다운로드 없이 검증.
3. 노출: `search_wiki` MCP 도구(+ answer 서브에이전트), `GET /search`, **Search 탭**, CLI `uv run wiki search`.

## Non-goals (v1)

- 외부 임베딩 API(보안 위반). LLM reranking(설계상 더 나중). 영속 임베딩 캐시/증분 색인(인프로세스 캐시 + 수동 reindex로 충분).
- graph expansion(별도).

## 기술/일관성

phase 스택 + `rank-bm25`, `fastembed`(로컬 ONNX 임베딩). "무결성/판정은 core 순수 함수" 패턴 유지 —
검색은 LLM 무관(임베딩 모델만 사용). 검색 자체엔 Claude CLI 불필요.

## 핵심 — `core/search.py`

- `iter_docs(vault) -> list[Doc]`: 지식 문서 수집. 포함 루트: `00_Inbox`, `01_Projects`, `02_Areas`,
  `03_Resources`, `10_Claims`, `30_Learning`의 `*.md`. 제외: `06_Metadata`, `docs/`, vault 루트의 설계 `*.md`/`*.canvas`.
  `Doc = {"ref": id-or-name-or-relpath, "title": str, "text": str, "path": str}`. text = frontmatter의
  title/name/claim/topic 등 핵심값 + 본문.
- `tokenize(text) -> list[str]`: 소문자 영숫자 토큰(BM25용).
- `class SearchIndex(docs, embed_fn)`:
  - 생성 시 BM25 코퍼스(`rank_bm25.BM25Okapi`) + `embed_fn([doc.text...])`로 문서 임베딩 행렬 구축.
  - `query(q, k=8) -> list[dict]`: BM25 점수 순위 + 쿼리 임베딩 코사인 순위를 **RRF**(`score = Σ 1/(60+rank)`)로 융합, 상위 k = `[{"ref","title","score","snippet"}]`. snippet = text 앞 200자.
- `build_index(vault, embed_fn=None) -> SearchIndex`: `embed_fn` 없으면 기본 **fastembed 로컬 임베더**
  (lazy import; 다국어 모델 — vault에 한국어 포함, 가용 모델명은 구현 시 `TextEmbedding.list_supported_models()`로 확인). 임베더는 `list[str] -> list[list[float]]` 형태.

테스트용 가짜 임베더 예: bag-of-words 해시 벡터(결정론적) — 의미 매칭을 흉내 내어 RRF/랭킹 플러밍을 검증.

## 배선

- MCP 도구 `search_wiki(query, k)` → 앱 캐시 인덱스 질의, 결과를 텍스트로 반환. `WIKI_TOOL_NAMES`에 추가.
- **answer 서브에이전트** tools에 `mcp__wiki__search_wiki` 추가(어휘 Grep 보강). `agent.py`는 splat이라 allowed_tools 자동 포함 — 변경 불필요.

## 웹 / 엔트리

- `create_app(vault, embed_fn=None)` — `embed_fn` 기본 None(런타임 fastembed); 테스트는 가짜 주입.
- 인프로세스 인덱스 캐시(앱 클로저). `GET /search?q=&k=8&reindex=0` → 첫 호출 또는 `reindex=1`에 `build_index(vault, embed_fn)` 후 `query` → JSON 결과. 빈 `q`는 `[]`.
- **Search 탭**: q 입력 + 검색 버튼 → 결과(제목·스니펫·점수) 목록.
- `__main__.py`에 `search` 커맨드: `uv run wiki search "<query>"` → 결과 출력(런타임 fastembed).

## 구조 (추가/수정)

```
wiki_agent/core/search.py   # NEW
wiki_agent/tools.py         # MODIFY: search_wiki + name
wiki_agent/subagents.py     # MODIFY: answer에 search_wiki
wiki_agent/app.py           # MODIFY: create_app(embed_fn=None) + GET /search + 캐시
wiki_agent/web/index.html   # MODIFY: Search 탭
wiki_agent/__main__.py      # MODIFY: search 커맨드
pyproject.toml              # MODIFY: rank-bm25, fastembed
tests/
  test_search.py            # NEW (가짜 임베더)
  test_app.py               # MODIFY (/search via fake embedder)
  test_subagents.py         # MODIFY (answer has search_wiki)
```

## 테스트 전략

- `core/search.py`(가짜 결정론적 임베더): (a) 의미적으로 쿼리와 가장 가까운 문서가 top-1, (b) `tokenize` 동작, (c) `iter_docs`가 06_Metadata/docs를 제외하고 지식 루트만 수집, (d) RRF가 BM25-only/임베딩-only를 적절히 융합(둘 다 1위인 문서가 최상위), (e) 빈 코퍼스/빈 쿼리 안전.
- `test_app.py`: `create_app(vault, embed_fn=fake)`로 문서 몇 개 심고 `GET /search?q=...`가 200 + 관련 문서 상위 반환(모델 무관). `/search` 라우트 존재.
- `test_subagents.py`: `answer`의 tools에 `mcp__wiki__search_wiki` 포함 단언.
- 실제 fastembed 품질(한국어 포함)·최초 모델 다운로드는 라이브 수동 검증.

## 검증(완료 기준)

전체 pytest 그린(가짜 임베더). `uv run wiki search "비슷한 의미의 질의"` 및 Search 탭에서
어휘가 정확히 일치하지 않아도 의미상 관련 문서가 상위에 뜸. answer 흐름이 search_wiki를 활용.
fastembed 최초 모델 다운로드는 라이브에서 1회 발생.
