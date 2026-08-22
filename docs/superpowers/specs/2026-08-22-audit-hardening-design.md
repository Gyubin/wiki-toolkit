# Audit hardening design (2026-08-22)

7개 영역 병렬 감사(코어, 검색, 에이전트 연동, 앱/CLI, vault 실태, 테스트/프로세스, 런타임 실행)에서
확정된 결함을 고치는 작업의 설계 결정. 발견 각각은 적대적 검증을 통과한 것만 반영한다.

## 확정된 결함과 결정

### A. 데이터 무결성 (core)

1. **claim ID 충돌.** `_next_seq`(tools.py, app.py에 중복 구현)가 `10_Claims/pending`의
   파일 수만 센다. claim이 승격되어 pending을 떠나면 카운트가 줄어, 같은 날 새 claim이
   이미 존재하는 ID를 다시 받는다. 결정: 파일 수 대신 해당 날짜의 **최대 seq + 1**을
   대상 디렉터리 전체(claims는 `10_Claims` 재귀)에서 계산하는 `core/ids.py:next_seq`를
   만들고 tools.py와 app.py가 공유한다.

2. **frontmatter 파싱이 값 안의 `---`에서 깨진다.** `schema.parse_doc`이
   `text.split("---", 2)`라서 줄 중간의 `---`(claim 텍스트에 흔함)에서 잘린다.
   결정: 줄 단위 앵커(`^---$`) 기반 파싱으로 교체. 닫는 펜스가 없으면 frontmatter가
   없는 문서로 취급한다(현재는 ValueError로 죽는다).

3. **`set_claim_status`로 verified 우회 승격 가능.** core가 내부적으로
   `approved_by_human=True`를 넘기므로 도구 경로로 verified를 그냥 통과시킨다.
   결정: core에서 `status="verified"`를 거부한다(ValueError). verified는
   `promote_claim` 단일 경로.

4. **인덱스 upsert가 substring 매칭.** `entry_id in ln`이라 다른 항목의 본문에 해당
   ID가 언급되면 그 줄까지 지운다. 결정: `ln.startswith(f"- [{entry_id}]")` 정확 매칭.

5. **한국어 텍스트가 정규화에서 소실.** `normalize_key`와 `search.tokenize`가
   `[a-z0-9]+`만 남겨 한국어 claim은 전부 빈 키가 되고(모두가 서로 중복 판정),
   한국어 검색은 BM25 매칭이 0이 된다. 결정: 한글 토큰을 포함하고, 키가 비면 원문
   폴백. BM25용 토큰화는 한글 연속열을 2-gram으로 쪼갠다(형태소 분석기 의존성 없이
   실용적인 표준 기법).

6. **한국어 이름 위키 페이지가 전부 `page.md` 하나로 충돌.** `wiki._slug`가
   `[^a-z0-9]+`를 전부 `-`로 바꿔 한글 이름이 빈 슬러그가 되고, 기존 파일을 조용히
   덮어쓴다. 결정: 슬러그에 한글 허용 + `create_wiki_page`는 기존 파일이 있으면
   FileExistsError(덮어쓰기는 `overwrite=True` 명시 시에만). `update_wiki_page`를
   MCP 도구로도 노출한다.

### B. verified 게이트 (agent 연동)

7. **`can_use_tool` 게이트가 죽은 코드.** 모든 wiki 도구가 `allowed_tools`에 들어가
   사전 승인되므로 권한 콜백이 promote에 대해 한 번도 호출되지 않는다. 또한 도구
   스키마상 모델이 `approved_by_human=true`를 스스로 넘길 수 있다. 결정(다층 방어):
   - tools.py의 promote_claim 래퍼는 `approved_by_human`을 **절대 전달하지 않는다**.
     에이전트 경로의 verified는 `evidence_refs`가 유일한 통로. 사람 승인은 웹 UI의
     `/claims/{cid}/approve`로만 들어온다.
   - `allowed_tools`에서 `promote_claim`과 `set_claim_status`를 빼서 이 둘은 항상
     `can_use_tool`을 거치게 한다.
   - permissions.py는 두 도구 모두 검사하고, 입력에서 `approved_by_human`을 제거한
     updated_input을 돌려준다.

8. **도구 스키마 미선언 파라미터.** SDK의 `{이름: 타입}` 단축형은 선언된 것만 노출하고
   전부 required로 만든다. `create_claim`의 `source_refs`(핵심 가치인 출처 연결),
   `promote_claim`의 `evidence_refs`(verified의 유일한 정상 통로!), `create_source`의
   `url`, `search_wiki`의 `k` 등이 모델에게 보이지 않았다. 결정: 선택 파라미터가 있는
   도구는 완전한 JSON 스키마(`type/properties/required`)로 선언한다.

### C. 검색

9. **매 프로세스/세션마다 vault 전체 재임베딩.** CLI `search`는 매 실행마다,
   서버/도구는 첫 질의마다 전량 임베딩한다. 또 세션 내 캐시는 vault가 바뀌어도
   갱신되지 않는다(막 만든 페이지가 검색 안 됨). 결정: (a) 문서 텍스트 해시 기반
   임베딩 디스크 캐시(`$WIKI_EMBED_CACHE` 아래 JSON), (b) vault 지문(md 파일 수 +
   최대 mtime)으로 무효화되는 인덱스 캐시. 바뀐 문서만 재임베딩된다.

10. **e5 모델을 접두사 없이 사용.** multilingual-e5는 `query: `/`passage: ` 접두사가
    없으면 검색 품질이 떨어진다(모델 카드 명시). 결정: SearchIndex 내부에서 문서는
    `passage: `, 질의는 `query: `를 붙여 임베딩한다.

11. **순수 파이썬 코사인.** 1024차원 리스트를 파이썬 루프로 계산한다. 결정: numpy
    행렬곱으로 교체(의존성은 fastembed가 이미 끌고 옴, pyproject에 명시 추가).

### D. 앱/CLI

12. **/chat이 요청마다 새 세션.** WikiSession의 멀티턴 설계가 웹 흐름에서 죽어 있다
    (대화 연속성 없음). 결정: 앱 수준 지속 세션 + asyncio.Lock 직렬화 + `/chat/reset`.

13. **SSE 프레이밍 오류.** 청크에 개행이 있으면 `data: {chunk}\n\n`가 프로토콜을
    깬다. 결정: 청크를 줄 단위로 쪼개 각 줄에 `data: ` 접두사.

14. **드라이브바이 요청 방어 없음.** 127.0.0.1 바인딩이지만 브라우저의 아무 웹페이지가
    `/chat`(Bash 가진 에이전트 실행)이나 `/capture`에 POST할 수 있다. 결정: Origin
    헤더 검사 미들웨어(Origin 없음/localhost/브라우저 확장 스킴만 허용, 그 외 403).

15. **`wiki lint`가 vault를 변조한다.** lint 경로가 scaffold를 호출해 "report-only"
    원칙을 스스로 어긴다. serve도 아무 cwd에 조용히 폴더 트리를 만든다. 결정:
    scaffold는 `init` 전용. serve/lint는 vault로 안 보이는 디렉터리(06_Metadata 없음)면
    안내 메시지와 함께 종료(비정상 종료 코드).

16. **경로 오류가 500으로 샌다.** 없는 claim 승인, URL fetch 실패 등. 결정: 예외 핸들러
    (FileNotFoundError 404, PermissionError 403, ValueError 400, capture fetch 실패 502).

17. **`wiki search`가 vault 위치 인자를 안 받고, unknown command가 exit 0.** 결정:
    search도 선행 디렉터리 인자를 vault로 해석, unknown command는 exit 1.

### E. 모델/유지보수

18. **모델명 7곳 하드코딩(`claude-opus-4-8`).** 결정: `$WIKI_MODEL` 환경변수(기본값
    `claude-opus-5`) 한 곳(subagents.py)에서 읽고 agent.py가 가져다 쓴다.

19. **생성 텍스트의 em dash.** 인덱스/로그 줄에 `—`를 쓴다. 소유자 표기 규칙에 맞춰
    `-`로 교체(기존 vault 파일은 인덱스 재작성 시 자연 갱신).

## 하지 않는 것

- 형태소 분석기(kiwipiepy 등) 도입: 2-gram으로 충분한지 실사용 후 판단.
- 벡터 DB/ANN: vault 규모(수백 문서)에서 numpy 전수 코사인이면 충분.
- 인증 토큰: localhost 개인 도구에 Origin 검사면 위협 모델에 충분.
