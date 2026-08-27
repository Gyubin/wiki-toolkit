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

- [x] source 4개 Raw 본문을 `update_source_raw --content_path`로 원본(c8a24c8) 바이트와 동일하게 복구.
      곱슬따옴표 18개와 단어 1건이 되돌아왔고, source-004는 svg 2개까지 그대로 담겼다
- [x] 복구 직후 `wiki lint`가 `quote_not_in_source` 6건을 보고했다. 처음 원본 대조로 찾은 것과 같은 6건이다
- [x] 그 6건을 `update_claim_quote`로 교정해 lint 0건.
      추가로 인용 범위가 좁던 9건(009 010 022 051 054 064 070 071 072)을 넓혀
      `render_review.py`의 기계 표시가 7건에서 0건이 됐다

## 검토표

- [x] `tools/review_template.html` + `tools/render_review.py`: source 하나의 pending claim을
      원문과 나란히 놓고 판정하는 HTML을 찍는다. 내용은 vault 파일에서만 읽고, 표시(marks)도
      전부 기계로 뽑는다 (인용문 미일치, 인용문 없음/짧음, 제 문장에는 있는데 인용문에는 없는
      숫자, attributed 제안인데 speaker 없음). 사람이나 모델이 claim 문장을 다시 옮겨 적는
      단계가 없다.
- [x] 2026-08-27 실제 vault 4개 source에 돌려 72건 중 7건에 숫자 표시가 붙는 것을 확인

## 안내 숫자

- [x] `core/pipeline.py`가 `pending` 폴더 파일 수가 아니라 `status: unverified`를 센다.
      키 이름도 `pending_claims` -> `unverified_claims`로 바꿨다. 2026-08-28에 claim 72건을
      검토해 전부 승격했는데도 안내가 "pending claim 53개가 검토를 기다린다"를 계속 보고했다.

## 검토 결과 (2026-08-28)

- [x] claim 72건을 인용문과 하나씩 대조. 71건은 제안한 상태로 승격, 1건(`claim-20260827-051`)은
      원문의 조건("when the buffered token IDs differ...")을 떨어뜨려 `partially_true`로 뒀다.
- [x] `render_review.py`의 숫자 대조가 영어 숫자 단어를 읽는다 ("ten times" -> 10).
      안 그러면 멀쩡한 claim에 표시가 붙고, 표시가 흔해지면 통째로 무시된다.
- [x] 검토표에 현재 status를 표시한다.
