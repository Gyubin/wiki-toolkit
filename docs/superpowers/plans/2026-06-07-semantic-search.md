# semantic search Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add hybrid local search (BM25 + local embeddings, RRF fusion) over the vault — exposed as a `search_wiki` MCP tool, a `GET /search` route, a Search tab, and `uv run wiki search`, per `docs/superpowers/specs/2026-06-07-semantic-search-design.md`.

**Architecture:** `core/search.py` builds an index over vault knowledge docs and fuses BM25 lexical ranks with local-embedding cosine ranks via Reciprocal Rank Fusion. The embedder is injectable (`embed_fn`) so unit tests run with a deterministic fake — no model download; the runtime default uses local `fastembed` (ONNX, data stays local — vault has work/confidential content). Index is cached in-process.

**Tech Stack:** Same as prior phases + `rank-bm25`, `fastembed`. Run tests with `uv run pytest`. Work on branch `main`. Commit ONLY the files each task touches (never `git add -A`).

---

## File Structure

```
wiki_agent/core/search.py   # NEW: iter_docs, tokenize, SearchIndex, build_index
wiki_agent/tools.py         # MODIFY: search_wiki tool + name (cached index)
wiki_agent/subagents.py     # MODIFY: answer gets search_wiki
wiki_agent/app.py           # MODIFY: create_app(vault, embed_fn=None) + GET /search (cached)
wiki_agent/web/index.html   # MODIFY: Search tab
wiki_agent/__main__.py      # MODIFY: search command
pyproject.toml              # MODIFY: + rank-bm25, fastembed
tests/test_search.py        # NEW (fake embedder)
tests/test_app.py           # MODIFY (/search via fake embedder)
tests/test_subagents.py     # MODIFY (answer has search_wiki)
```
`agent.py` needs no change — `allowed_tools` splats `*WIKI_TOOL_NAMES`, so `search_wiki` is auto-included once Task 2 adds it.

---

## Task 1: deps + core/search.py

**Files:** Modify `pyproject.toml`; Create `wiki_agent/core/search.py`, `tests/test_search.py`

- [ ] **Step 1: Add dependencies to `pyproject.toml`** — add these two lines to the `dependencies = [...]` list:
```toml
    "rank-bm25>=0.2.2",
    "fastembed>=0.3",
```
Then run `uv sync`. Expected: resolves and installs. If `fastembed` fails to build/install on this platform, report BLOCKED with the error (do not remove it — it is required at runtime; unit tests below do not import it).

- [ ] **Step 2: Write the failing test** — `tests/test_search.py`

```python
from wiki_agent.core import search, claims
from wiki_agent import schema

_VOCAB = ["python", "typed", "react", "hook", "effect", "git", "commit", "search", "vector"]


def fake_embed(texts):
    return [[1.0 if w in set(search.tokenize(t)) else 0.0 for w in _VOCAB] for t in texts]


def test_tokenize():
    assert search.tokenize("React useEffect!!") == ["react", "useeffect"]


def test_iter_docs_scopes(vault):
    claims.create_claim(vault, claim="react hook effect timing", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-01", seq=1)
    (vault / "06_Metadata/notes.md").write_text("should be excluded", encoding="utf-8")
    paths = {d["path"] for d in search.iter_docs(vault)}
    assert any("10_Claims" in p for p in paths)
    assert not any("06_Metadata" in p for p in paths)


def test_query_ranks_relevant_top(vault):
    claims.create_claim(vault, claim="react hook effect timing", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-01", seq=1)
    claims.create_claim(vault, claim="git commit message style", claim_type="technical_fact",
                        source_refs=["s"], date_str="2026-01-02", seq=1)
    idx = search.build_index(vault, embed_fn=fake_embed)
    results = idx.query("react hook", k=2)
    assert results
    assert "react" in results[0]["title"].lower()
    assert {"ref", "title", "score", "snippet"} <= set(results[0])


def test_empty_query_returns_empty(vault):
    idx = search.build_index(vault, embed_fn=fake_embed)
    assert idx.query("", k=5) == []
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_search.py -v`
Expected: FAIL (module missing).

- [ ] **Step 4: Write `wiki_agent/core/search.py`**

```python
"""Hybrid local search: BM25 (lexical) + local embeddings (semantic), RRF fusion."""
from __future__ import annotations

import math
import re
from pathlib import Path

from rank_bm25 import BM25Okapi

from .. import schema

_INCLUDE = ("00_Inbox", "01_Projects", "02_Areas", "03_Resources", "10_Claims", "30_Learning")
_RRF_K = 60


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


def iter_docs(vault: Path) -> list[dict]:
    vault = Path(vault)
    docs: list[dict] = []
    for root in _INCLUDE:
        base = vault / root
        if not base.exists():
            continue
        for p in base.rglob("*.md"):
            try:
                meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            title = (meta.get("title") or meta.get("name") or meta.get("claim")
                     or meta.get("topic") or p.stem)
            ref = meta.get("id") or meta.get("name") or str(p.relative_to(vault))
            head = " ".join(str(meta.get(k, "")) for k in ("title", "name", "claim", "topic"))
            text = f"{head}\n{body}".strip()
            docs.append({"ref": str(ref), "title": str(title), "text": text,
                         "path": str(p.relative_to(vault))})
    return docs


def _cosine(a, b) -> float:
    num = sum(x * y for x, y in zip(a, b))
    da = math.sqrt(sum(x * x for x in a))
    db = math.sqrt(sum(y * y for y in b))
    return num / (da * db) if da and db else 0.0


class SearchIndex:
    def __init__(self, docs: list[dict], embed_fn):
        self.docs = docs
        self._embed_fn = embed_fn
        self._bm25 = BM25Okapi([tokenize(d["text"]) for d in docs]) if docs else None
        self._doc_vecs = embed_fn([d["text"] for d in docs]) if docs else []

    def query(self, q: str, k: int = 8) -> list[dict]:
        if not self.docs or not q.strip():
            return []
        n = len(self.docs)
        bm = self._bm25.get_scores(tokenize(q))
        qvec = self._embed_fn([q])[0]
        cos = [_cosine(qvec, v) for v in self._doc_vecs]
        bm_rank = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: bm[i], reverse=True))}
        cos_rank = {i: r for r, i in enumerate(sorted(range(n), key=lambda i: cos[i], reverse=True))}
        fused = sorted(
            ((1.0 / (_RRF_K + bm_rank[i]) + 1.0 / (_RRF_K + cos_rank[i]), i) for i in range(n)),
            reverse=True,
        )
        out = []
        for score, i in fused[:k]:
            d = self.docs[i]
            out.append({"ref": d["ref"], "title": d["title"],
                        "score": round(score, 6), "snippet": d["text"][:200]})
        return out


def _default_embedder():
    from fastembed import TextEmbedding
    model = TextEmbedding(model_name="intfloat/multilingual-e5-small")

    def embed(texts):
        return [list(v) for v in model.embed(list(texts))]

    return embed


def build_index(vault: Path, embed_fn=None) -> SearchIndex:
    return SearchIndex(iter_docs(vault), embed_fn or _default_embedder())
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_search.py -v`
Expected: 4 passed. (Tests use `fake_embed`; `fastembed` is not imported here.)

- [ ] **Step 6: Verify the runtime embedder model name is valid (no test dependency)**

Run:
```bash
uv run python -c "from fastembed import TextEmbedding; names=[m['model'] for m in TextEmbedding.list_supported_models()]; print('intfloat/multilingual-e5-small' in names); print([n for n in names if 'multilingual' in n.lower()][:5])"
```
Expected: prints `True`. If it prints `False`, edit `_default_embedder` to use a multilingual model name from the printed list (prefer one containing `multilingual`); if none, drop the `model_name=` argument to use the default. This does not affect the unit tests.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock wiki_agent/core/search.py tests/test_search.py
git commit -m "feat: hybrid local search (BM25 + embeddings, RRF)"
```
(Add `uv.lock` only if it changed/exists.)

---

## Task 2: search_wiki tool + answer subagent

**Files:** Modify `wiki_agent/tools.py`, `wiki_agent/subagents.py`, `tests/test_tools.py`, `tests/test_subagents.py`

- [ ] **Step 1: Append tests**

To `tests/test_tools.py`:
```python
def test_search_tool_name_present():
    assert "mcp__wiki__search_wiki" in tools.WIKI_TOOL_NAMES
```

To `tests/test_subagents.py` (append a new test; keep existing ones):
```python
def test_answer_has_search():
    agents = subagents.build_subagents()
    assert "mcp__wiki__search_wiki" in agents["answer"].tools
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_tools.py::test_search_tool_name_present tests/test_subagents.py::test_answer_has_search -v`
Expected: FAIL.

- [ ] **Step 3: Modify `wiki_agent/tools.py`**

3a. Add `search` to the core import — change `from .core import claims, git, learning, projects, sources, wiki` to:
```python
from .core import claims, git, learning, projects, search, sources, wiki
```

3b. Append to `WIKI_TOOL_NAMES`:
```python
    "mcp__wiki__search_wiki",
```

3c. Inside `build_wiki_server`, before the final `return create_sdk_mcp_server(...)`, add a cached index + tool:
```python
    _search_index: dict = {}

    @tool("search_wiki", "Hybrid semantic+lexical search over the vault",
          {"query": str})
    async def search_wiki(args):
        if "idx" not in _search_index:
            _search_index["idx"] = search.build_index(vault)
        results = _search_index["idx"].query(args["query"], int(args.get("k", 8)))
        text = "\n".join(f"- [{r['ref']}] {r['title']} (score {r['score']})"
                         for r in results) or "no results"
        return _ok(text)
```

3d. Add `search_wiki` to the `tools=[...]` list in the final `return create_sdk_mcp_server(...)` (append after the last existing entry `create_decision`):
```python
               collect_git_session, create_session_summary, create_decision, search_wiki],
```

- [ ] **Step 4: Modify `wiki_agent/subagents.py`** — in `build_subagents()`, change the `answer` agent's `tools` line from:
```python
            tools=["Read", "Grep", "Glob", "mcp__wiki__create_claim"],
```
to:
```python
            tools=["Read", "Grep", "Glob", "mcp__wiki__create_claim", "mcp__wiki__search_wiki"],
```

- [ ] **Step 5: Run to verify they pass**

Run: `uv run pytest tests/test_tools.py tests/test_subagents.py -v`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add wiki_agent/tools.py wiki_agent/subagents.py tests/test_tools.py tests/test_subagents.py
git commit -m "feat: search_wiki tool wired into answer subagent"
```

---

## Task 3: GET /search route (embedder-injectable app)

**Files:** Modify `wiki_agent/app.py`, `tests/test_app.py`

- [ ] **Step 1: Append test** to `tests/test_app.py`:
```python
_SEARCH_VOCAB = ["python", "typed", "react", "hook", "git", "commit"]


def _fake_embed(texts):
    from wiki_agent.core import search
    return [[1.0 if w in set(search.tokenize(t)) else 0.0 for w in _SEARCH_VOCAB] for t in texts]


def test_search_route(vault):
    from wiki_agent.core import claims
    from wiki_agent import schema
    claims.create_claim(vault, claim="react hook timing", claim_type="technical_fact",
                        source_refs=["s"], date_str=schema.today_str(), seq=1)
    claims.create_claim(vault, claim="git commit conventions", claim_type="technical_fact",
                        source_refs=["s"], date_str=schema.today_str(), seq=2)
    app = create_app(vault, embed_fn=_fake_embed)
    client = TestClient(app)
    r = client.get("/search?q=react")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and rows
    assert "react" in rows[0]["title"].lower()
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_app.py::test_search_route -v`
Expected: FAIL (`create_app` takes no `embed_fn`, or no `/search`).

- [ ] **Step 3: Modify `wiki_agent/app.py`**

3a. Add `search` to the core import — change `from .core import claims, learning, lint, sources` to:
```python
from .core import claims, learning, lint, search, sources
```

3b. Change the signature `def create_app(vault: Path) -> FastAPI:` to:
```python
def create_app(vault: Path, embed_fn=None) -> FastAPI:
```

3c. Inside `create_app`, add a cached search index + route immediately BEFORE the `@app.get("/")` home route:
```python
    _search_index: dict = {}

    @app.get("/search")
    def search_route(q: str = "", k: int = 8, reindex: bool = False):
        if reindex or "idx" not in _search_index:
            _search_index["idx"] = search.build_index(vault, embed_fn=embed_fn)
        return _search_index["idx"].query(q, k)
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_app.py -v`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/app.py tests/test_app.py
git commit -m "feat: GET /search route with injectable embedder"
```

---

## Task 4: Search tab + CLI search command

**Files:** Modify `wiki_agent/web/index.html`, `wiki_agent/__main__.py`

- [ ] **Step 1: Edit `wiki_agent/web/index.html`**

1a. REPLACE the `<nav>...</nav>` block with (adds Search after Lint):
```html
  <nav>
    <button data-tab="chat" class="active">Chat</button>
    <button data-tab="capture">Capture</button>
    <button data-tab="wrap">Wrap</button>
    <button data-tab="verify">Verify</button>
    <button data-tab="review">Review</button>
    <button data-tab="lint">Lint</button>
    <button data-tab="search">Search</button>
  </nav>
```

1b. INSERT this section immediately after the `lint` section's closing `</section>` (before `</main>`):
```html
    <section id="search" class="panel">
      <input id="searchQ" style="width:70%" placeholder="의미 기반 검색어" />
      <button onclick="searchRun()">검색</button>
      <div id="searchResults"></div>
    </section>
```

1c. INSERT this JS function inside the `<script>` block, right after the `lintContradictions()` function's closing brace:
```javascript
    async function searchRun() {
      const q = document.getElementById('searchQ').value;
      const rows = await (await fetch('/search?q=' + encodeURIComponent(q))).json();
      document.getElementById('searchResults').innerHTML = rows.map(r =>
        `<div class="row"><b>${r.title}</b> <small>[${r.ref}] ${r.score}</small><br>${r.snippet}</div>`
      ).join('') || '결과 없음';
    }
```

- [ ] **Step 2: Edit `wiki_agent/__main__.py`** — add a `search` command. Add this import near the existing `from .core import lint as lint_core`:
```python
from .core import search as search_core
```
Then, inside `main()`, add this branch BEFORE the final `print(f"unknown command: ...")` line:
```python
    if cmd == "search":
        query = " ".join(args[1:])
        idx = search_core.build_index(Path.cwd())
        for r in idx.query(query, 8):
            print(f"[{r['score']}] {r['title']} ({r['ref']})")
        return
```

- [ ] **Step 3: Verify UI serves with the Search tab**

Run:
```bash
uv run python -c "from fastapi.testclient import TestClient; from wiki_agent.app import create_app; import pathlib; c=TestClient(create_app(pathlib.Path('.'))); r=c.get('/'); assert r.status_code==200 and 'data-tab=\"search\"' in r.text and 'searchRun' in r.text; print('Search tab OK')"
```
Expected: prints `Search tab OK`. (Do not call `/search` here — that would load the real model.)

- [ ] **Step 4: Run the full suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/web/index.html wiki_agent/__main__.py
git commit -m "feat: Search tab and CLI search command"
```

---

## Task 5: Live fastembed smoke

**Files:** none (verification only)

- [ ] **Step 1: Full suite (fake embedder — fast, offline)**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 2: Live semantic search smoke (downloads the model on first run; needs network once)**

```bash
cd /Users/gyubin.son/workspace/dev/personal-wiki
uv run python - <<'PY'
import pathlib
from wiki_agent.core import claims, search
from wiki_agent import schema
v = pathlib.Path.cwd()
claims.create_claim(v, claim="useEffect runs after the browser paints", claim_type="technical_fact",
                    source_refs=["s"], date_str=schema.today_str(), seq=950)
idx = search.build_index(v)  # real fastembed
for r in idx.query("when does the effect hook fire relative to rendering", 5):
    print(r["score"], r["title"])
PY
rm -f 10_Claims/pending/claim-*-950.md
```
Expected: the seeded useEffect claim ranks near the top even though the query uses different words (semantic match). If `fastembed` cannot download the model (offline), note it — the deterministic checks and `core/search` unit tests already pass; this step is a runtime/quality check only.

- [ ] **Step 3: Final suite re-check**

Run: `uv run pytest -q`
Expected: all green.

---

## Self-Review

**Spec coverage:**
- Hybrid BM25 + local embeddings + RRF → Task 1 (`SearchIndex.query`). ✓
- Injectable embedder / fake in tests / fastembed default (local, data stays local) → Task 1 (`build_index(embed_fn)`, `_default_embedder`). ✓
- `search_wiki` MCP tool + answer subagent → Task 2. ✓
- `GET /search` (embedder-injectable, cached) → Task 3. ✓
- Search tab + CLI → Task 4. ✓
- Tests: core (Task 1), tool/subagent (Task 2), route (Task 3), live (Task 5). ✓
- Scoping (exclude 06_Metadata/docs) → `iter_docs` + `test_iter_docs_scopes` (Task 1). ✓
- `agent.py` unchanged (splat) — `search_wiki` flows into allowed_tools automatically. ✓

**Placeholder scan:** No TBD/TODO; full code in every step. The model-name verification (Task 1 Step 6) is a concrete check-and-adjust instruction, not a placeholder, and is isolated from the (fake-embedder) test suite.

**Type/name consistency:** `tokenize`/`iter_docs`/`SearchIndex`/`build_index` identical across Task 1 (def), Task 2 (tool: `search.build_index(vault)`), Task 3 (route: `search.build_index(vault, embed_fn=embed_fn)`), Task 4 (CLI: `search_core.build_index(Path.cwd())`). Result dict keys `ref/title/score/snippet` identical across core, tool text, route JSON, web render, CLI print. `_fake_embed`/`fake_embed` are per-test-file helpers (named locally, not shared across tasks). `create_app(vault, embed_fn=None)` — the new optional param is backward compatible with all existing `create_app(vault)` callers in earlier test files.
