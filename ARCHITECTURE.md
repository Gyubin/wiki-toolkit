# ARCHITECTURE — wiki-agent

> A map, not a manual. Structural boundaries that rarely change, and what does **not** exist where.
> For the "why" of each feature, read the ExecPlans in `docs/superpowers/specs/` and `plans/`.

A local conversational AI agent + FastAPI web app that turns raw clips and coding sessions into
verified, source-linked knowledge and learning material in one Markdown vault. The vault on disk is
the product; Obsidian reads it; this code writes it.

## Layers (imports flow upward only — a higher layer may import a lower one, never the reverse)

```
L0  schema.py          enums, IDs, frontmatter render/parse — SINGLE SOURCE OF TRUTH
L1  core/*             pure, deterministic vault logic (no LLM, no web)
      sources  claims  wiki  learning  index  scaffold  git  projects  lint  search
L2  tools.py           wraps core/* as in-process MCP @tools (mcp__wiki__*)
    permissions.py     can_use_tool gate (verified gate)
L3  subagents.py       AgentDefinition x6 (ingest/verify/answer/learning/wrap/lint), scoped tools
L4  agent.py           ClaudeAgentOptions + WikiSession (one conversational session)
L5  app.py             FastAPI: routes + SSE; serves web/index.html
    __main__.py        CLI: `uv run wiki [init|serve|lint|search]`
```

The dependency direction above is **mechanically enforced** by `tests/test_architecture.py` — a
violation fails the test, not a code review.

## Module responsibilities (one line each)

- `schema.py` — `CLAIM_TYPES`/`CLAIM_STATUSES`/`SENSITIVITIES`/`WIKI_PAGE_TYPES`/`LEARNING_LEVELS`, `make_id`, `render_doc`/`parse_doc`, validators.
- `core/scaffold.py` — create vault folder tree + seed index/log files.
- `core/index.py` — append-only logs, upsert-by-id index lines under `06_Metadata/`.
- `core/sources.py` — capture raw clips (Inbox) with sensitivity tag; html→markdown; triage records.
- `core/claims.py` — claim lifecycle: create (always `unverified`), dedup key, `promote_claim` (verified gate), status changes.
- `core/wiki.py` — human-readable wiki pages with enforced frontmatter + index entry.
- `core/learning.py` — learning items + spaced-repetition review driver.
- `core/git.py` — read-only git session collection (diff/commits/files) for wrap-feature.
- `core/projects.py` — `01_Projects/<repo>/` session summaries and ADRs.
- `core/lint.py` — deterministic, report-only vault hygiene checks.
- `core/search.py` — hybrid BM25 + local-embedding (fastembed) search, RRF fusion; injectable embedder.
- `tools.py` — `@tool` wrappers + `build_wiki_server`; `WIKI_TOOL_NAMES`.
- `permissions.py` — `make_can_use_tool` (denies unapproved `verified` promotion).
- `subagents.py` — `build_subagents()`; per-agent prompt (`prompts/*.md`) + tool allowlist.
- `agent.py` — `build_options(vault)` + `WikiSession` (async, multi-turn).
- `app.py` — `create_app(vault, embed_fn=None)`: capture/queues/chat/wrap/lint/search routes.
- `__main__.py` — process entry; scaffolds the vault then serves or runs a CLI subcommand.

## What is NOT here (constraints by absence)

- **`core/` has no LLM or web dependency.** No `claude_agent_sdk`, `fastapi`, `uvicorn`. Core is pure and unit-tested without a model or server. (Enforced.)
- **`schema.py` imports nothing from `wiki_agent`.** It is the base. (Enforced.)
- **Only `app.py` imports the web framework.** (Enforced.)
- **No second "work vault."** Work/confidential content lives in the same vault under `01_Projects/<repo>/`, distinguished by a `sensitivity` frontmatter tag — not refused.
- **No external embedding API.** Embeddings are local (fastembed); vault content never leaves the machine.
- **No persistent conversation memory.** Durable state = vault Markdown files + git history. Chat sessions are ephemeral.
- **`lint` checks vault content; `test_architecture.py` checks code layers.** Different things — don't conflate.

## Process

Changes go through `docs/superpowers/`: brainstorm → spec → plan (ExecPlans) → TDD → `uv run pytest` →
commit. If a decision isn't written down there, it doesn't exist for the next agent.
