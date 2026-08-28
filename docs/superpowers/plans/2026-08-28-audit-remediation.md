# 2026-08 전체 감사 수습 (Plan)

> spec: specs/2026-08-28-audit-remediation-design.md

TDD 순서. 각 단계는 실패하는 테스트를 먼저 추가하고 구현으로 통과시킨다.
전 단계 공통: `uv run pytest`, `uv run ruff check`.

1. **schema**: `validate_doc_id(doc_id, prefix)`와 `ID_SHAPED` 추가. lint의 로컬 정규식을
   schema 것으로 교체.
2. **claims**: `has_written_evidence` (게이트와 lint 공용), `_find_file` id 검증 + 에러
   메시지 + 고정 순회, `list_pending` status 필터, `create_claim` sensitivity 검증.
3. **sources**: `find_source` id 검증 + 에러 메시지, `triage_record` 존재 확인,
   `max_sensitivity` 추가.
4. **learning**: `_find` id 검증 + 에러 메시지.
5. **index**: `update_index` 개행 접기.
6. **wiki**: `update_wiki_page(date_str=...)`로 `updated` 갱신. 본문 보존 계약 테스트 추가.
7. **git**: `commit_vault`의 commit에 pathspec. 스테이징 미침범 테스트.
8. **pipeline**: `_inbox_scan`(ingest 대기 vs 삭제 대기, 깨진 클립 포함),
   `_claim_statuses`(status 기준 집계), `citable_unlinked`, next_step 메시지와 순서 테스트.
9. **lint**: `verified_without_evidence` 판정 교체, `inbox_ingested_leftover` 분류.
10. **search**: `EmbeddingUnavailable`, 입력 절단, 400 배치 소생, 캐시 파일명에 dim,
    `SearchIndex.degraded`, IndexCache BM25 강등, pre-ingest 원격 차단.
11. **tools**: create_source가 id 반환, create_claim sensitivity 상속, triage 반환 상세,
    diff 절단 표시, 커밋 실패 경고, search_wiki 강등 경고, vault_next_step 표시 갱신,
    git vault 자동 커밋 테스트.
12. **__main__**: search의 EmbeddingUnavailable 강등 (설정 오류는 기존대로 exit 2).
13. **scaffold**: wiki-page 템플릿을 wiki-page.md 계약으로 교체.
14. **prompts와 문서**: verify.md, lint.md, answer.md, ingest.md, web-clipper-setup.md,
    .env.example, README, ARCHITECTURE, AGENTS 갱신.
15. **테스트 하네스**: conftest의 `WIKI_ENV_FILE` 격리, 아키텍처 테스트의 모듈 전수 분류.
