# ARCHITECTURE — wiki-agents

> A map, not a manual. Structural boundaries that rarely change, and what does **not** exist where.
> For the "why" of each feature, read the ExecPlans in `docs/superpowers/specs/` and `plans/`.

A local toolkit that turns raw clips and coding sessions into source-linked knowledge and learning
material in one Markdown vault. The vault on disk is the product; Obsidian reads it; this code writes
it. **The vault lives outside this repo** (a separate private directory at `$WIKI_VAULT`); this repo
is code only. Every entry point resolves the vault path via `resolve_vault` (`__main__.py`):
explicit arg > `$WIKI_VAULT` > cwd.

**여기에 에이전트는 없다.** 이름은 `wiki-agents`지만 이 repo가 하는 일은 vault 로직과 그것을 MCP
도구로 내보내는 것까지다. 에이전트는 그 도구를 물고 있는 Claude Code다. 웹 앱과 SDK 에이전트
계층은 2026-08-25에 지웠다 (아래 "지운 것" 절).

## Layers (imports flow upward only — a higher layer may import a lower one, never the reverse)

```
L0  schema.py          enums, IDs, frontmatter render/parse - SINGLE SOURCE OF TRUTH
L1  core/*             pure, deterministic vault logic (no LLM, no web)
      sources  claims  wiki  learning  index  ids  scaffold  git  projects  lint  search
      pipeline (다음 단계 계산)
L2  tools.py           wraps core/* as MCP @tools (mcp__wiki__*, 17 tools);
                       write tools auto-commit the vault (audit trail)
L3  __main__.py        CLI: `uv run wiki init|mcp|lint|search`
                       (mcp = 도구 세트를 stdio MCP로 노출, Claude Code 등록용)
```

The dependency direction above is **mechanically enforced** by `tests/test_architecture.py` — a
violation fails the test, not a code review.

## Module responsibilities (one line each)

- `schema.py` — `CLAIM_TYPES`/`CLAIM_STATUSES`/`SENSITIVITIES`/`WIKI_PAGE_TYPES`/`LEARNING_LEVELS`, `make_id`, `render_doc`/`parse_doc`, validators.
- `core/ids.py` — next_seq: 해당 날짜 최대 시퀀스 + 1 (파일 개수 아님; ID 재사용 방지).
- `core/scaffold.py` — create vault folder tree + seed index/log/template files (+.gitkeep). init 전용.
- `core/index.py` — append-only logs, upsert-by-id index lines under `06_Metadata/`.
- `core/sources.py` — capture raw clips (Inbox) with sensitivity tag; html→markdown; triage records.
  봇 차단 페이지(`_BOTWALL_MARKERS`)는 `create_source`가 거부한다.
- `core/claims.py` — claim lifecycle: create (always `unverified`), dedup key, `promote_claim`
  (`verified`는 `evidence_refs`가 유일한 통로), status changes.
- `core/wiki.py` — human-readable wiki pages with enforced frontmatter + index entry.
- `core/learning.py` — learning items + spaced-repetition review driver.
- `core/git.py` — read-only git session collection for wrap + commit_vault (감사 추적용 자동 커밋).
- `core/projects.py` — `01_Projects/<repo>/` session summaries and ADRs.
- `core/lint.py` — deterministic, report-only vault hygiene checks.
- `core/pipeline.py` — `vault_state`/`next_step`: 파이프라인에서 사람을 기다리는 지점 하나를 계산.
  ingest 대기 > pending claim > wiki page 미승격 verified > 복습 도래 순으로 하나만 돌려준다.
- `core/search.py` — hybrid BM25(한글 2-gram) + embedding search, RRF fusion. 임베딩은 기본이 OpenAI
  Embeddings API(`text-embedding-3-large`)이고, `WIKI_EMBED_PROVIDER=local`이면 fastembed로 로컬 실행(e5 접두사);
  injectable embedder; 벡터 디스크 캐시 + vault 지문 기반 인덱스 무효화.
  env: `WIKI_EMBED_PROVIDER`(openai|local, 기본 openai), `OPENAI_API_KEY`, `WIKI_EMBED_MODEL`,
  `WIKI_EMBED_DIM`, `WIKI_OPENAI_BASE_URL`, `WIKI_EMBED_SEND_SENSITIVE`, `WIKI_EMBED_CACHE`.
- `tools.py` — `@tool` wrappers + `build_wiki_tools`(도구 목록) / `build_wiki_server`(MCP 래핑);
  `WIKI_TOOL_NAMES`. 쓰기 도구와 `list_pending`의 반환에 `pipeline.next_step`을 덧붙여
  사람이 다음 단계를 외우지 않아도 되게 한다 (프롬프트가 아니라 데이터 경로).
- `__main__.py` — process entry. `load_env_file()`이 `$WIKI_ENV_FILE`(기본 repo 루트 `.env`)을 읽어
  셸에 없는 값만 채운다 (MCP 서버는 셸 rc를 안 거칠 수 있다). `.env`는 gitignore, 형식은 `.env.example` 참조.
- `prompts/*.md`: **코드가 읽지 않는다.** Claude Code가 직접 읽는 절차서다 (아래 참조).

## `prompts/`는 코드가 아니라 계약서다

예전에는 `subagents.py`가 이 파일들을 서브에이전트 system prompt로 자동 부착했다. 그 계층을
지운 지금 **아무도 붙여주지 않는다.** 도구만 열려 있고 절차는 안 열려 있다.

- `ingest.md`: 클립 하나를 triage하고 claim으로 쪼개는 계약. 이게 계약의 원본이다.
- `verify.md`: pending claim 검토. `verified`는 `evidence_refs` 필수.
- `answer.md` / `learning.md` / `wrap.md` / `lint.md`: 각 작업 절차.
- `system.md`: 원칙 모음. vault 작업 전에 읽는다.

읽지 않으면 triage를 건너뛰거나, claim마다 돌아야 할 `find_similar_claim`을 생략하거나, claim을
덜 쪼갠다. 이 실패는 조용해서 lint도 사람도 나중에 못 잡는다.

## What is NOT here (constraints by absence)

- **`core/` has no LLM or web dependency.** No `claude_agent_sdk`, `fastapi`, `uvicorn`. Core is pure and unit-tested without a model or server. (Enforced.)
- **`schema.py` imports nothing from `wiki_agents`.** It is the base. (Enforced.)
- **어떤 모듈도 웹 프레임워크를 import하지 않는다.** (Enforced. 예전에는 `app.py`만 예외였다.)
- **`verified`로 가는 우회로가 없다.** `evidence_refs` 하나뿐이다. 사람 판단으로 올릴 때도 그 판단을
  문장으로 `evidence_refs`에 적는다.
- **게이트를 강제하는 런타임 코드가 없다.** `permissions.py`의 `can_use_tool`은 SDK 에이전트 전용이라
  stdio MCP 경로에서는 한 번도 불린 적이 없었다. 지금 Claude Code는 Write/Edit/Bash를 다 가지고 있고
  claim 파일을 손으로 고칠 수 있다. 규칙이지 코드가 아니다.
- **No second "work vault."** Work/confidential content lives in the same vault under `01_Projects/<repo>/`, distinguished by a `sensitivity` frontmatter tag — not refused.
- **임베딩은 기본적으로 외부 API를 탄다 (2026-08-25 변경).** 문서 본문이 OpenAI Embeddings API로 나간다.
  `sensitivity: work`도 보낸다(사용자 결정). `confidential`만 안 보내고 BM25(로컬)로만 검색된다
  (`WIKI_EMBED_SEND_SENSITIVE=1`로 해제). 전부 로컬로 돌리려면 `WIKI_EMBED_PROVIDER=local`.
- **No conversation memory.** Durable state = vault Markdown files + git history (쓰기마다 자동 커밋).

## 지운 것 (2026-08-25, `e7387fb`)

FastAPI 웹 앱과 SDK 에이전트 계층을 지웠다. 파일은 `git show e7387fb^:<경로>`로 그대로 돌아온다.
**여기에 적어두는 이유는 파일이 아니라 "그런 게 있었다"는 사실이 git으로 안 돌아오기 때문이다.**

| 지운 것 | 줄 수 | 무엇이었나 |
| --- | --- | --- |
| `app.py` | 249 | FastAPI 라우트 13개: capture, claim과 review 큐, lint, search, chat, wrap |
| `web/index.html` | 174 | 탭 7개짜리 로컬 UI (Chat, Capture, Wrap, Verify, Review, Lint, Search) |
| `agent.py` | 63 | `ClaudeAgentOptions` + `WikiSession` (대화형 세션 하나) |
| `subagents.py` | 74 | `AgentDefinition` 6개 (ingest/verify/answer/learning/wrap/lint) |
| `permissions.py` | 46 | `can_use_tool` 게이트 |
| 테스트 4개 | 362 | 위 파일들의 테스트 |

**왜.** 사용자가 Claude Code(stdio MCP)에서만 쓴다. 웹 앱은 띄운 흔적이 vault git 히스토리에 없고,
2026-08-25 실사용에서 claim 18개를 Claude Code로 전부 검토했다 (attributed 12, opinion 3,
accepted_for_now 3, verified 0). 웹이 독점하던 "증거 없이 verified" 경로는 한 번도 필요하지 않았다.
안 도는 코드가 문서를 틀리게 만들고 있었다: `pipeline.next_step`이 쓰기 때마다 "웹 Verify 탭에서
승인"이라고 안내했고, `AGENTS.md`는 "main agent has no Bash/Write/Edit"라고 적고 있었는데 실제로
쓰는 경로에서는 둘 다 거짓이었다.

**같이 사라진 판단들 (여기 옮겨 적는다).** `subagents.py`의 도구 허용 목록에만 있던 것들이고
프롬프트 파일에는 안 적혀 있었다. 다시 에이전트를 짤 일이 생기면 이 세 줄부터 본다.

- **verify에는 Bash를 주지 않는다.** verify는 신뢰 불가 클립에서 나온 claim 텍스트를 다룬다.
  프롬프트 주입이 성공했을 때 실행 능력이 없어야 한다. 테스트 실행은 wrap의 몫이었다.
- **lint는 `Write`/`Edit`/`Bash`를 전부 막는다.** 읽기 전용 감사다. 모순을 찾아 보고만 하고
  해소는 사람이 한다.
- **answer는 `Write`/`Edit`를 막는다.** 답변에서 나온 통찰은 `create_claim`으로 unverified로만
  들어간다. wiki page에 직접 쓰지 않는다.

**같이 뺀 것.** `promote_claim`의 `approved_by_human`. 그 플래그를 넘기는 곳은 웹의 `/approve`
하나였고, 파일에 아무 흔적도 안 남겼다(프론트매터 키 13개 어디에도 없었다). 결과물은
`evidence_refs: []`인 verified였고 lint가 `verified_without_evidence`로 잡았다. 사람이 승인했다는
기록이 아니라 게이트를 끄는 스위치였다. 되살리려면 `core/claims.py`에 3줄이면 된다.

**같이 옮긴 것.** 봇 차단 페이지 검사(`_BOTWALL_MARKERS`)가 `app.py`의 `/capture` 라우트에만 있어서
MCP 경로로 들어오는 캡처는 안 걸렸다. `core/sources.create_source`로 옮겼다. 최소길이 200자 검사는
같이 옮기지 않고 lint의 `thin_source`(warning)로 바꿨다. 웹에서는 URL을 직접 받아올 때만 걸렸는데
MCP 경로에는 그 단계가 없고, 조건을 바꾸면 짧은 붙여넣기 메모까지 막힌다.

## Process

Changes go through `docs/superpowers/`: brainstorm → spec → plan (ExecPlans) → TDD → `uv run pytest` →
commit. If a decision isn't written down there, it doesn't exist for the next agent.
