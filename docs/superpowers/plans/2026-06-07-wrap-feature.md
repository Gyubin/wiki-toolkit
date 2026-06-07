# wrap-feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `wrap-feature` — turn a coding session (git `base..head` diff + optional transcript) into a project session summary, ADRs, generalized concept/pattern wiki pages, and learning artifacts in the unified vault, per `docs/superpowers/specs/2026-06-07-wrap-feature-design.md`.

**Architecture:** New deterministic core (`core/git.py`, `core/projects.py`) + a `wrap` subagent + new MCP tools, driven from a web "Wrap" tab via a `/wrap` SSE route (reusing `WikiSession`). Phase-1 sensitivity hard-gate is relaxed from "refuse work" to "tag + allow"; project knowledge lands under `01_Projects/<repo>/`.

**Tech Stack:** Same as phase 1 — Python 3.11+, `uv`, `claude-agent-sdk` (model `claude-opus-4-8`), FastAPI, PyYAML, pytest. Run tests with `uv run pytest`. Work on branch `main`. Commit each task; commit ONLY the files the task touches (the repo also holds unrelated design docs — never `git add -A`).

---

## File Structure

```
wiki_agent/
  core/
    git.py        # NEW: collect_session (read-only)
    projects.py   # NEW: project_slug, ensure_project, create_session_summary, create_decision
    sources.py    # MODIFY: relax work refusal -> tag
    claims.py     # MODIFY: optional sensitivity param
    wiki.py       # MODIFY: optional sensitivity param
  permissions.py  # MODIFY: drop create_source work-deny (keep verified gate)
  tools.py        # MODIFY: +3 tools, +names
  subagents.py    # MODIFY: add `wrap`
  prompts/wrap.md # NEW
  app.py          # MODIFY: add POST /wrap (in _attach_chat)
  web/index.html  # MODIFY: add Wrap tab
tests/
  test_git.py, test_projects.py            # NEW
  test_sources.py, test_permissions.py     # MODIFY
  test_subagents.py, test_tools.py, test_app.py  # MODIFY
```

`agent.py` needs **no change**: its `allowed_tools` already splats `*WIKI_TOOL_NAMES`, so the 3 new tool names are auto-included once Task 4 adds them.

---

## Task 1: core/git.py — read-only session collection

**Files:** Create `wiki_agent/core/git.py`, `tests/test_git.py`

- [ ] **Step 1: Write the failing test** — `tests/test_git.py`

```python
import subprocess
import pytest
from wiki_agent.core import git


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "myrepo"
    r.mkdir()
    def run(*a):
        subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)
    run("init")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (r / "a.txt").write_text("hello\n")
    run("add", ".")
    run("commit", "-m", "first")
    (r / "a.txt").write_text("hello world\n")
    run("add", ".")
    run("commit", "-m", "second: change a.txt")
    return r


def test_collect_session(repo):
    s = git.collect_session(repo, "HEAD~1", "HEAD")
    assert "a.txt" in s["changed_files"]
    assert any("second" in c["subject"] for c in s["commits"])
    assert "hello world" in s["diff"]


def test_collect_session_rejects_non_git(tmp_path):
    with pytest.raises(ValueError):
        git.collect_session(tmp_path, "HEAD~1", "HEAD")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_git.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/core/git.py`**

```python
"""Read-only git session collection for wrap-feature."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise ValueError(f"git failed in {repo}: {e}") from e
    return out.stdout


def collect_session(repo: Path, base: str, head: str = "HEAD") -> dict:
    repo = Path(repo)
    if not (repo / ".git").exists():
        raise ValueError(f"not a git repo: {repo}")
    rng = f"{base}..{head}"
    diff = _git(repo, "diff", rng)
    files = [f for f in _git(repo, "diff", "--name-only", rng).splitlines() if f]
    commits = []
    for ln in _git(repo, "log", "--format=%H%x09%s", rng).splitlines():
        if "\t" in ln:
            sha, subject = ln.split("\t", 1)
            commits.append({"sha": sha, "subject": subject})
    return {"diff": diff, "changed_files": files, "commits": commits}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_git.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/core/git.py tests/test_git.py
git commit -m "feat: read-only git session collection"
```

---

## Task 2: core/projects.py — sessions + ADRs

**Files:** Create `wiki_agent/core/projects.py`, `tests/test_projects.py`

- [ ] **Step 1: Write the failing test** — `tests/test_projects.py`

```python
from wiki_agent.core import projects
from wiki_agent import schema


def test_ensure_project(vault):
    base = projects.ensure_project(vault, "/some/path/MyRepo")
    assert base.name == "myrepo"
    assert (base / "sessions").is_dir()
    assert (base / "decisions").is_dir()
    assert (base / "project-index.md").exists()


def test_create_session_summary(vault):
    p = projects.create_session_summary(
        vault, repo="/x/MyRepo", title="add auth", body="## Goal\n\nx\n",
        date_str="2026-06-07", seq=1,
    )
    assert p.parent.name == "sessions"
    meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
    assert meta["type"] == "session"
    assert meta["repo"] == "myrepo"
    assert meta["sensitivity"] == "work"


def test_create_decision(vault):
    p = projects.create_decision(
        vault, repo="/x/MyRepo", title="use JWT", context="c", decision="d",
        alternatives="a", consequences="q", date_str="2026-06-07", seq=1,
    )
    assert p.parent.name == "decisions"
    meta, body = schema.parse_doc(p.read_text(encoding="utf-8"))
    assert meta["type"] == "decision"
    assert "## Context" in body and "## Consequences" in body
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_projects.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/core/projects.py`**

```python
"""Project-scoped knowledge under 01_Projects/<repo>/: sessions and ADRs."""
from __future__ import annotations

import re
from pathlib import Path

from .. import schema
from . import index


def project_slug(repo: Path | str) -> str:
    name = Path(repo).name
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "project"


def ensure_project(vault: Path, repo: Path | str) -> Path:
    slug = project_slug(repo)
    base = Path(vault) / "01_Projects" / slug
    for sub in ("sessions", "decisions"):
        (base / sub).mkdir(parents=True, exist_ok=True)
    idx = base / "project-index.md"
    if not idx.exists():
        idx.write_text(f"# Project: {slug}\n\n", encoding="utf-8")
    return base


def create_session_summary(
    vault: Path, *, repo: Path | str, title: str, body: str,
    date_str: str, seq: int, sensitivity: str = "work",
) -> Path:
    base = ensure_project(vault, repo)
    sid = schema.make_id("session", date_str, seq)
    meta = {
        "type": "session", "id": sid, "repo": project_slug(repo),
        "title": title, "sensitivity": sensitivity, "created": date_str,
    }
    path = base / "sessions" / f"{sid}.md"
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.append_log(vault, "ingest-log", f"session {sid} ({project_slug(repo)})")
    return path


def create_decision(
    vault: Path, *, repo: Path | str, title: str, context: str, decision: str,
    alternatives: str, consequences: str, date_str: str, seq: int,
    sensitivity: str = "work",
) -> Path:
    base = ensure_project(vault, repo)
    did = schema.make_id("decision", date_str, seq)
    meta = {
        "type": "decision", "id": did, "repo": project_slug(repo),
        "title": title, "status": "accepted", "sensitivity": sensitivity,
        "created": date_str,
    }
    body = (
        f"## Context\n\n{context}\n\n## Decision\n\n{decision}\n\n"
        f"## Alternatives\n\n{alternatives}\n\n## Consequences\n\n{consequences}\n"
    )
    path = base / "decisions" / f"{did}.md"
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_projects.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/core/projects.py tests/test_projects.py
git commit -m "feat: project sessions and ADRs"
```

---

## Task 3: Relax sensitivity (refuse → tag) across core + permissions

**Files:** Modify `wiki_agent/core/sources.py`, `wiki_agent/core/claims.py`, `wiki_agent/core/wiki.py`, `wiki_agent/permissions.py`, `tests/test_sources.py`, `tests/test_permissions.py`

- [ ] **Step 1: Update the two affected tests first**

In `tests/test_sources.py`, REPLACE the existing `test_create_source_refuses_work` function with:
```python
def test_create_source_tags_work(vault):
    path = sources.create_source(
        vault, origin="coding_agent", content="company code",
        sensitivity="work", date_str="2026-06-07", seq=2,
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["sensitivity"] == "work"
```

In `tests/test_permissions.py`, REPLACE the existing `test_deny_work_source` function with:
```python
@pytest.mark.asyncio
async def test_allow_work_source(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__create_source",
                     {"origin": "x", "content": "y", "sensitivity": "work"}, None)
    assert res.behavior == "allow"
```

- [ ] **Step 2: Run to verify the updated tests now FAIL against old code**

Run: `uv run pytest tests/test_sources.py::test_create_source_tags_work tests/test_permissions.py::test_allow_work_source -v`
Expected: FAIL (old code raises PermissionError / denies).

- [ ] **Step 3: Modify `wiki_agent/core/sources.py`** — replace the whole `create_source` function with this (the `sensitivity != "personal"` refusal is removed; the tag remains):

```python
def create_source(
    vault: Path, *, origin: str, content: str, sensitivity: str = "personal",
    date_str: str, seq: int, url: str | None = None, subdir: str = "raw",
) -> Path:
    if sensitivity not in schema.SENSITIVITIES:
        raise ValueError(f"unknown sensitivity: {sensitivity}")
    sid = schema.make_id("source", date_str, seq)
    meta = {
        "type": "source", "id": sid, "origin": origin,
        "captured_at": date_str, "sensitivity": sensitivity, "url": url or "",
    }
    body = f"## Raw\n\n{content}\n"
    path = Path(vault) / "00_Inbox" / subdir / f"{sid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.append_log(vault, "ingest-log", f"captured {sid} from {origin} [{sensitivity}]")
    return path
```

- [ ] **Step 4: Modify `wiki_agent/core/claims.py`** — replace the `create_claim` function with this (adds `sensitivity` param + meta field; everything else unchanged):

```python
def create_claim(
    vault: Path, *, claim: str, claim_type: str, source_refs: list[str],
    date_str: str, seq: int, proposed_status: str | None = None,
    speaker: str | None = None, sensitivity: str = "personal",
) -> Path:
    schema.validate_claim_type(claim_type)
    cid = schema.make_id("claim", date_str, seq)
    meta = {
        "type": "claim", "id": cid, "claim_type": claim_type,
        "status": "unverified", "proposed_status": proposed_status or "",
        "claim": claim, "speaker": speaker or "", "source_refs": source_refs,
        "evidence_refs": [], "sensitivity": sensitivity,
        "created": date_str, "updated": date_str,
    }
    path = Path(vault) / "10_Claims/pending" / f"{cid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema.render_doc(meta, f"## Claim\n\n{claim}\n"), encoding="utf-8")
    index.update_index(vault, "claim-index", cid, f"{claim[:60]} — unverified")
    return path
```

- [ ] **Step 5: Modify `wiki_agent/core/wiki.py`** — replace the `create_wiki_page` function with this (adds `sensitivity` param + meta field):

```python
def create_wiki_page(
    vault: Path, *, name: str, page_type: str, body: str,
    claim_refs: list[str], date_str: str, domain: list[str] | None = None,
    sensitivity: str = "personal",
) -> Path:
    if page_type not in schema.WIKI_PAGE_TYPES:
        raise ValueError(f"unknown page_type: {page_type}")
    meta = {
        "type": page_type, "name": name, "domain": domain or [],
        "status": "draft", "sensitivity": sensitivity,
        "created": date_str, "updated": date_str,
        "claim_refs": claim_refs, "code_refs": [],
    }
    path = Path(vault) / "03_Resources" / _TYPE_DIR[page_type] / f"{_slug(name)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.update_index(vault, "wiki-index", _slug(name), f"{name} ({page_type})")
    return path
```

- [ ] **Step 6: Modify `wiki_agent/permissions.py`** — replace the whole `make_can_use_tool` function with this (the `create_source` work-deny block is removed; the verified gate stays):

```python
def make_can_use_tool(vault: Path):
    async def can_use_tool(tool_name: str, input_data: dict, context):
        if tool_name == "mcp__wiki__promote_claim":
            if input_data.get("target_status") == "verified":
                if not input_data.get("approved_by_human") and not input_data.get("evidence_refs"):
                    return PermissionResultDeny(
                        message="verified requires human approval or evidence (principle 9)"
                    )
        return PermissionResultAllow(updated_input=input_data)

    return can_use_tool
```

- [ ] **Step 7: Run the full suite to verify the change is consistent**

Run: `uv run pytest -q`
Expected: all pass (the two updated tests now pass; the verified-gate tests still pass).

- [ ] **Step 8: Commit**

```bash
git add wiki_agent/core/sources.py wiki_agent/core/claims.py wiki_agent/core/wiki.py wiki_agent/permissions.py tests/test_sources.py tests/test_permissions.py
git commit -m "feat: relax sensitivity from hard-gate to tag (unified vault)"
```

---

## Task 4: tools.py — add wrap tools + names

**Files:** Modify `wiki_agent/tools.py`, `tests/test_tools.py`

- [ ] **Step 1: Update the test** — append to `tests/test_tools.py`:
```python
def test_wrap_tool_names_present():
    names = tools.WIKI_TOOL_NAMES
    assert "mcp__wiki__collect_git_session" in names
    assert "mcp__wiki__create_session_summary" in names
    assert "mcp__wiki__create_decision" in names
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_tools.py::test_wrap_tool_names_present -v`
Expected: FAIL (names absent).

- [ ] **Step 3: Modify `wiki_agent/tools.py`**

3a. Update the import line `from .core import claims, learning, sources, wiki` to:
```python
from .core import claims, git, learning, projects, sources, wiki
```

3b. Append three entries to the `WIKI_TOOL_NAMES` list:
```python
    "mcp__wiki__collect_git_session",
    "mcp__wiki__create_session_summary",
    "mcp__wiki__create_decision",
```

3c. Inside `build_wiki_server`, add these three tool definitions BEFORE the final `return create_sdk_mcp_server(...)`:
```python
    @tool("collect_git_session",
          "Read a repo's diff/commits/changed files for base..head (read-only)",
          {"repo": str, "base": str, "head": str})
    async def collect_git_session(args):
        s = git.collect_session(args["repo"], args["base"], args.get("head", "HEAD"))
        text = (
            "commits:\n" + "\n".join(f"- {c['sha'][:8]} {c['subject']}" for c in s["commits"])
            + "\n\nchanged_files:\n" + "\n".join(s["changed_files"])
            + "\n\ndiff:\n" + s["diff"][:20000]
        )
        return _ok(text)

    @tool("create_session_summary",
          "Write a session summary under 01_Projects/<repo>/sessions (sensitivity=work)",
          {"repo": str, "title": str, "body": str})
    async def create_session_summary(args):
        slug = projects.project_slug(args["repo"])
        p = projects.create_session_summary(
            vault, repo=args["repo"], title=args["title"], body=args["body"],
            date_str=schema.today_str(),
            seq=_next_seq(vault, f"01_Projects/{slug}/sessions", "session"),
        )
        return _ok(f"created {p.stem}")

    @tool("create_decision",
          "Write an ADR under 01_Projects/<repo>/decisions (sensitivity=work)",
          {"repo": str, "title": str, "context": str, "decision": str,
           "alternatives": str, "consequences": str})
    async def create_decision(args):
        slug = projects.project_slug(args["repo"])
        p = projects.create_decision(
            vault, repo=args["repo"], title=args["title"], context=args["context"],
            decision=args["decision"], alternatives=args["alternatives"],
            consequences=args["consequences"], date_str=schema.today_str(),
            seq=_next_seq(vault, f"01_Projects/{slug}/decisions", "decision"),
        )
        return _ok(f"created {p.stem}")
```

3d. Add the three new tool objects to the `tools=[...]` list in the `return create_sdk_mcp_server(...)` call:
```python
               create_learning_item, list_due_reviews, record_review,
               collect_git_session, create_session_summary, create_decision],
```
(append the three names after the existing `record_review`).

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_tools.py -v`
Expected: 3 passed (incl. the new one).

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/tools.py tests/test_tools.py
git commit -m "feat: wrap MCP tools (git session, session summary, ADR)"
```

---

## Task 5: wrap subagent + prompt

**Files:** Create `wiki_agent/prompts/wrap.md`; Modify `wiki_agent/subagents.py`, `tests/test_subagents.py`

- [ ] **Step 1: Write `wiki_agent/prompts/wrap.md`**

```markdown
You wrap up a finished coding session into durable knowledge. Inputs: a repo path and a
base..head range (and possibly a pasted transcript).

Steps:
1. Call collect_git_session(repo, base, head) to get the diff, changed files, and commits.
2. If a transcript was provided, use it for intent/rationale; otherwise infer from diff + commits.
3. Optionally run the repo's tests via Bash and note results.
4. Produce, in this order:
   - A session summary via create_session_summary(repo, title, body). The body covers: goal,
     what changed, key files/diff highlights, tests run + results, debugging, and WHY the design
     choices were made.
   - For each real design decision, an ADR via create_decision(repo, title, context, decision,
     alternatives, consequences).
   - Generalized, identifier-stripped concept/pattern pages via create_wiki_page (remove company
     names, internal paths, secrets — keep only reusable knowledge).
   - Learning items via create_learning_item for prerequisites you (the human) should study, plus
     flashcards/quiz/mini-exercise prompts in the item body.

Project-specific artifacts (sessions, ADRs) are tagged sensitivity=work and live under the repo's
project folder. Generalized concepts go to 03_Resources. Never write secrets or raw company code
into 03_Resources or learning items.
```

- [ ] **Step 2: Update the test** — in `tests/test_subagents.py`, REPLACE `test_build_subagents_has_four` with:
```python
def test_build_subagents_has_wrap():
    agents = subagents.build_subagents()
    assert set(agents) == {"ingest", "verify", "answer", "learning", "wrap"}
    assert "Bash" in agents["wrap"].tools
    assert "mcp__wiki__collect_git_session" in agents["wrap"].tools
    # answer still cannot Write
    assert "Write" not in (agents["answer"].tools or [])
```

- [ ] **Step 3: Run to verify it fails**

Run: `uv run pytest tests/test_subagents.py -v`
Expected: FAIL (no `wrap` agent).

- [ ] **Step 4: Modify `wiki_agent/subagents.py`** — add a `wrap` entry to the dict returned by `build_subagents()`, after the `learning` entry (before the closing `}`):
```python
        "wrap": AgentDefinition(
            description="Wrap a coding session into session summary, ADRs, concepts, and learning.",
            prompt=_p("wrap"),
            tools=["Read", "Grep", "Glob", "Bash"] + [t for t in w if any(
                k in t for k in ("collect_git_session", "create_session_summary",
                                 "create_decision", "create_wiki_page", "create_claim",
                                 "create_learning_item"))],
            model="claude-opus-4-8",
        ),
```

- [ ] **Step 5: Run to verify it passes**

Run: `uv run pytest tests/test_subagents.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add wiki_agent/prompts/wrap.md wiki_agent/subagents.py tests/test_subagents.py
git commit -m "feat: wrap subagent and prompt"
```

---

## Task 6: /wrap route + Wrap tab

**Files:** Modify `wiki_agent/app.py`, `wiki_agent/web/index.html`, `tests/test_app.py`

- [ ] **Step 1: Update the test** — append to `tests/test_app.py`:
```python
def test_wrap_route_exists(vault):
    app = create_app(vault)
    routes = {r.path for r in app.routes}
    assert "/wrap" in routes
```

- [ ] **Step 2: Run to verify it fails**

Run: `uv run pytest tests/test_app.py::test_wrap_route_exists -v`
Expected: FAIL (`/wrap` not registered).

- [ ] **Step 3: Modify `wiki_agent/app.py`** — replace the entire `_attach_chat` function with this (adds `/wrap` alongside `/chat`):
```python
def _attach_chat(app: FastAPI, vault: Path) -> None:
    from .agent import WikiSession

    class ChatBody(BaseModel):
        prompt: str

    class WrapBody(BaseModel):
        repo: str
        base: str
        head: str = "HEAD"
        transcript: str | None = None

    async def _stream(prompt: str):
        async with WikiSession(vault) as session:
            async for chunk in session.ask(prompt):
                yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    @app.post("/chat")
    async def chat(body: ChatBody):
        return StreamingResponse(_stream(body.prompt), media_type="text/event-stream")

    @app.post("/wrap")
    async def wrap(body: WrapBody):
        prompt = (
            "Use the wrap subagent to wrap up this coding session. "
            f"repo={body.repo}, range={body.base}..{body.head}. "
            "First call collect_git_session, then produce a session summary, any ADRs, "
            "generalized concept/pattern pages, and learning items."
        )
        if body.transcript:
            prompt += f"\n\nTranscript (optional context):\n{body.transcript}"
        return StreamingResponse(_stream(prompt), media_type="text/event-stream")
```

- [ ] **Step 4: Run to verify it passes**

Run: `uv run pytest tests/test_app.py -v`
Expected: all pass (incl. `test_wrap_route_exists`).

- [ ] **Step 5: Add the Wrap tab to `wiki_agent/web/index.html`**

5a. Add a nav button — change the `<nav>` block so it reads (add the Wrap button before Verify):
```html
  <nav>
    <button data-tab="chat" class="active">Chat</button>
    <button data-tab="capture">Capture</button>
    <button data-tab="wrap">Wrap</button>
    <button data-tab="verify">Verify</button>
    <button data-tab="review">Review</button>
  </nav>
```

5b. Add a panel — insert this `<section>` right after the `capture` section's closing `</section>`:
```html
    <section id="wrap" class="panel">
      <input id="wrapRepo" style="width:60%" placeholder="repo 절대경로 (예: /Users/me/work/myrepo)" />
      <input id="wrapBase" style="width:18%" placeholder="base (예: HEAD~1)" />
      <input id="wrapHead" style="width:18%" placeholder="head (기본 HEAD)" />
      <textarea id="wrapTranscript" placeholder="(선택) 코딩 에이전트 transcript"></textarea>
      <button onclick="wrapRun()">Wrap</button>
      <div id="wrapLog" style="white-space:pre-wrap;border:1px solid #ccc;padding:.5rem;min-height:6rem"></div>
    </section>
```

5c. Add the JS handler — insert this function inside the `<script>` block, right after the `send()` function:
```javascript
    async function wrapRun() {
      const body = {
        repo: document.getElementById('wrapRepo').value,
        base: document.getElementById('wrapBase').value || 'HEAD~1',
        head: document.getElementById('wrapHead').value || 'HEAD',
        transcript: document.getElementById('wrapTranscript').value || null,
      };
      const log = document.getElementById('wrapLog');
      log.textContent = 'wrapping...\n';
      const res = await fetch('/wrap', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
      const reader = res.body.getReader(); const dec = new TextDecoder();
      while (true) { const {value, done} = await reader.read(); if (done) break;
        dec.decode(value).split('\n').forEach(l => {
          if (l.startsWith('data: ') && l !== 'data: [DONE]') log.textContent += l.slice(6);
        });
      }
    }
```

- [ ] **Step 6: Verify the UI still serves and includes the Wrap tab**

Run:
```bash
uv run python -c "from fastapi.testclient import TestClient; from wiki_agent.app import create_app; import pathlib; c=TestClient(create_app(pathlib.Path('.'))); r=c.get('/'); assert r.status_code==200 and 'data-tab=\"wrap\"' in r.text; print('Wrap tab OK')"
```
Expected: prints `Wrap tab OK`.

- [ ] **Step 7: Commit**

```bash
git add wiki_agent/app.py wiki_agent/web/index.html tests/test_app.py
git commit -m "feat: /wrap route and Wrap tab"
```

---

## Task 7: Full suite + live e2e verification

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest -q`
Expected: all green.

- [ ] **Step 2: Live wrap smoke against this repo itself (it is a git repo)**

This vault is itself a git repo, so we can wrap its own last commit as a smoke test. Run:
```bash
cd /Users/gyubin.son/workspace/dev/personal-wiki
cat > /tmp/wrap_smoke.py <<'PY'
import asyncio, pathlib
from wiki_agent.agent import WikiSession

async def main():
    async with WikiSession(pathlib.Path.cwd()) as s:
        out = []
        prompt = ("Use the wrap subagent. repo=" + str(pathlib.Path.cwd()) +
                  ", range=HEAD~1..HEAD. Call collect_git_session first, then create exactly one "
                  "session summary with create_session_summary (title 'smoke'). Keep it short.")
        async for chunk in s.ask(prompt):
            out.append(chunk)
        print("OUT:", "".join(out)[:400])

asyncio.run(asyncio.wait_for(main(), timeout=240))
PY
uv run python /tmp/wrap_smoke.py 2>&1 | tail -10
rm -f /tmp/wrap_smoke.py
```
Expected: a session file appears under `01_Projects/personal-wiki/sessions/`. Verify:
```bash
ls 01_Projects/personal-wiki/sessions/ 2>&1
```
Expected: at least one `session-*.md`. (If the agent chose a different repo slug, check `01_Projects/`.)

- [ ] **Step 3: Manual UI check (optional, by the human)**

`uv run wiki serve` → Wrap tab → enter a real work repo path + `HEAD~1` + `HEAD` → Wrap → confirm
session summary under `01_Projects/<repo>/sessions/`, any ADRs under `decisions/`, generalized concepts
under `03_Resources/`, and learning cards under `30_Learning/` — visible in Obsidian too.

- [ ] **Step 4: Commit any cleanup (if needed)**

If the smoke run created stray files you want to drop, remove them; otherwise nothing to commit.

---

## Self-Review

**Spec coverage:**
- Input (diff primary + optional transcript) → Task 1 (`collect_git_session`) + Task 6 (`/wrap` body has `transcript`). ✓
- Storage under `01_Projects/<repo>/` → Task 2. ✓
- sensitivity tag (refuse→tag) → Task 3 (sources/claims/wiki/permissions). ✓
- 4 artifacts: session summary + ADR (Task 2/4/5), concept/pattern (reuse `create_wiki_page`, wrap prompt Task 5), learning (reuse `create_learning_item`, wrap prompt Task 5). ✓
- Agent wiring: tools (Task 4), `wrap` subagent (Task 5), `allowed_tools` auto via splat (noted, no agent.py change). ✓
- Web /wrap + Wrap tab → Task 6. ✓
- Tests: git/projects new (Task 1/2), sensitivity updates (Task 3), tools/subagents/app updates (Task 4/5/6), e2e (Task 7). ✓

**Placeholder scan:** No TBD/TODO; every code step shows full code. The "Similar to phase 1" risk is avoided — full function bodies are repeated where modified.

**Type/name consistency:** `collect_session` (core) vs tool `collect_git_session` (intentional, distinct names — core fn vs MCP tool). `project_slug`/`ensure_project`/`create_session_summary`/`create_decision` used identically in Task 2 (def), Task 4 (tool calls). `WIKI_TOOL_NAMES` additions match the `@tool` names (`collect_git_session`, `create_session_summary`, `create_decision`). `_next_seq`/`_ok` already exist in `tools.py` from phase 1. Subagent set assertion updated to include `wrap`. `_attach_chat` fully replaced (single definition preserved).
