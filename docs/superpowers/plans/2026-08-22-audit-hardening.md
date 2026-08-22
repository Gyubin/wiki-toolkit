# Audit hardening plan (2026-08-22)

스펙: `../specs/2026-08-22-audit-hardening-design.md`. 근거 데이터:
감사 워크플로우 확정 발견 40건(세션 스크래치패드 `audit-findings.json`, 워크플로우
wf_fa9a2fa3-337 저널). 각 배치는 실패 테스트 -> 구현 -> pytest 녹색 -> 커밋 순서.

## Batch 1: core 무결성

- [x] schema.parse_doc 줄 앵커 파싱 (값 안의 `---` 안전, 닫는 펜스 없으면 frontmatter 없음 취급)
- [x] core/ids.py `next_seq` (해당 날짜 최대 seq + 1, 재귀 스캔) 신설, tools.py와 app.py의 개수 기반 `_next_seq` 제거
- [x] create_source/create_claim/create_learning_item/create_session_summary/create_decision 기존 파일 덮어쓰기 거부
- [x] set_claim_status에서 verified 거부 (verified는 promote_claim 단일 경로)
- [x] normalize_key 한글 토큰 포함 + 빈 키 원문 폴백
- [x] wiki._slug와 projects.project_slug 한글 허용, create_wiki_page 덮어쓰기 거부(overwrite=True 예외)
- [x] index.update_index 정확 매칭 (`- [id]` 접두)
- [x] learning: next_review 값 str 강제(YAML date 파싱 대비), 알 수 없는 level 방어
- [x] 생성 텍스트의 em dash 제거 (index/log/lint 출력)

## Batch 2: lint 확장 (여전히 report-only)

- [x] 파싱 실패 파일 보고 (조용한 skip 제거)
- [x] 중복 id 검사
- [x] index 항목 -> 실제 파일 정합성 검사
- [x] Inbox frontmatter 없는 파일 info 보고 (Web Clipper 유입물 가시화)

## Batch 3: 검색

- [x] tokenize: ascii 단어 + 한글 2-gram
- [x] e5 접두사 (문서 `passage: `, 질의 `query: `)
- [x] numpy 코사인 (pyproject에 numpy 명시)
- [x] 임베딩 디스크 캐시 (모델명 + 텍스트 해시 키, `$WIKI_EMBED_CACHE` 아래)
- [x] vault 지문(md 수 + 최대 mtime) 기반 인덱스 무효화, tools/app 공용
- [x] vault 루트 *.md 비재귀 포함 (설계 문서 검색 가능하게)
- [x] 임베딩 모델 env `WIKI_EMBED_MODEL`. 기본값은 e5-large 유지: fastembed 지원 목록에
      multilingual e5는 large뿐이라(실측) 원 계획의 e5-small 전환 불가. 비용은 벡터
      캐시로 흡수. fastembed `>=0.8,<0.9` 핀, mean pooling 정보성 경고 억제(e5는 원래 mean)
- [x] CLI search 선행 디렉터리 인자를 vault로 해석

## Batch 4: 도구/권한/에이전트

- [x] 선택 인자 있는 도구를 완전한 JSON 스키마로 (evidence_refs, source_refs, url, k 등)
- [x] promote_claim 래퍼에서 approved_by_human 차단
- [x] permissions: set_claim_status도 게이트, approved_by_human 입력 제거
- [x] allowed_tools에서 promote_claim/set_claim_status 제외 (can_use_tool 활성화)
- [x] update_wiki_page 도구 노출
- [x] `WIKI_MODEL` env (기본 claude-opus-5), 하드코딩 7곳 제거
- [x] search_wiki 도구가 지문 캐시 사용

## Batch 5: 앱/웹

- [x] 지속 WikiSession + asyncio.Lock + /chat/reset
- [x] SSE: 서버 json.dumps 이벤트, 클라이언트 stream 디코드 + 버퍼 + 공용 파서
- [x] Origin 검사 미들웨어 (없음/localhost/확장 스킴 허용)
- [x] 예외 핸들러: FileNotFoundError 404, PermissionError 403, ValueError 400, capture fetch 실패 502
- [x] 웹 UI innerHTML 이스케이프

## Batch 6: CLI

- [x] scaffold는 init 전용; serve/lint는 vault 아니면 안내 후 종료
- [x] unknown command와 lint error 발견 시 비 0 종료 코드

## Batch 7: 테스트/프로세스/문서

- [x] test_architecture 전 레이어 매트릭스 강제
- [x] 학습 간격 사다리와 레벨 캡 테스트
- [x] scaffold: 00_Inbox/coding-agent-sessions, 00_Inbox/unprocessed, 템플릿 seed 5종, .gitkeep
- [x] pre-commit 훅 재설치 (이사 후 깨진 경로)
- [x] ARCHITECTURE.md, AGENTS.md, web-clipper-setup.md 갱신

## Batch 8: vault 정리 (별도 repo)

- [x] 깨진 index 항목 제거 (유실 claim 3건, session 1건)
- [x] 실패 캡처(source-20260607-001, JS 차단 페이지) 제거
- [x] scaffold 재실행으로 폴더/템플릿/.gitkeep 반영, 커밋

## 리뷰 라운드 (구현 후 적대적 리뷰 워크플로우가 확정한 추가 수정)

- [x] permission_mode acceptEdits -> default (acceptEdits는 Write/Edit를 콜백 전에 자동 승인)
- [x] can_use_tool에서 메인 에이전트(agent_id 없음)의 Bash/Write/Edit 명시적 거부
- [x] RRF 동점을 competition ranking으로 (파일 순서가 순위를 지배하던 결함)
- [x] commit_vault 경로 한정 스테이징 (사용자 수동 편집 보호)
- [x] lint duplicate_id의 프로젝트별 session/decision id 스코프 인식
- [x] 닫는 펜스 없는 파일: lint가 unparseable로 보고, list_pending/find_similar는 생존
- [x] VecCache 오염 자가 복구(로드 검증, 차원 불일치 전체 재임베딩, 원자적 저장)
- [x] vault_fingerprint의 stat 예외 허용 (깨진 심링크)
- [x] 전 문서 빈 토큰 시 BM25 ZeroDivision 방지
- [x] 빈 vault에서 임베딩 모델 로드 생략
- [x] 한글 unigram+bigram 토큰화 (한 글자 질의 매치)
- [x] update_wiki_page를 03_Resources로 한정 (클레임 status 우회 차단)
- [x] Host 헤더 검사 (DNS 리바인딩)
- [x] /capture 봇월/빈 페이지 저장 거부
- [x] SSE 클라이언트 끊김 시 세션 폐기 (턴 중간 상태 재사용 방지)
- [x] search_wiki 임베딩을 스레드로 (이벤트 루프 정지 방지)
- [x] verify 서브에이전트에서 Bash 제거 (주입 방어), ingest에 클리퍼 정규화 단계
- [x] learning record_review의 level 키 부재 방어
- [x] lint dangling_ref 검사 (id 모양 참조의 실존 확인)
