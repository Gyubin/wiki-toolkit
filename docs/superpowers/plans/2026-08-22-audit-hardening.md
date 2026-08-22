# Audit hardening plan (2026-08-22)

스펙: `../specs/2026-08-22-audit-hardening-design.md`. 근거 데이터:
감사 워크플로우 확정 발견 40건(세션 스크래치패드 `audit-findings.json`, 워크플로우
wf_fa9a2fa3-337 저널). 각 배치는 실패 테스트 -> 구현 -> pytest 녹색 -> 커밋 순서.

## Batch 1: core 무결성

- [ ] schema.parse_doc 줄 앵커 파싱 (값 안의 `---` 안전, 닫는 펜스 없으면 frontmatter 없음 취급)
- [ ] core/ids.py `next_seq` (해당 날짜 최대 seq + 1, 재귀 스캔) 신설, tools.py와 app.py의 개수 기반 `_next_seq` 제거
- [ ] create_source/create_claim/create_learning_item/create_session_summary/create_decision 기존 파일 덮어쓰기 거부
- [ ] set_claim_status에서 verified 거부 (verified는 promote_claim 단일 경로)
- [ ] normalize_key 한글 토큰 포함 + 빈 키 원문 폴백
- [ ] wiki._slug와 projects.project_slug 한글 허용, create_wiki_page 덮어쓰기 거부(overwrite=True 예외)
- [ ] index.update_index 정확 매칭 (`- [id]` 접두)
- [ ] learning: next_review 값 str 강제(YAML date 파싱 대비), 알 수 없는 level 방어
- [ ] 생성 텍스트의 em dash 제거 (index/log/lint 출력)

## Batch 2: lint 확장 (여전히 report-only)

- [ ] 파싱 실패 파일 보고 (조용한 skip 제거)
- [ ] 중복 id 검사
- [ ] index 항목 -> 실제 파일 정합성 검사
- [ ] Inbox frontmatter 없는 파일 info 보고 (Web Clipper 유입물 가시화)

## Batch 3: 검색

- [ ] tokenize: ascii 단어 + 한글 2-gram
- [ ] e5 접두사 (문서 `passage: `, 질의 `query: `)
- [ ] numpy 코사인 (pyproject에 numpy 명시)
- [ ] 임베딩 디스크 캐시 (모델명 + 텍스트 해시 키, `$WIKI_EMBED_CACHE` 아래)
- [ ] vault 지문(md 수 + 최대 mtime) 기반 인덱스 무효화, tools/app 공용
- [ ] vault 루트 *.md 비재귀 포함 (설계 문서 검색 가능하게)
- [ ] 임베딩 모델 env `WIKI_EMBED_MODEL`. 기본값은 e5-large 유지: fastembed 지원 목록에
      multilingual e5는 large뿐이라(실측) 원 계획의 e5-small 전환 불가. 비용은 벡터
      캐시로 흡수. fastembed `>=0.8,<0.9` 핀, mean pooling 정보성 경고 억제(e5는 원래 mean)
- [ ] CLI search 선행 디렉터리 인자를 vault로 해석

## Batch 4: 도구/권한/에이전트

- [ ] 선택 인자 있는 도구를 완전한 JSON 스키마로 (evidence_refs, source_refs, url, k 등)
- [ ] promote_claim 래퍼에서 approved_by_human 차단
- [ ] permissions: set_claim_status도 게이트, approved_by_human 입력 제거
- [ ] allowed_tools에서 promote_claim/set_claim_status 제외 (can_use_tool 활성화)
- [ ] update_wiki_page 도구 노출
- [ ] `WIKI_MODEL` env (기본 claude-opus-5), 하드코딩 7곳 제거
- [ ] search_wiki 도구가 지문 캐시 사용

## Batch 5: 앱/웹

- [ ] 지속 WikiSession + asyncio.Lock + /chat/reset
- [ ] SSE: 서버 json.dumps 이벤트, 클라이언트 stream 디코드 + 버퍼 + 공용 파서
- [ ] Origin 검사 미들웨어 (없음/localhost/확장 스킴 허용)
- [ ] 예외 핸들러: FileNotFoundError 404, PermissionError 403, ValueError 400, capture fetch 실패 502
- [ ] 웹 UI innerHTML 이스케이프

## Batch 6: CLI

- [ ] scaffold는 init 전용; serve/lint는 vault 아니면 안내 후 종료
- [ ] unknown command와 lint error 발견 시 비 0 종료 코드

## Batch 7: 테스트/프로세스/문서

- [ ] test_architecture 전 레이어 매트릭스 강제
- [ ] 학습 간격 사다리와 레벨 캡 테스트
- [ ] scaffold: 00_Inbox/coding-agent-sessions, 00_Inbox/unprocessed, 템플릿 seed 5종, .gitkeep
- [ ] pre-commit 훅 재설치 (이사 후 깨진 경로)
- [ ] ARCHITECTURE.md, AGENTS.md, web-clipper-setup.md 갱신

## Batch 8: vault 정리 (별도 repo)

- [ ] 깨진 index 항목 제거 (유실 claim 3건, session 1건)
- [ ] 실패 캡처(source-20260607-001, JS 차단 페이지) 제거
- [ ] scaffold 재실행으로 폴더/템플릿/.gitkeep 반영, 커밋
