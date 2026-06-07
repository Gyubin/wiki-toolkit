# Harness Engineering 구조 적용 — Design (Spec)

> 상태: 합의 완료(brainstorming), 구현 계획 대기
> 날짜: 2026-06-07
> 참고: [OpenAI Harness engineering](https://openai.com/index/harness-engineering/), [5원칙 요약](https://tonylee.im/en/blog/openai-harness-engineering-five-principles-codex/), [4 pillars](https://milvus.io/blog/harness-engineering-ai-agents.md)

## Context

OpenAI는 Codex 에이전트로 대규모 코드베이스를 만들며 "harness engineering"(에이전트의 실행 환경을
설계하는 규율)을 정립했다. 핵심 원칙: 구조화된 실행(research→plan→execute→verify), "에이전트가 못 보면
존재하지 않는다"(레포에 결정/계획 기록), agent specialization, retrieval integration, 그리고 **mechanical
enforcement over documentation**(규칙을 문서가 아니라 린터/테스트로 강제), "map not manual"(ARCHITECTURE.md
코드 지도).

우리 wiki-agent는 이미 다수를 충족한다: 구조화된 실행(brainstorm→spec→plan→TDD→verify), ExecPlans
(`docs/superpowers/`), 서브에이전트(specialization), 하이브리드 검색(retrieval), core 게이트 함수(데이터 무결성의
기계적 강제). **빠진 것**은 (1) 코드 지도, (2) 에이전트용 golden principles, (3) **코드 레이어의 기계적 강제**다.
이 spec은 그 3조각을 추가해 미래 에이전트의 harness를 완성한다.

## Goals

1. **`tests/test_architecture.py`** — 레이어 의존 방향을 AST로 검사해 위반 시 실패하는 기계적 lint(+ 체커가 실제 위반을 잡는지 자가 테스트).
2. **`ARCHITECTURE.md`** — 코드 지도(레이어·각 폴더 책임·"여기엔 무엇이 없다").
3. **`AGENTS.md`** — 이 레포를 고치는 에이전트용 golden principles(기계적·의견적 규칙).

## Non-goals

- 새 런타임 기능 없음(검색/관찰성 등은 이미 있거나 별도). 기존 모듈 리팩터링 없음(현재 레이어는 이미 준수 중).
- CI 파이프라인 구성(테스트는 `uv run pytest`로 실행; CI 연결은 사용자 환경 몫).

## 레이어 모델 (강제 대상)

의존은 아래→위로만 흐른다(위가 아래를 import). 현재 코드는 이미 준수.

```
L0  schema.py                      (stdlib + yaml 만; wiki_agent.* import 금지)
L1  core/*  (sources, claims, wiki, learning, index, scaffold, git, projects, lint, search)
            → schema + core/* + 소형 외부libs(yaml, markdownify, rank_bm25, fastembed, subprocess) 만
            → claude_agent_sdk / fastapi / uvicorn / 형제 상위모듈(tools·agent·app·subagents·permissions) import 금지
L2  tools.py, permissions.py       (claude_agent_sdk + core + schema)
L3  subagents.py                   (claude_agent_sdk + tools)
L4  agent.py                       (claude_agent_sdk + tools + subagents + permissions + schema)
L5  app.py, __main__.py            (fastapi/uvicorn + core + agent + schema)
```

강제 규칙(기계적):
- **core 순수성**: `wiki_agent/core/**.py`는 `{claude_agent_sdk, fastapi, uvicorn, starlette}` 및
  형제 오케스트레이션 모듈(`wiki_agent.{tools,agent,app,subagents,permissions,__main__}`)을 import하지 않는다. (`schema`·`wiki_agent.core.*`는 허용)
- **schema 기반성**: `wiki_agent/schema.py`는 어떤 `wiki_agent.*`도 import하지 않는다.
- **웹 격리**: `app.py` 외의 모듈은 `fastapi`/`starlette`를 import하지 않는다.

## test_architecture.py 설계

- 헬퍼(테스트 파일 내): `referenced_modules(source, pkg) -> set[str]` — `ast`로 `Import`/`ImportFrom`을
  파싱, 상대 import를 파일의 패키지 기준 절대 모듈 문자열로 resolve해 반환. `core_violations(source, pkg) -> list[str]`.
- 테스트:
  - `test_core_is_pure`: 실제 `wiki_agent/core/**.py` 전부 스캔 → 위반 0 (현재 통과; 미래 드리프트 가드).
  - `test_schema_is_base`: `schema.py`가 `wiki_agent.*` 미참조.
  - `test_only_app_imports_web`: `app.py` 외 모듈은 fastapi/starlette 미참조.
  - `test_checker_catches_violation`: 합성 소스(`from claude_agent_sdk import x`)를 `core_violations`에 넣어 **위반으로 잡히는지** 단언 — lint가 vacuous하지 않음을 증명.

## ARCHITECTURE.md 설계 (map, not manual)

간결한 코드 지도: (a) 한 줄 목적, (b) 위 레이어 다이어그램, (c) 폴더/파일별 책임 1줄, (d) **"무엇이 없는가"**
(core엔 LLM/웹 의존 없음; lint는 vault가 아니라 코드 레이어를 검사; 영속 상태는 vault 파일 + git이며 대화 히스토리가 아님),
(e) "research→plan→execute→verify는 `docs/superpowers/`의 spec/plan(ExecPlans)으로 수행" 포인터.

## AGENTS.md 설계 (golden principles)

이 레포를 수정하는 에이전트용 기계적 규칙:
1. 환경: `uv`(`uv run pytest`, `uv run wiki serve|init|lint|search`). 런타임에 Claude Code CLI 필요(에이전트 경로).
2. 무결성: 구조적 쓰기(claim/source/wiki/session/decision/learning, index/log)는 **반드시 `core/` 함수/`@tool` 경유**, 손수 마크다운 쓰기 금지. enum/frontmatter/ID는 `schema.py`가 단일 출처.
3. 게이트: `verified`는 사람 승인 또는 evidence 필요(`promote_claim`/`can_use_tool`). work/confidential은 거부가 아니라 `01_Projects/<repo>/` 라우팅 + `sensitivity` 태그. lint는 보고만(수정 금지).
4. 레이어: 위 의존 방향 준수 — `core/`는 순수(LLM/웹 의존 없음). 위반은 `test_architecture.py`가 잡는다.
5. 워크플로우: 변경은 spec→plan(`docs/superpowers/`)→TDD→`uv run pytest` 그린 후 커밋. 커밋은 태스크가 만진 파일만(`git add -A` 금지; 레포에 무관 문서 있음).
6. 보안: 통합 vault엔 work 콘텐츠가 섞임 — 개인/공개 원격에 push 금지.

## 구조 (추가)

```
ARCHITECTURE.md          # NEW
AGENTS.md                # NEW
tests/test_architecture.py  # NEW
```
기존 코드 변경 없음(현재 레이어는 이미 준수).

## 테스트 / 검증

`uv run pytest` 그린(새 아키텍처 테스트 포함, 현재 코드에서 통과). `test_checker_catches_violation`이 합성
위반을 잡는 것으로 lint의 실효성 증명. ARCHITECTURE.md/AGENTS.md는 사람이 읽어 정확성 확인.

---

## Follow-up (2026-06-08): 빠른 피드백 루프 + vault 분리

위 3조각 이후 OpenAI 글 대비 남은 두 갭을 보완했다.

1. **빠른 피드백 티어** — 기존엔 `uv run pytest`(가장 느린 티어)만 존재. 추가:
   - `pyproject.toml`에 `[tool.ruff]`(select `E,F,I,B,UP,S`, line-length 100) — project-memory가 주장하던 `lint=ruff`를 실제로 배선.
   - `.pre-commit-config.yaml` — commit 시 `ruff check --fix`(초 단위), push 시 `pytest`(분 단위). 훅은 `uv run`으로 dev-group 버전과 동일 실행(드리프트 없음).
   - 의도적 보안 예외(`core/git.py`의 git subprocess = S603/S607, `core/search.py`의 best-effort 인덱싱 = S112)는 이유를 단 `# noqa`로 문서화.
   - **포맷터(ruff-format)는 의도적으로 미적용** — 손으로 정렬한 컴팩트 스타일(예: `subagents.py` 도구 리스트)을 보존하기 위해 lint만 강제.

2. **vault ↔ code 분리** — 기존엔 한 디렉터리에 vault(untracked·non-gitignored)와 코드가 공존 → `git add -A` 한 번이면 work 콘텐츠 유출 위험, vault엔 버전 이력/백업 없음. 변경:
   - 코드는 이미 vault-path 파라미터화(`__main__.py`). `resolve_vault`(explicit > `$WIKI_VAULT` > cwd)로 통일하고 `search`가 cwd를 하드코딩하던 버그 수정(`tests/test_cli.py`로 가드).
   - vault 콘텐츠는 레포 밖 **별도 private git 레포**(`$WIKI_VAULT`)로 이동 → 코드 레포는 code-only·게시 가능, vault는 독립 이력/백업 확보.
   - `.gitignore`에 vault 디렉터리(`00_Inbox`…`30_Learning`, `.obsidian`, `.omc`) 추가(레포 내 dev `wiki init`가 vault를 stage하지 못하게 하는 안전장치).

### 의도적으로 보류한 것 (designed for obsolescence)
- **Claude Code 전용 훅**(`.claude/settings.json`의 PostToolUse `ruff --fix`, Stop=pytest 게이트)은 검토 후 보류. pre-commit/pre-push로 동일 보장을 도구-중립적으로 확보했고, CC 종속을 늘리지 않기 위함. 모델/도구 변화 시 재검토.
- **CI**는 여전히 non-goal(사용자 환경 몫); pre-push pytest가 로컬 대체.
