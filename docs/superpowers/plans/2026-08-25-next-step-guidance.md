# Plan: 파이프라인 다음 단계 안내

Spec: `../specs/2026-08-25-next-step-guidance-design.md`

- [x] `core/pipeline.py`: `vault_state`, `next_step` (우선순위 4단계, 하나만 반환)
- [x] `tools.py`: `_with_next_step` 헬퍼, `_done`과 `list_pending`에 부착
- [x] 새 도구 `vault_next_step` (17번째), `WIKI_TOOL_NAMES` 갱신
- [x] `build_wiki_server` -> `build_wiki_tools` + `build_wiki_server`로 분리 (테스트 접근성)
- [x] `tests/test_pipeline.py` 7개, `tests/test_tools.py` 4개 (실제 핸들러 호출)
- [x] AGENTS.md / ARCHITECTURE.md 16 -> 17 도구, `core/pipeline.py` 등재
- [x] repo 루트 `CLAUDE.md`에 "다음 단계 줄을 그대로 전달한다" 규칙
