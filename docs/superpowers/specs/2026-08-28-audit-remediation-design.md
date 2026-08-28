# 2026-08 전체 감사 수습 (Spec)

> 상태: 구현 완료 (2026-08-28, 검증 라운드까지 반영)

## 문제

2026-08-28에 repo 전체를 검토했다 (코드, 프롬프트 계약, 테스트, 운영 문서를 7개 차원으로
훑고, 발견마다 독립 검증자 3명이 반박을 시도해 2표 이상 받은 것만 남김). 원발견 55건 중
45건이 확정됐다. 전부 고치지는 않는다. 이 spec은 그중 "실제로 자주 발화하고 조용히
틀리는" 것들을 고른다.

가장 아픈 두 가지는 시스템의 핵심 약속이 뚫린 것이다.

1. **"confidential은 밖으로 안 나간다"가 거짓이 되는 경로 둘.**
   MCP `create_claim`이 sensitivity를 노출하지 않아 모든 claim이 `personal`로 태어난다.
   confidential source에서 뽑은 claim은 `## 원문`에 그 원문을 verbatim으로 담으므로,
   source 본문 차단(search.py)을 파생 문서가 우회해 임베딩 API로 나간다.
   또 ingest 전의 클립은 frontmatter에 sensitivity가 없어서 차단 판정(문자열 일치)에
   안 걸리고, 그 창에서 검색 한 번이면 본문 전체가 나간다.
2. **"verified는 근거로만"의 게이트가 truthiness 검사다.**
   `evidence_refs=[""]`가 `promote_claim`을 통과하고, lint의 `verified_without_evidence`도
   같은 판정식이라 잡지 못한다 (재현됨).

그 다음 급이 안내가 틀리는 것들이다. 안내가 틀리면 통째로 무시된다는 것은 이 repo가
이미 배운 교훈이다 (pipeline.py의 2026-08-28 주석).

- `list_pending`이 폴더를 세서, 검토 끝난 `accepted_for_now`가 영원히 pending으로 나온다
  (pipeline에서 고친 것과 같은 버그가 형제 함수에 남았다).
- `create_source`가 source id를 반환하지 않아, 병렬 ingest에서 CLAUDE.md의 "grep으로
  매핑 확인" 우회가 필요해졌다.
- wiki page 승격 안내가 verified 폴더만 세는데 실사용 검토 결과는 거의 전부
  attributed/accepted_for_now라 그 단계가 한 번도 발화하지 않는다.
- ingest가 끝난 클립 원본(삭제 대기)이 "인제스트해줘"로 다시 안내되고, YAML이 깨진
  클립은 집계에서 사라진다.

검색은 원격 임베딩 경로의 실패 처리가 문제다: 8k 토큰 넘는 문서 하나가 HTTP 400으로
인덱스 빌드를 영구히 죽이고(그 문서는 캐시에 못 들어가므로 반복), `WIKI_EMBED_DIM`을
바꾸면 캐시 차원 불일치로 쿼리마다 크래시, API 장애면 로컬 BM25까지 전멸한다.

감사 추적도 약속과 다르다: `commit_vault`의 paths 제한이 `git add`에만 걸리고 `git commit`에
pathspec이 없어서, 사용자가 스테이징해 둔 무관한 파일이 에이전트 커밋에 쓸려 들어간다.
그리고 이 자동 커밋 전체에 테스트가 없다 (모든 도구 테스트가 git 아닌 vault에서 돌아
no-op이다).

전체 발견 목록과 검증 기록은 감사 세션 산출물(audit-result.json)에 있고, 이 spec은 그중
1군(반환값/게이트 소수정), 2군(신뢰 모델), 3군(검색 견고성), 4군(파이프라인 의미론),
5군(테스트)을 채택한 것이다.

## 결정

### 게이트와 민감도

- `promote_claim`과 lint 둘 다 근거 판정을 "공백 아닌 문자열이 하나라도 있는가"로 바꾼다
  (`claims.has_written_evidence`, 단일 판정 함수).
- `create_claim` MCP 도구에 `sensitivity` 선택 인자를 노출하고, 안 주면 `source_refs`가
  가리키는 source들의 최고 민감도를 상속한다 (`sources.max_sensitivity`).
- ingest 전의 Inbox 문서(id 없음)는 원격 임베딩에서 제외한다 (BM25로는 계속 검색됨).
  `WIKI_EMBED_SEND_SENSITIVE=1`이면 기존과 같이 전부 보낸다.
- 경로/glob에 들어가는 id 인자(claim_id, source_id, learning_id)는
  `schema.validate_doc_id`로 형식을 검증한다. `../`와 `*`가 파일 조회에 닿지 못하게 한다.

### 파이프라인 안내

- `list_pending`은 status가 `unverified`인 것만 돌려준다.
- `create_source` 반환에 source id를 넣는다: `created source-YYYYMMDD-NNN (파일명)`.
- `triage_record`는 source 존재를 먼저 확인하고, 반환에 id와 결정을 적는다.
- wiki page 승격 대기는 verified 폴더가 아니라 인용 가능 status
  (`verified/attributed/accepted_for_now/partially_true`) 기준으로 센다
  (`vault_state`의 `verified_unlinked` 키는 `citable_unlinked`로 바뀐다).
- id 없는 Inbox 클립 중 frontmatter url이 이미 등록된 source의 url과 일치하는 것은
  "ingest 끝남, 삭제 대기"로 분리 안내한다 (pipeline과 lint 같은 판정).
- YAML이 깨진 클립도 ingest 대기로 센다 (지금은 조용히 사라진다).
- 검토 단계 안내에 검토표(tools/render_review.py) 힌트를 붙인다.

### 검색 견고성

- 임베딩 입력을 16,000자에서 절단한다 (BM25는 전체 본문을 계속 본다).
- 배치가 HTTP 400이면 항목별로 재시도하고, 항목 단독으로도 400이면 반으로 줄여가며
  살린다. 끝까지 안 되면 0 벡터로 포기한다 (그 문서는 confidential과 같은 BM25 전용).
- 벡터 캐시 파일명에 `WIKI_EMBED_DIM`을 넣는다 (차원 변경 = 새 캐시).
- 일시적 실패(네트워크, 429/5xx 소진)는 `EmbeddingUnavailable`로 구분해 던지고,
  MCP 도구 경로(IndexCache)는 어떤 임베딩 실패든 BM25 전용 인덱스로 강등해 경고를
  붙인다 (지문을 저장하지 않아 다음 호출에서 자가 회복). CLI는 `EmbeddingUnavailable`일
  때만 강등하고, 설정 오류(키 없음/거부)는 지금처럼 안내 + exit 2.

### 감사 추적

- `commit_vault`의 `git commit`에도 pathspec을 건다. 사용자가 스테이징해 둔 무관한
  파일이 쓸려 들어가지 않는다.
- 자동 커밋이 실패하면 (vault가 git repo인데 커밋이 안 됐으면) 도구 반환에 경고 한 줄을
  붙인다. 쓰기는 계속 비차단.
- git vault에서 도구 핸들러가 실제로 커밋을 남기는지 테스트로 고정한다.

### 그 밖의 확정 버그 소수정

- `update_wiki_page`가 `updated` 날짜를 갱신한다.
- `update_index`가 항목 텍스트의 개행을 접는다 (두 줄짜리 항목이 고아 줄을 남기는 버그).
- `_find_file`류의 못 찾음 에러에 동사를 붙인다 (`no such claim: ...`).
- `collect_git_session`이 diff를 자를 때 절단 표시를 붙인다.
- `_find_file`이 상태 폴더를 고정 순서로 순회한다 (두 사본이 생긴 손상 상태에서
  세션마다 다른 파일을 집는 비결정성 제거).
- scaffold의 wiki-page 템플릿을 prompts/wiki-page.md 계약(콘텐츠 위, 근거 아래)으로
  바꾼다. 지금 템플릿은 2026-08-28에 버린 형식을 새 vault마다 심고 있다.
- `.env.example`에 `WIKI_OPENAI_BASE_URL`, `WIKI_EMBED_CACHE`를 추가한다.

### 프롬프트 계약 정비

- verify.md: Bash 금지(주입 방어)와 수리 도구(update_claim_quote, update_source_raw)
  안내를 적는다. 지금은 ARCHITECTURE의 "지운 것" 절에만 있다.
- lint.md: 읽기 전용(Write/Edit/Bash 금지)을 명문화한다.
- answer.md: system.md와 같은 7개 범주로 맞추고("프로젝트 기준" 누락), 주입 경고를
  붙인다.
- ingest.md: 클립 frontmatter의 url 키 이름을 web-clipper-setup.md의 실제 템플릿
  (`url:`)과 일치시킨다. 지금은 `source`라고 적혀 있어 계약끼리 모순이다.

### 테스트 하네스

- 아키텍처 테스트: 모든 최상위 모듈이 `_LAYER`에 분류되어 있어야 한다. 지금은 새
  모듈이 모든 검사에서 면제된다.
- conftest: `WIKI_ENV_FILE`을 없는 경로로 고정해 개발자의 실제 `.env`가 테스트
  프로세스에 새지 않게 한다.

## 비범위 (알고 남기는 것)

- `update_claim_quote`가 `## 원문` 뒤 내용을 지우는 것: core가 만드는 파일에는 그 뒤에
  아무것도 없어서 손 편집된 파일에서만 발화한다. 계약 위반이지만 급하지 않다.
- render_review의 숫자 부분 문자열 매칭, claim_refs와 본문 id 집합 lint,
  `create_wiki_page`의 body_path, index 재작성의 원자성, .env 인라인 주석,
  봇월 문구 하드 블록 완화, record_review 자동 승급, LICENSE 선택.
- 같은 날 repo 이름을 wiki-agents에서 **wiki-toolkit**으로 바꿨다 (여기엔 에이전트가
  없다는 사실을 이름이 약속하도록). CLI 명령, MCP 서버명, 도구 접두사는 `wiki` 그대로다.

## 검증 라운드에서 추가로 고친 것 (같은 날)

수습 diff를 독립 검증자들이 다시 훑어 12건을 보고했고, 판정 결과 다음을 추가로 고쳤다.

- **쿼리 시점 임베딩 무가드 (high).** BM25 강등이 빌드에만 걸려 있었다. 벡터 캐시가
  따뜻하면 빌드는 API 없이 성공하고 첫 원격 호출이 쿼리 임베딩이라, 정확히 제일 흔한
  상태에서 장애가 검색을 죽였다 (재현됨). `SearchIndex.query`가 잡아서 그 쿼리를 BM25로
  답하고 `query_degraded`를 세운다. 도구와 CLI가 경고를 표면화한다.
- **재클리핑 오분류 (medium).** leftover 판정이 url 일치뿐이라, 같은 페이지를 나중에
  다시 클리핑한 새 캡처(내용 갱신)를 "지워라"로 안내했다. 따르면 새 내용이 사라진다.
  클립 전문이 source 본문에 담겨 있을 때만 leftover다 (pipeline과 lint 동일 판정).
- **커밋 경고 오발 (low).** 같은 내용을 다시 쓰면 커밋할 변경이 없는데 그걸 실패로
  경고했다. 스코프에 staged 변경이 없으면 True를 돌려준다.
- **render_review가 잘못된 id에 트레이스백 (low).** find_source의 id 검증이 낳은
  ValueError를 잡아 기존 안내로 끝낸다.
- **`~` 미확장 (medium).** `.env`의 `WIKI_EMBED_CACHE`와 `WIKI_VAULT`는 셸을 거치지
  않아 `~`가 문자 그대로 남았다. 소비 지점에서 expanduser한다.
- **검토표 힌트에 필수 `--out`이 빠져 있었다 (low).**
- **문서 3건.** 클리퍼 문서와 README 두 벌이 pre-ingest 차단을 무조건으로 서술했는데
  `WIKI_EMBED_SEND_SENSITIVE=1`이면 풀린다. 한글 README가 "git repo면" 조건을 빠뜨렸다.
- **테스트 2건.** pre-ingest 차단을 iter_docs까지 관통해서 고정 (손으로 만든 docs만
  검사해서 표시 쪽 절반은 되돌려도 초록이었다), `_EMBED_MAX_CHARS` 절단 고정.

알고 남기는 것: merge 진행 중(MERGE_HEAD)에는 pathspec 커밋이 거부되어 그 창의 쓰기는
감사 커밋 없이 경고만 남는다 (merge를 끝내면 복구). git이 partial commit을 merge 중에
금지하는 것이라 우회하지 않는다.
