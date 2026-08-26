# Plan: 원문 그대로 담기

Spec: `../specs/2026-08-27-verbatim-capture-design.md`

- [x] `core/sources.py`: `update_source_raw(vault, source_id, content, reason)` (source frontmatter에 updated가 없어 date_str은 안 받는다)
- [x] `core/claims.py`: `update_claim_quote(vault, claim_id, quote, reason, date_str)`,
      `unblockquote` 헬퍼 (`blockquote`의 역)
- [x] `core/lint.py`: `quote_not_in_source` 규칙 (blockquote 벗기고, 공백 접고, `(...)` 생략 인정)
- [x] `tools.py`: `create_source`에 `content_path` 추가 (content와 배타), 새 도구
      `update_source_raw` / `update_claim_quote`, `WIKI_TOOL_NAMES` 17 -> 19
- [x] 테스트: `test_sources.py`, `test_claims.py`, `test_lint.py`, `test_tools.py`
- [x] AGENTS.md / ARCHITECTURE.md 17 -> 19 도구
- [x] `prompts/ingest.md`: 큰 클립은 `content_path`를 쓰라는 한 줄
- [x] `uv run ruff check` clean, `uv run pytest` green

## 코드 반영 후 (vault 작업, MCP 서버 재시작 필요)

- [ ] source 4개 Raw 본문을 원본(커밋 c8a24c8) 기준으로 재작성해 `update_source_raw`로 교체
- [ ] `wiki lint`로 `quote_not_in_source`가 몇 건인지 확인
- [ ] 남은 claim 인용문을 `update_claim_quote`로 교정, lint 0건 확인

## 검토표

- [x] `tools/review_template.html` + `tools/render_review.py`: source 하나의 pending claim을
      원문과 나란히 놓고 판정하는 HTML을 찍는다. 내용은 vault 파일에서만 읽고, 표시(marks)도
      전부 기계로 뽑는다 (인용문 미일치, 인용문 없음/짧음, 제 문장에는 있는데 인용문에는 없는
      숫자, attributed 제안인데 speaker 없음). 사람이나 모델이 claim 문장을 다시 옮겨 적는
      단계가 없다.
- [x] 2026-08-27 실제 vault 4개 source에 돌려 72건 중 7건에 숫자 표시가 붙는 것을 확인
