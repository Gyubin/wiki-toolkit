# wrap-feature — Design (Spec)

> 상태: 합의 완료(brainstorming), 구현 계획 대기
> 날짜: 2026-06-07
> 기반: `2026-06-07-personal-ai-wiki-agent-design.md`(phase 1 구현 완료) + `personal-ai-wiki-learning-system-design.md` §7.2/§6.5

## Context

phase 1에서 개인 지식 epistemic 루프(ingest/verify/answer/learning)를 구현했다. North Star #2
("AI가 대신 수행한 코딩 작업을 내 개발 실력으로 흡수한다")를 완성하려면, 코딩 세션을 프로젝트
지식·결정 기록·학습 자산으로 변환하는 `wrap-feature`가 필요하다. phase 1에서 work-vault 분리
복잡도 때문에 미뤘던 기능이다.

**사용자 결정(설계 변경):** 별도 work vault를 두지 않고 **하나의 vault에서 폴더로 분리 통합 관리**한다.
프로젝트/회사 지식은 `01_Projects/<repo>/`에, 일반 지식은 `02_Areas`/`03_Resources`에 둔다.
`sensitivity`는 하드 거부 게이트가 아니라 **프론트매터 태그**로 유지(필터·공유범위·향후 자동검사용).

**주의(차단 아님):** 통합 vault에는 회사 코드/맥락이 함께 담긴다. 이 vault를 개인용·공개 원격으로
push하지 말 것. (현재 repo엔 원격 없음.)

## Goals (v1)

repo 경로 + `base..head` (+ 선택 transcript)를 입력받아 다음을 산출:
1. **세션 요약** → `01_Projects/<repo>/sessions/`
2. **Decision/ADR**(§6.5) → `01_Projects/<repo>/decisions/`
3. **Concept/Pattern 위키**(일반화·식별자 제거) → `03_Resources/`
4. **학습 산출물**(prerequisite + flashcard/quiz/mini-exercise) → `30_Learning/`

부수: phase 1의 sensitivity 하드 게이트를 "거부 → 라우팅+태그"로 완화.

## Non-goals (v1)

- 자동 transcript 캡처(붙여넣기만), repo에 파일 쓰기/커밋(읽기 전용), 멀티 repo 동시 wrap.
- 별도 work vault / submodule(사용자가 단일 vault로 결정).
- wiki-lint·시맨틱 검색(다음 phase).

## 기술/일관성

phase 1 스택 그대로(`uv`, `claude-agent-sdk` 모델 `claude-opus-4-8`, FastAPI, PyYAML, pytest).
"무결성 로직은 `core/` 순수 함수, `@tool`(에이전트)과 FastAPI 라우트가 같은 함수 공유" 패턴 유지.

## 입력 / 흐름

```
Wrap 탭(또는 Chat) → POST /wrap {repo, base, head, transcript?}
  → wrap 프롬프트 구성 → WikiSession 스트리밍
  → wrap 서브에이전트:
       collect_git_session(repo, base, head)  # diff/commits/files (읽기 전용)
       (선택) transcript 참고
       Bash로 repo의 테스트 로그/결과 확인
       → create_session_summary / create_decision / create_wiki_page / create_learning_item
```

## 새 결정론적 core (순수·테스트 가능)

### `core/git.py`
- `collect_session(repo: Path, base: str, head: str) -> dict` → `{"diff": str, "changed_files": [str], "commits": [{"sha","subject"}]}`. 읽기 전용(`git -C repo diff/log --name-only`). repo가 git이 아니거나 ref 오류면 `ValueError`.

### `core/projects.py`
- `project_slug(repo: Path) -> str` (repo basename 슬러그).
- `ensure_project(vault, repo) -> Path` → `01_Projects/<slug>/{sessions,decisions}/` 생성 + `project-index.md` 시드.
- `create_session_summary(vault, *, repo, title, body, sensitivity="work", date_str, seq) -> Path` → `01_Projects/<slug>/sessions/session-<date>-<seq>.md`, frontmatter(type: session, id, repo, sensitivity, created).
- `create_decision(vault, *, repo, title, context, decision, alternatives, consequences, sensitivity="work", date_str, seq) -> Path` → `01_Projects/<slug>/decisions/decision-<date>-<seq>.md`, §6.5 스키마.

## sensitivity 모델 변경 (phase 1 수정)

- `schema.py`: `SENSITIVITIES` 유지. (세션/결정 id prefix는 기존 `make_id`로 충분.)
- `core/sources.py::create_source`: work/confidential **거부 제거** → `sensitivity` 태그만 달아 허용(기존 `00_Inbox/raw`에 그대로, 태그로 구분).
- `permissions.py::make_can_use_tool`: create_source의 work-deny **제거**. **검증 게이트(verified)는 유지.**
- `core/claims.py::create_claim`, `core/wiki.py::create_wiki_page`: 선택 `sensitivity` 필드 추가(기본 `"personal"`), frontmatter에 기록.
- 갱신할 기존 테스트: `test_sources.py::test_create_source_refuses_work` → "허용+태그 확인"으로, `test_permissions.py::test_deny_work_source` → "허용"으로.

## 에이전트 배선

- 새 MCP `@tool`(build_wiki_server에 추가): `collect_git_session`, `create_session_summary`, `create_decision`. 기존 create_wiki_page/create_claim/create_learning_item은 `sensitivity` 인자 전달.
- `WIKI_TOOL_NAMES`에 새 3개 추가(`mcp__wiki__collect_git_session` 등).
- 새 서브에이전트 `wrap`(프롬프트=§7.2 체크리스트: 목표/변경/diff/테스트/디버깅/설계근거/갱신할 wiki/새 concept·pattern·decision/배워야 할 prerequisite/카드·퀴즈·exercise). tools = Read, Grep, Glob, Bash + 위 wiki 도구. `build_subagents()`에 추가, `agent.build_options`의 allowed_tools에 새 도구 포함.

## 웹

- `POST /wrap` (SSE): body `{repo, base, head, transcript?}` → wrap 프롬프트 문자열 구성 → `WikiSession`으로 스트리밍(기존 /chat과 동일 메커니즘). 입력 검증: repo 경로 존재 확인.
- "Wrap" 탭: repo 경로 / base / head / transcript(textarea) 폼 + 실행 버튼, 결과 스트림 표시.

## 프로젝트 구조 (추가/수정)

```
wiki_agent/
  core/
    git.py        # NEW: collect_session
    projects.py   # NEW: ensure_project, create_session_summary, create_decision
    sources.py    # MODIFY: relax work refusal -> tag
    claims.py     # MODIFY: optional sensitivity
    wiki.py       # MODIFY: optional sensitivity
  permissions.py  # MODIFY: drop create_source work-deny
  tools.py        # MODIFY: add 3 tools + sensitivity passthrough + names
  subagents.py    # MODIFY: add `wrap`
  agent.py        # MODIFY: allowed_tools includes new tools
  prompts/wrap.md # NEW
  app.py          # MODIFY: add POST /wrap
  web/index.html  # MODIFY: add Wrap tab
tests/
  test_git.py        # NEW (temp git repo fixture)
  test_projects.py   # NEW
  test_sources.py / test_permissions.py  # MODIFY (sensitivity)
  test_app.py        # MODIFY (/wrap route exists)
```

## 테스트 전략

- `core/git.py`: pytest fixture가 임시 git repo를 만들고(`git init`, 2 commits) `collect_session`이 diff·commits·changed_files를 반환하는지. 비-git 경로는 ValueError.
- `core/projects.py`: `vault` fixture 위에서 ensure_project 폴더 생성, create_session_summary/create_decision의 경로·frontmatter(특히 `sensitivity: work`, ADR 필드) 검증.
- sensitivity 변경: 갱신 테스트가 work source/claim/wiki가 허용되고 태그가 붙는지.
- `/wrap`: 라우트 등록 + 앱 부팅 스모크(LLM 미경유). 라이브 wrap은 수동 검증(실제 repo 필요).

## 검증(완료 기준)

`uv run wiki serve` → Wrap 탭에 실제 repo 경로 + 최근 `HEAD~1..HEAD` 입력 → 실행 →
`01_Projects/<repo>/sessions/`에 세션 요약, `decisions/`에 ADR(있으면), `03_Resources/`에 일반화 concept,
`30_Learning/`에 학습 카드가 생기는지 + Obsidian에서 확인. 전체 pytest 그린.
