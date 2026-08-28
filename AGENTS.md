# AGENTS.md — golden principles for agents working in this repo

Opinionated, mechanical rules. Follow them; several are enforced by tests. Read `ARCHITECTURE.md`
for the code map and `docs/superpowers/` for the design history (ExecPlans).

## 1. Environment
- Use **`uv`**: `uv run pytest`, `uv run ruff check`, `uv run wiki init|mcp|lint|search`. Don't invoke `python`/`pip` directly.
- Only `init` scaffolds. mcp/lint/search **refuse** a directory without `06_Metadata/` (exit 2). lint exits 1 when error-severity findings exist. Bare `wiki` prints usage and exits 2 (there is no default subcommand).
- `wiki mcp <vault>` exposes the same 20 tools over stdio for Claude Code: `claude mcp add wiki -- uv run --directory <this repo> wiki mcp <vault>`.
- **The vault lives outside this repo.** Every `wiki` subcommand resolves the vault as: explicit path arg > `$WIKI_VAULT` > cwd (`resolve_vault` in `__main__.py`). Point it at your vault, e.g. `uv run wiki lint "$WIKI_VAULT"`. This repo holds **code only**.
- **검색 임베딩은 기본이 OpenAI API다.** `search`와 `search_wiki`는 `OPENAI_API_KEY`가 필요하다(없으면
  CLI는 안내 + exit 2; 네트워크 등 일시적 장애면 BM25 결과로 강등된다). 오프라인이나 전량 로컬이
  필요하면 `WIKI_EMBED_PROVIDER=local` (fastembed, 첫 실행에 가중치 2.1GB 다운로드).
  `sensitivity: confidential` 문서 본문과 ingest 전의 id 없는 Inbox 클립만 원격 임베딩에서
  제외된다(BM25로는 검색됨). 키와 설정은 셸 export 또는 repo 루트 `.env`(gitignore, `.env.example` 참조).
- **여기에 에이전트는 없다.** 웹 앱과 SDK 에이전트 계층은 2026-08-25에 지웠다 (`e7387fb`). 이 repo는 vault 로직(`core/`)과 그것을 MCP 도구로 노출하는 껍데기(`tools.py`, `__main__.py`)뿐이다. 에이전트는 이 도구들을 물고 있는 Claude Code다. 절차는 `wiki_toolkit/prompts/*.md`에 있고 **아무도 자동으로 붙여주지 않는다.** 작업 전에 해당 파일을 직접 읽는다.

## 2. Integrity — go through `core/`, never hand-write structured files
- All structured writes — sources, claims, wiki pages, sessions, ADRs, learning items, and the index/log — **must** go through a `core/` function (or its `@tool` wrapper). Do **not** hand-roll Markdown or frontmatter.
  한 가지 예외: `ingest-log.md`의 마무리 서술 줄(`ingested: ...`)은 감싸는 도구가 없어 손으로
  쓴다 (`prompts/ingest.md` 참조; 기존 로그의 서술 줄들이 이미 이 관행이다).
- `schema.py` is the **single source of truth** for enums, IDs, and frontmatter. Add a status/type there first; never inline a literal list elsewhere.

## 3. Gates and sensitivity
- A claim becomes `verified` **only via `evidence_refs`**. 우회로가 없다. 사람 판단으로 올릴 때도 그 판단을 evidence_refs에 문장으로 적는다 (예: `"2026-08-25 본인 확인: source-20260825-001 3문단과 대조"`). 근거를 문장으로 못 적겠으면 verified가 아니라 `attributed` / `opinion` / `accepted_for_now`다.
- **게이트를 지켜주는 코드는 없다.** 예전에는 `permissions.py`의 `can_use_tool`이 있었지만 그건 SDK 에이전트 전용이었고 stdio MCP 경로에서는 한 번도 불린 적이 없다 (그래서 웹과 같이 지웠다). 지금 Claude Code는 Read/Write/Edit/Bash를 다 가지고 있어서 claim 파일을 손으로 고쳐 스키마와 ID 채번과 게이트를 통째로 우회할 수 있다. **그렇게 하지 않는다**는 것이 규칙이지 코드가 아니다. 구조화된 쓰기는 전부 `mcp__wiki__*`를 거친다.
- Work/confidential content is **not refused**; it is routed to `01_Projects/<repo>/` and tagged `sensitivity`. Keep secrets/company identifiers out of `03_Resources/` and learning items.
- `lint` is **report-only** — it never modifies the vault. Resolution is the human's job.

## 4. Layering (enforced)
- Imports flow upward only: `schema → core → tools → __main__`.
- `core/` stays **pure**: no `claude_agent_sdk`, `fastapi`, `uvicorn`. `schema.py` imports nothing from `wiki_toolkit`. **어떤 모듈도 웹 프레임워크를 import하지 않는다** (예전에는 `app.py`만 예외였다; 그 예외가 없어져서 검사가 강해졌다).
- `tests/test_architecture.py` fails on any violation. Run it before assuming a refactor is safe.

## 5. Workflow
- Non-trivial change: write a spec + plan under `docs/superpowers/`, then TDD (failing test → impl → pass).
- 랭킹 로직(`core/search.py`의 tokenize, RRF, 융합 가중, iter_docs의 색인 텍스트 구성)을 바꿀 때는 질의와 정답 세트(hard-negative
  포함 10~20개)를 기존 embed_fn 주입 패턴으로 pytest 케이스에 먼저 넣고, before/after를 같은
  실행에서 잰다. 상시 벤치 인프라는 만들지 않는다 (2026-08-28 gbrain 검토 spec 참조).
- `uv run ruff check` clean and `uv run pytest` green before committing. Fast loops are wired via `.pre-commit-config.yaml` (ruff at commit, pytest at push); install once with `uv run pre-commit install --hook-type pre-commit --hook-type pre-push`.
- Commit **only the files your task touched** — `git add -A` is forbidden. End commit subjects in the conventional `feat:`/`test:`/`docs:` style already used.

## 6. Security
- This repo is **code only and may be published**; the vault (work/confidential content) is a **separate private repo** outside this tree, located at `$WIKI_VAULT`. Vault dirs (`00_Inbox`…`30_Learning`, `.obsidian`) are git-ignored here so they can never be committed into the code history. Don't push the vault to any personal/public remote.

## 7. Designed for obsolescence
- Each harness piece encodes a current model limitation. After a model upgrade, re-check whether a scoped prompt, gate, or tool is still needed and remove what isn't.
