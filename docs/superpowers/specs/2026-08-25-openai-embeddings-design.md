# 임베딩을 OpenAI API로 전환 (Spec)

> 상태: 구현 완료 (2026-08-25)
> 관련: `2026-06-07-semantic-search-design.md` (하이브리드 검색 원안, 로컬 전용 가정)

## 결정

시맨틱 검색의 임베딩 기본 경로를 로컬 fastembed에서 **OpenAI Embeddings API**로 바꾼다.
로컬 경로는 지우지 않고 `WIKI_EMBED_PROVIDER=local`로 남긴다.

## 왜

- 로컬 경로는 첫 실행에 가중치 2.1GB를 내려받고(`~/.cache/wiki-agents/fastembed`), CPU ONNX로 돈다.
  1인용 vault 규모에서 이 비용이 임베딩 품질보다 크다.
- `text-embedding-3-large`가 multilingual-e5-large보다 한국어 검색 품질에서 앞선다는 것이 이 전환의
  전제인데, **이번에 자체 측정하지 않았다.** 벤치마크는 vault에 문서가 쌓인 뒤 재본다.

## 바뀌는 경계 (중요)

전환 전 ARCHITECTURE.md는 "No external embedding API. vault content never leaves the machine"을
설계 제약으로 명시했다. 이 제약이 깨진다.

- **`sensitivity: work` 본문은 API로 보낸다** (2026-08-25 사용자 결정). 개인 계정을 쓰고, work 콘텐츠가
  나가는 것을 사용자가 명시적으로 허용했다.
- `sensitivity: confidential` 문서의 **본문만 원격 API로 보내지 않는다.** 이 문서들은 0 벡터를 받아
  코사인 기여가 0이 되고 BM25(로컬)만으로 순위에 들어온다. 검색 결과에서 사라지지는 않는다.
  근거: 원리 문서 §3.1이 confidential은 회사 정책을 따르라고 하고, 그 정책은 이 repo가 알 수 없다.
- 해제 스위치: `WIKI_EMBED_SEND_SENSITIVE=1` (confidential까지 전송).
- 질의문 자체는 provider가 openai면 항상 API로 나간다 (사용자가 방금 타이핑한 문장).

## 비용

2026-08-25 openai 공식 가격표 기준 (per 1M input tokens):

| 모델 | 가격 | 기본 차원 |
| --- | --- | --- |
| `text-embedding-3-large` (기본값) | $0.13 | 3072 |
| `text-embedding-3-small` | $0.02 | 1536 |

large가 small의 **6.5배**다. 단 절대액이 작다. 문서 1000개(각 2000토큰 = 200만 토큰)를 전량 임베딩해도
large가 약 $0.26이고, 벡터 디스크 캐시가 있어 바뀐 문서만 다시 임베딩한다. 이 규모에서 6.5배는 실질
차이가 아니라 판단해 large를 기본으로 둔다.

`dimensions` 파라미터(`WIKI_EMBED_DIM`)는 **비용을 줄이지 않는다.** 과금은 입력 토큰 기준이고 출력
차원과 무관하다. 캐시 파일 크기와 코사인 계산량만 줄어든다.

## 구현 형태

- `core/search.py`에 provider 스위치를 둔다: `embed_provider()`, `embed_model_name()`,
  `embed_prefixes()`, `remote_blocked_sensitivities()`.
- e5 접두사(`passage: ` / `query: `)는 로컬 전용이다. OpenAI 모델에는 접두사를 붙이지 않는다.
  주입된 `embed_fn`(테스트, `create_app(embed_fn=...)`)은 하위 호환으로 e5 접두사를 유지한다.
- 벡터 디스크 캐시 파일명에 provider와 모델명을 넣어 차원이 다른 벡터가 한 파일에 섞이지 않게 한다.
- 재시도: 429와 5xx, 네트워크 오류에 대해 지수 백오프로 최대 4회. 배치 96개.
- 빈 vault는 임베더를 만들지 않는다. 즉 문서가 0개면 API 키도 요구하지 않는다.
- 새 의존성 없음. `httpx`는 이미 있고, `core/`는 여전히 `claude_agent_sdk`/`fastapi`/`uvicorn`을
  import하지 않는다 (test_architecture 통과).

## 검증

- 12개 테스트 추가 (`tests/test_search.py`): provider 기본값, 키 부재 시 즉시 실패, 배치 분할,
  응답 index 기준 순서 복원, dimensions 전달, 429와 ConnectError 재시도, 응답 개수 불일치 거부,
  빈 입력에서 호출 안 함, 캐시 파일 분리, 접두사 미적용, 민감 문서 미전송과 해제 스위치.
- 전체 155개 통과, ruff clean.
- **실제 API 호출로는 검증하지 않았다** (이 머신에 `OPENAI_API_KEY`가 없다). httpx MockTransport
  기준이므로, 첫 실키 호출에서 응답 스키마와 rate limit 동작을 한 번 확인해야 한다.

## 보류

- 사내 게이트웨이를 쓸 경우의 인증 헤더 형식은 확인하지 않았다. `WIKI_OPENAI_BASE_URL`로 엔드포인트만
  갈아끼울 수 있게 해뒀고, 헤더는 `Authorization: Bearer` 고정이다.
- work/confidential 문서용 별도 로컬 인덱스(두 벡터 공간 분리)는 만들지 않았다. 지금은 그 문서들이
  BM25로만 검색된다.
