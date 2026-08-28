# wiki-toolkit

한국어: [README.ko.md](README.ko.md)

A local toolkit that grows one Markdown vault into a personal knowledge base. Raw material
(web clips, coding sessions) comes in, gets split into source-linked claims, and only what a
human has reviewed gets promoted into wiki pages and flashcards. You read the vault with
Obsidian; every structured write goes through the code in this repo.

Despite what the old name (`wiki-agents`) promised, **there are no agents here.** This repo
is the pure vault logic (`core/`) plus a thin shell that exposes it as 19 MCP tools. The
judgment calls are made by Claude Code holding those tools, and the procedure for each task
lives in `wiki_toolkit/prompts/*.md`.

## Core ideas

- **Raw text is a candidate, not truth.** A capture is stored as a source, then split into
  claims small enough that a single verdict applies to each. Every claim is born
  `unverified`.
- **There is exactly one road to `verified`.** Passing written evidence (`evidence_refs`)
  to `promote_claim`. When the evidence is your own judgment, you write that judgment down
  as a sentence. If you cannot, the claim is `attributed`, `opinion`, or
  `accepted_for_now` instead.
- **Every claim carries its source passage.** The claim text is already a reworded summary,
  so the verbatim passage it came from is stored alongside (`## 원문`). Without it, a claim
  that subtly bends the original passes review.
- **Long bodies travel as file paths.** Retyping content into tool arguments is where text
  silently drifts. `create_source` takes `content_path`, `update_wiki_page` takes
  `body_path`.
- **Every write commits the vault.** If the vault is a git repo, each write tool leaves one
  commit, so history answers "what changed when".
- **The tools tell you what is next.** Write tools append a "다음: ..." line to their
  result, so nobody has to memorize the pipeline stages.

## Pipeline

```
clip/session     capture source    extract claims     human review       wiki page          flashcards
             ->                ->                 ->                 ->                 ->
             create_source       create_claim        promote_claim      create_wiki_page   create_learning_item
```

Each stage waits for a human decision. `vault_next_step` computes where you are.

## Getting started

Requires [uv](https://docs.astral.sh/uv/) and Python 3.11+.

```bash
git clone https://github.com/Gyubin/wiki-toolkit.git
cd wiki-toolkit

# 1) create a vault (a separate directory OUTSIDE this repo)
uv run wiki init ~/wiki-vault

# 2) set the embedding API key for search
cp .env.example .env   # fill in OPENAI_API_KEY

# 3) register the MCP server with Claude Code
claude mcp add wiki -- uv run --directory "$PWD" wiki mcp ~/wiki-vault
```

After registration the 19 `mcp__wiki__*` tools are available inside Claude Code. To collect
clips from a browser, follow [the Obsidian Web Clipper setup](docs/web-clipper-setup.md).

Every command resolves the vault path the same way: explicit argument > `$WIKI_VAULT` >
current directory. Only `init` creates a vault; the other commands refuse a directory
without `06_Metadata/` (exit 2).

## CLI

```bash
uv run wiki init [vault]             # create the folder tree and templates (only init scaffolds)
uv run wiki mcp [vault]              # expose the 19 tools over stdio MCP (for Claude Code)
uv run wiki lint [vault]             # read-only hygiene checks; exit 1 when errors exist
uv run wiki search [vault] <query>   # hybrid search (BM25 + embeddings)
```

## The 19 MCP tools

| Group | Tools | What they do |
| --- | --- | --- |
| capture | `create_source` `triage_record` `update_source_raw` | Capture raw text into the Inbox and record the triage decision (drop, keep-as-link, deep) |
| claims | `create_claim` `find_similar_claim` `promote_claim` `set_claim_status` `update_claim_quote` `list_pending` | Create claims (always unverified), check duplicates, change status. `verified` requires `evidence_refs`. Claims inherit the sensitivity of their sources |
| wiki | `create_wiki_page` `update_wiki_page` | Human-readable pages under `03_Resources/` |
| learning | `create_learning_item` `list_due_reviews` `record_review` | Flashcards and spaced-repetition reviews |
| coding sessions | `collect_git_session` `create_session_summary` `create_decision` | Read a repo diff and keep session summaries and ADRs (`01_Projects/<repo>/`, sensitivity=work) |
| search and guidance | `search_wiki` `vault_next_step` | Search the whole vault; compute the next pipeline step |

To fix something that is already in the vault, use `update_source_raw`,
`update_claim_quote`, or `update_wiki_page` instead of hand-editing files. Hand edits
bypass the schema, the ID sequencing, and the verified gate, and no code stops you; it is a
rule, not a guardrail.

## Vault layout

The vault is a separate directory outside this repo (usually its own private git repo).
`wiki init` creates:

```
00_Inbox/        # where raw captures land (browser-clips, chatgpt-gemini-clips, ...)
01_Projects/     # per-repo session summaries and ADRs (sensitivity: work)
02_Areas/
03_Resources/    # human-readable wiki pages (Concepts, Patterns, Glossary, Comparisons, Misconceptions)
06_Metadata/     # indexes, logs, templates
10_Claims/       # folders by status: pending, verified, attributed, disputed, rejected, outdated
30_Learning/     # learning material (flashcards, quizzes, exercises, skill-maps, weekly-synthesis)
```

A claim starts at `unverified` and moves up to `verified` (evidence required),
`attributed`, `opinion`, `partially_true`, or `accepted_for_now`, or down to `disputed`,
`outdated`, `deprecated`, or `rejected`. The single source of truth for the schema is
`wiki_toolkit/schema.py`.

## prompts/ are contracts, not code

Nothing reads `wiki_toolkit/prompts/*.md` programmatically. They are procedures that Claude
Code must read before working, and no layer attaches them automatically. Skipping them
fails silently: triage gets skipped, claims come out too coarse, quotes drift.

| File | When to read it |
| --- | --- |
| `system.md` | Shared principles, before any vault work |
| `ingest.md` | Splitting one clip into a source and claims |
| `verify.md` | Reviewing and promoting pending claims |
| `wiki-page.md` | Creating or editing wiki pages |
| `answer.md` `learning.md` `wrap.md` `lint.md` | Answering, flashcards, session wrap-up, contradiction audit |

## Search

`search_wiki` and `wiki search` fuse BM25 (Korean 2-gram) and embedding search with RRF.
Embeddings default to the OpenAI Embeddings API (`text-embedding-3-large`), so
`OPENAI_API_KEY` is required.

- `sensitivity: confidential` bodies are not sent to the API (they stay searchable via
  BM25). Clips that have not been ingested yet (no id) are not sent either, since they have
  no sensitivity tag yet. Setting `WIKI_EMBED_SEND_SENSITIVE=1` opts into sending both.
- To run fully local, set `WIKI_EMBED_PROVIDER=local` (fastembed; first run downloads 2.1GB
  of weights).
- Vectors are cached on disk; only changed documents are re-embedded. When the embedding
  API is temporarily unreachable, search degrades to BM25-only with a warning instead of
  failing.

Settings come from shell environment variables first, then from `.env` at the repo root
(see `.env.example`). Also supported: `WIKI_EMBED_MODEL`, `WIKI_EMBED_DIM`,
`WIKI_OPENAI_BASE_URL`, `WIKI_EMBED_SEND_SENSITIVE`, `WIKI_EMBED_CACHE`, `WIKI_ENV_FILE`.

## Development

```bash
uv run pytest        # tests
uv run ruff check    # lint
uv run pre-commit install --hook-type pre-commit --hook-type pre-push   # commit/push hooks
```

Imports flow only in the direction `schema -> core -> tools -> __main__`, and `core/` is
pure logic with no LLM or web dependency. `tests/test_architecture.py` enforces the
boundary mechanically.

Further reading:

- [ARCHITECTURE.md](ARCHITECTURE.md): the code map, design judgments, and the record of
  what was deleted
- [AGENTS.md](AGENTS.md): rules for agents working in this repo
- `docs/superpowers/`: change history (brainstorms, specs, ExecPlans)
