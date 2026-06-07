# AGENTS.md — golden principles for agents working in this repo

Opinionated, mechanical rules. Follow them; several are enforced by tests. Read `ARCHITECTURE.md`
for the code map and `docs/superpowers/` for the design history (ExecPlans).

## 1. Environment
- Use **`uv`**: `uv run pytest`, `uv run wiki init|serve|lint|search`. Don't invoke `python`/`pip` directly.
- The agent runtime (`WikiSession`, `/chat`, `/wrap`, `/lint/contradictions`) needs the **Claude Code CLI** installed; pure `core/` logic and the web routes that only touch `core/` do not.

## 2. Integrity — go through `core/`, never hand-write structured files
- All structured writes — sources, claims, wiki pages, sessions, ADRs, learning items, and the index/log — **must** go through a `core/` function (or its `@tool` wrapper). Do **not** hand-roll Markdown or frontmatter.
- `schema.py` is the **single source of truth** for enums, IDs, and frontmatter. Add a status/type there first; never inline a literal list elsewhere.

## 3. Gates and sensitivity
- A claim becomes `verified` **only** with human approval or `evidence_refs` — `promote_claim` raises and `can_use_tool` denies otherwise. Don't bypass it.
- Work/confidential content is **not refused**; it is routed to `01_Projects/<repo>/` and tagged `sensitivity`. Keep secrets/company identifiers out of `03_Resources/` and learning items.
- `lint` is **report-only** — it never modifies the vault. Resolution is the human's job (Verify tab).

## 4. Layering (enforced)
- Imports flow upward only: `schema → core → tools/permissions → subagents → agent → app`.
- `core/` stays **pure**: no `claude_agent_sdk`, `fastapi`, `uvicorn`. `schema.py` imports nothing from `wiki_agent`. Only `app.py` imports the web framework.
- `tests/test_architecture.py` fails on any violation. Run it before assuming a refactor is safe.

## 5. Workflow
- Non-trivial change: write a spec + plan under `docs/superpowers/`, then TDD (failing test → impl → pass).
- `uv run pytest` must be green before committing.
- Commit **only the files your task touched** — `git add -A` is forbidden (the repo holds unrelated vault content and design docs). End commit subjects in the conventional `feat:`/`test:`/`docs:` style already used.

## 6. Security
- This is one unified vault containing work content. **Do not push it to a personal or public remote.** No remote is configured by default — keep it that way unless it's a private, authorized destination.

## 7. Designed for obsolescence
- Each harness piece encodes a current model limitation. After a model upgrade, re-check whether a scoped prompt, gate, or tool is still needed and remove what isn't.
