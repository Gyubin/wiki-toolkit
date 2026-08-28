# gbrain 검토 반영 (Spec)

> 상태: 구현 완료 (2026-08-28)

## 배경

gbrain(https://github.com/garrytan/gbrain, v0.47.3.0, 2026-08-27 커밋)을 정독하고 wiki-toolkit에
반영할 요소를 검토했다. 방법: 서브에이전트 36개로 gbrain 8개 영역 정독 + wiki-toolkit 인벤토리,
반영 후보 13건 합성, 후보마다 "제약 적합성"과 "실사용 가치" 두 렌즈의 적대적 검증. 검증은 주장을
믿지 않고 양쪽 repo와 vault를 직접 재서 판정했다 (claim 90개 normalize_key 충돌 0건, unverified
0건 등).

결론: 새 코드 인프라를 들이는 제안은 전부 기각됐고, 축소형 5건만 채택했다. gbrain의 장치
대부분은 DB, 상시 프로세스, 다사용자, 10만 페이지 규모의 문제를 푸는 것이라 여기서는 문제
자체가 없거나 동등물이 이미 있었다.

## 코드 변경 2건: 실측된 id 결함 수정 + 예방적 aliases

id로 검색하면 아예 안 나온다. `search.iter_docs`가 색인 텍스트 head에 title/name/claim/topic만
넣고 id를 안 넣는데, frontmatter는 `parse_doc`이 벗겨내므로 id 문자열이 색인에 등장하는 문서가
**source 0/5, claim 0/90**이었다 (2026-08-28 실측). `source-20260827-004` 질의는 rank 11~49로
밀려 기본 k=8 밖이다. 수정 후 재실측: top-8 밖 0/95, rank 1은 81/95. 정확 일치가 1위를 놓치는
14건은 같은 날짜와 seq 토큰을 공유하는 반대 종류 문서에 밀린 경우다 (`source`/`claim` 접두
토큰은 idf가 낮다).

aliases 쪽은 실측된 결함이 아니라 예방이다. vault에 aliases를 쓴 페이지는 아직 0개이고, 한글
제목과 영문 원어가 갈라져 검색이 놓친 사고도 기록된 것이 없다. 비용이 작고(선택 필드와 색인
한 줄) Obsidian이 이 키를 네이티브로 읽어서 넣었다.

## 결정

1. **`iter_docs`의 head에 `id`와 `aliases`를 포함한다.** `create_wiki_page`/`update_wiki_page`에
   선택 인자 `aliases`(list)를 추가한다. aliases는 Obsidian이 네이티브로 읽는 frontmatter 키라
   퀵 스위처 탐색도 같이 좋아진다. 한글 위키에서 영문 원어와 한글 표기가 갈라지는 문제
   (gbrain의 named-entity 검색 실패와 같은 클래스)를 겨냥한다.
   gbrain의 exact-lookup 계층과 3번째 RRF arm은 이식하지 않는다. title은 head에 이미 있어
   전제가 성립하지 않고, 실측상 정확 제목 질의 7개 전부 top-8 안이었다.
2. **`prompts/ingest.md`의 중복 검사 절차를 "읽고 판단"으로 개정한다** (gbrain
   brain-ingest-gate). 점수 숫자로 판단하지 않고 최상위 히트를 열어 읽고 밴드를 배정한다.
   exists/probable 등급이나 evidence 라벨을 코드로 찍는 확장은 기각했다 (근사 검색은
   `search_wiki`가 이미 하고, 같은 source 형제 claim이 버스트 ingest에서 가짜 양성을
   양산한다).
3. **`prompts/ingest.md`에 계약 버전 문자열을 두고 ingest-log 줄에 함께 적는다.** 계약을
   고쳤을 때 "어떤 source를 옛 방식으로 ingest했나"가 파일에서 결정적으로 나온다.
   content_hash 스키마 필드는 기각했다. `update_source_raw`가 본문을 바꾸는 정상 복구
   경로에서 즉시 낡는다 (2026-08-28에 source 5개 중 4개 재작성 실증).
4. **`prompts/lint.md` 모순 패스에 시간 축 판정을 넣는다** (gbrain contradictions probe의
   verdict enum 축소판). 진짜 모순 / 시간적 대체 / 모순 아님 3분류, 판정 근거는 source의
   captured_at과 Raw 안의 published, 해소는 실행하지 않고 붙여넣기 예시만
   (never-auto-apply), 결과는 vault 밖 파일로 남긴다. 쌍 생성 스크립트와 effective_date
   필드는 기각 (90개는 한 세션이 전수 통독 가능).
5. **personal-wiki CLAUDE.md에 계약 디스패치 표를 추가한다** (gbrain RESOLVER.md 축소판).
   verify.md의 "Bash 금지" 보안 규칙이 어디서도 라우팅되지 않던 구멍을 메운다. 내용은 옮겨
   적지 않고 포인터만 둔다.

## 기각한 것 (다음에 다시 제안하지 않도록 기록)

| 제안 | 기각 근거 (실측) |
| --- | --- |
| create_claim 내장 dedup | claim 90개 전체 normalize_key 충돌 0건. lint `duplicate_claim`이 같은 판정을 이미 함 |
| 검토 적체 lint (N일 방치 unverified) | unverified 0건. `next_step`이 unverified를 최우선 안내라 적체가 침묵할 통로 없음 |
| 지시문 인라인 펜스 격리 | 청킹이 없고 `search_wiki`는 본문을 반환하지 않아 전제 불성립. verbatim 캡처 계약과 lint의 substring 검사를 깨뜨림 |
| verified 게이트 pytest 가드 | 이미 세 겹 기계화 (promote_claim PermissionError, set_claim_status 거부, lint 검사, 셋 다 테스트 있음) |
| 쓰기 시점 인용 원문 대조 | 실측된 사고(2026-08-27)는 인용과 source가 같이 드리프트한 유형이라 원리적으로 못 잡음 |
| create_source 바이너리 가드 | `read_text(encoding="utf-8")` strict 디코딩이 바이너리를 이미 하드 실패시킴 |
| VERIFY.md 검증 런북 | 드리프트할 두 번째 저장소(DB)가 없음. 인덱스는 vault 지문으로 매번 재생성돼 계수 대조가 항진명제 |
| 검색 품질 측정 인프라 (qrels + 쿼리 캡처) | 랭킹 변경 계획이 없고 테스트의 embed_fn 주입이 hermetic 측정을 이미 제공. AGENTS.md에 "랭킹을 바꾸기 전에 질의와 정답 세트를 먼저 만들어 before/after를 같은 실행에서 잰다" 한 줄만 남김 |

reranker, schema pack, push-context, calibration(Brier), 잡 큐, MEMORY_VERBS 프로토콜 등 18건은
합성 단계에서 애초에 제외했다. 공통 사유: DB/상주 프로세스 전제, 또는 단일 사용자 규모에서
표본이나 수요 자체가 없음.

## 재검토 조건

- claim이 수백 개를 넘어 한 세션이 전수 통독을 못 하게 되면: 모순 쌍 생성 스크립트,
  find_similar_claim 근사 확장.
- 랭킹 로직(tokenize, RRF, 융합 가중)을 실제로 바꾸는 변경이 생기면: 그 변경 안에서 질의
  10~20개(정답 id + hard-negative)를 pytest 케이스로 먼저 넣는다. 상시 인프라는 만들지 않는다.
- 검색이 매치 주변 스니펫이나 청킹으로 바뀌면: 지시문 인라인 마킹 재검토.
- id 정확 일치가 rank 1이어야 하는 요구가 생기면: 검색 앞단의 exact-ref 단축 경로를 재검토한다
  (2026-08-28 실측: rank 1은 81/95, top-8 진입은 95/95).
