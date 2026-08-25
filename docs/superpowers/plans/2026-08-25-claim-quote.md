# claim에 원문 인용 담기 (Plan)

Spec: `../specs/2026-08-25-claim-quote-design.md`

TDD. 실패하는 테스트를 먼저 쓰고 구현한다.

## 1. `core/claims.py` (L1)

- [x] `create_claim`에 `quote: str | None = None` 추가.
- [x] 모듈 함수 `blockquote(text) -> str`: 모든 줄 앞에 `> `를 붙이고, 빈 줄에는 `>`만 붙인다.
      빈 줄에 `> ` 대신 아무것도 안 붙이면 markdown blockquote가 거기서 끊긴다.
- [x] 본문 조립: `quote`가 있으면 `## Claim\n\n{claim}\n\n## 원문\n\n{blockquote(quote)}\n`,
      없으면 예전 그대로 `## Claim\n\n{claim}\n`.

테스트 (`tests/test_claims.py`):
- [x] quote를 주면 본문에 `## 원문`과 `> `로 시작하는 줄이 있다.
- [x] 여러 줄 + 빈 줄이 든 인용이 blockquote로 안 끊긴다 (빈 줄도 `>`로 시작).
- [x] quote 없으면 본문이 예전 문자열과 정확히 같다 (회귀 방지).
- [x] `promote_claim`으로 상태를 바꿔도 `## 원문`이 남는다.

## 2. `tools.py` (L2)

- [x] `create_claim` 도구의 optional 스키마에 `quote: _STR` 추가.
- [x] 설명 문구에 "근거가 된 원문 문단을 quote로 같이 넘긴다" 취지를 넣는다.
- [x] 핸들러에서 `args.get("quote")` 전달.

테스트 (`tests/test_tools.py`):
- [x] 핸들러에 quote를 넘기면 만들어진 파일에 `## 원문`이 있다.
- [x] MCP `tools/list`에서 `quote`가 properties에 있고 required에는 없다.

## 3. `prompts/ingest.md` (계약)

- [x] claim마다 근거가 된 원문 문단을 `quote`로 같이 넘기라고 적는다.
- [x] 원문을 요약하거나 번역해서 넣지 말고 **그대로 인용**하라고 못박는다.
      claim이 이미 정리된 한국어이므로 quote까지 정리하면 대조할 원본이 사라진다.

## 4. 문서

- [x] `ARCHITECTURE.md`의 `core/claims.py` 한 줄에 반영.
- [x] `AGENTS.md`는 안 건드린다 (게이트나 레이어가 안 바뀐다).

## 검증

- [x] `uv run pytest` 초록
- [x] `uv run ruff check` 클린
- [x] stdio MCP 왕복으로 `create_claim` 스키마 확인
- [x] 실제 vault `wiki lint` 0 finding (기존 claim 18개가 안 깨지는지)
