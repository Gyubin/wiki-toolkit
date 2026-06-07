# wiki-lint — Design (Spec)

> 상태: 합의 완료(brainstorming), 구현 계획 대기
> 날짜: 2026-06-07
> 기반: phase 1 + wrap-feature 구현 완료. 설계 §9 `/wiki-lint`, D5(탐지 자동·해소 사람).

## Context

vault가 커지면 claim status/폴더 불일치, 출처 없는 claim, 중복, orphan 위키, 낡은(stale) 문서,
모순이 쌓인다. `wiki-lint`는 이를 **보고**해 사람이 정리하도록 돕는 정기 위생 점검 도구다.
**자동 수정하지 않는다**(D5: 탐지는 자동, 해소는 사람). 해소는 기존 Verify 탭/`set_claim_status`로.

## Goals (v1)

1. **결정론적 체크**(LLM 무관, 즉시): `core/lint.py::run_checks`.
2. **LLM 모순 패스**(읽기 전용 `lint` 서브에이전트): claim 간 모순 쌍 보고.
3. 웹 **Lint 탭** + `GET /lint`(결정론적) + `POST /lint/contradictions`(SSE) + CLI `uv run wiki lint`.

## Non-goals (v1)

- 자동 수정/일괄 정리(보고만). 모순 외 의미적 stale 추론(파일/repo 변경 추적은 review_after 날짜로만).
- 시맨틱 검색(다음 phase, 설계상 1000문서 전 불필요).

## 기술/일관성

phase 1 스택 그대로. "무결성/판정은 `core/` 순수 함수가 결정론적으로, 추론은 서브에이전트가" 패턴 유지.
결정론적 lint는 LLM·CLI 의존 없이 동작; 모순 패스만 `WikiSession`(Claude CLI) 사용.

## 결정론적 체크 — `core/lint.py`

`run_checks(vault: Path, today_str: str) -> list[dict]`. 각 finding = `{"check","severity","ref","message"}`.
`claims._STATUS_DIR`(status→dir)와 `claims.normalize_key`를 재사용.

| check | severity | 판정 |
|---|---|---|
| `status_folder_mismatch` | error | `10_Claims/<dir>/claim-*.md`의 frontmatter `status`에 대해 `_STATUS_DIR[status] != <dir>` |
| `missing_source_refs` | warning | claim의 `source_refs`가 빈 리스트 |
| `verified_without_evidence` | warning | `status == "verified"` 이고 `evidence_refs` 빔 |
| `duplicate_claim` | warning | `normalize_key(claim, speaker)` 동일한 claim이 2개 이상(그룹당 finding 1개, ref=ids) |
| `orphan_wiki` | info | `03_Resources/**/*.md` 위키인데 `claim_refs` 빔 |
| `stale` | warning | 임의 `*.md` frontmatter에 `review_after`가 있고 `review_after <= today_str` |

순회 범위: claims는 `10_Claims/**`, 위키는 `03_Resources/**`, stale은 vault 전체 `*.md`(frontmatter 파싱 실패는 무시).
정렬: severity(error>warning>info) 후 check 이름.

## LLM 모순 패스 — `lint` 서브에이전트 (읽기 전용)

`prompts/lint.md`: 10_Claims의 pending/verified claim을 읽어 **서로 모순되는 claim 쌍**을 찾고,
각 쌍을 `[id-a] vs [id-b] — 무엇이 충돌하는지` 형식으로 보고. **수정 금지**(set/promote 호출 안 함).
해소는 사람이 Verify에서. tools = `Read`, `Grep`, `Glob`만(쓰기 도구 없음). model `claude-opus-4-8`.

## 웹 / 엔트리

- `GET /lint` → `core.lint.run_checks(vault, today)` 결과 JSON(LLM 무관, 즉시).
- `POST /lint/contradictions` (SSE) → "lint 서브에이전트로 모순을 점검하라"는 프롬프트를 `WikiSession`으로 스트리밍.
- **Lint 탭**: 버튼 "결정론적 점검"(findings 테이블, severity별 색/그룹) + "모순 검사(LLM)"(스트림 로그).
- `__main__.py`에 `lint` 커맨드: `run_checks` 출력(사람이 읽는 텍스트).

## 프로젝트 구조 (추가/수정)

```
wiki_agent/
  core/lint.py        # NEW: run_checks
  prompts/lint.md     # NEW
  subagents.py        # MODIFY: add `lint` (Read/Grep/Glob only)
  app.py              # MODIFY: GET /lint + POST /lint/contradictions
  web/index.html      # MODIFY: Lint 탭
  __main__.py         # MODIFY: `lint` 커맨드
tests/
  test_lint.py        # NEW
  test_app.py         # MODIFY (/lint, /lint/contradictions 라우트)
  test_subagents.py   # MODIFY (lint 포함; agent set 갱신)
  test_agent.py       # MODIFY (build_options agents set에 lint 포함)
```
`agent.py` allowed_tools 변경 불필요(lint 서브에이전트는 이미 허용된 Read/Grep/Glob만 사용).

## 테스트 전략

- `core/lint.py`: `vault` fixture에 의도적으로 (a) verified 폴더에 status=unverified인 claim(폴더/상태 불일치), (b) source_refs 빈 claim, (c) evidence 없는 verified claim, (d) 동일 normalize_key claim 2개, (e) claim_refs 빈 위키, (f) `review_after`가 과거인 문서를 심고, `run_checks`가 각 check를 정확히 1건 이상 잡고 severity가 맞는지 단위 테스트.
- `/lint`·`/lint/contradictions` 라우트 등록 + 앱 부팅 스모크(LLM 미경유, TestClient로 GET /lint가 200).
- `test_subagents`/`test_agent`의 agent set 단언에 `lint` 추가.
- 모순 LLM 패스는 라이브 수동 검증.

## 검증(완료 기준)

전체 pytest 그린. `uv run wiki lint` → 심어둔 문제들이 출력. `uv run wiki serve` → Lint 탭에서
"결정론적 점검"이 severity별로 findings를 보여주고, "모순 검사(LLM)"가 모순 쌍을 스트리밍.
