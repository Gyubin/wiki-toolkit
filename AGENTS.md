# AGENTS.md — golden principles for agents working in this repo

Opinionated, mechanical rules. Follow them; several are enforced by tests. Read `ARCHITECTURE.md`
for the code map and `docs/superpowers/` for the design history (ExecPlans).

## 1. Environment
- Use **`uv`**: `uv run pytest`, `uv run ruff check`, `uv run wiki init|serve|lint|search|mcp`. Don't invoke `python`/`pip` directly.
- Only `init` scaffolds. serve/lint/search/mcp **refuse** a directory without `06_Metadata/` (exit 2). lint exits 1 when error-severity findings exist.
- `wiki mcp <vault>` exposes the same 17 tools over stdio for Claude Code: `claude mcp add wiki -- uv run --directory <this repo> wiki mcp <vault>`.
- **The vault lives outside this repo.** Every `wiki` subcommand resolves the vault as: explicit path arg > `$WIKI_VAULT` > cwd (`resolve_vault` in `__main__.py`). Point it at your vault, e.g. `uv run wiki serve "$WIKI_VAULT"`. This repo holds **code only**.
- **검색 임베딩은 기본이 OpenAI API다.** `search`와 `search_wiki`는 `OPENAI_API_KEY`가 필요하다(없으면
  CLI는 안내 + exit 2, 웹은 503). 오프라인이나 전량 로컬이 필요하면 `WIKI_EMBED_PROVIDER=local`
  (fastembed, 첫 실행에 가중치 2.1GB 다운로드). `sensitivity: confidential` 문서 본문만 원격 임베딩에서
  제외된다(BM25로는 검색됨). 키와 설정은 셸 export 또는 repo 루트 `.env`(gitignore, `.env.example` 참조).
- The agent runtime (`WikiSession`, `/chat`, `/wrap`, `/lint/contradictions`) needs the **Claude Code CLI** installed; pure `core/` logic and the web routes that only touch `core/` do not.

## 2. Integrity — go through `core/`, never hand-write structured files
- All structured writes — sources, claims, wiki pages, sessions, ADRs, learning items, and the index/log — **must** go through a `core/` function (or its `@tool` wrapper). Do **not** hand-roll Markdown or frontmatter.
- `schema.py` is the **single source of truth** for enums, IDs, and frontmatter. Add a status/type there first; never inline a literal list elsewhere.

## 3. Gates and sensitivity
- A claim becomes `verified` only via `evidence_refs` (agent path) or human approval in the web Verify tab. `approved_by_human` is **not** a tool argument; the gate strips it. `promote_claim`/`set_claim_status` must stay **out of** `allowed_tools` (a preapproved tool never reaches `can_use_tool`). The main agent has no Bash/Write/Edit, so files can't be hand-edited around the gate.
- Work/confidential content is **not refused**; it is routed to `01_Projects/<repo>/` and tagged `sensitivity`. Keep secrets/company identifiers out of `03_Resources/` and learning items.
- `lint` is **report-only** — it never modifies the vault. Resolution is the human's job (Verify tab).

## 4. Layering (enforced)
- Imports flow upward only: `schema → core → tools/permissions → subagents → agent → app`.
- `core/` stays **pure**: no `claude_agent_sdk`, `fastapi`, `uvicorn`. `schema.py` imports nothing from `wiki_agents`. Only `app.py` imports the web framework.
- `tests/test_architecture.py` fails on any violation. Run it before assuming a refactor is safe.

## 5. Workflow
- Non-trivial change: write a spec + plan under `docs/superpowers/`, then TDD (failing test → impl → pass).
- `uv run ruff check` clean and `uv run pytest` green before committing. Fast loops are wired via `.pre-commit-config.yaml` (ruff at commit, pytest at push); install once with `uv run pre-commit install --hook-type pre-commit --hook-type pre-push`.
- Commit **only the files your task touched** — `git add -A` is forbidden. End commit subjects in the conventional `feat:`/`test:`/`docs:` style already used.

## 6. Security
- This repo is **code only and may be published**; the vault (work/confidential content) is a **separate private repo** outside this tree, located at `$WIKI_VAULT`. Vault dirs (`00_Inbox`…`30_Learning`, `.obsidian`) are git-ignored here so they can never be committed into the code history. Don't push the vault to any personal/public remote.

## 7. Designed for obsolescence
- Each harness piece encodes a current model limitation. After a model upgrade, re-check whether a scoped prompt, gate, or tool is still needed and remove what isn't.
