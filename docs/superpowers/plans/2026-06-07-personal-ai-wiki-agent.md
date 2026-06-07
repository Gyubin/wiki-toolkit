# Personal AI Wiki Agent — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local conversational AI agent + web app that turns raw clips into verified, source-linked knowledge and learning cards in a Markdown vault, per `docs/superpowers/specs/2026-06-07-personal-ai-wiki-agent-design.md`.

**Architecture:** One FastAPI process serves a no-build web UI (Chat/Capture/Verify/Review) and wraps a `claude-agent-sdk` `ClaudeSDKClient` session. Integrity logic lives in pure functions under `wiki_agent/core/`, wrapped twice — as `@tool`s for the agent and called directly by FastAPI routes for buttons. Obsidian reads the same vault on disk.

**Tech Stack:** Python 3.11+, `uv`, `claude-agent-sdk` (needs Claude Code CLI at runtime), FastAPI + uvicorn, PyYAML, httpx + markdownify (URL capture), pytest. Model `claude-opus-4-8`.

---

## File Structure

```
personal-ai-wiki/                      # existing Obsidian vault, becomes git repo
  wiki_agent/
    __init__.py
    __main__.py        # `uv run wiki [init|serve]`
    schema.py          # enums, IDs, frontmatter render/parse — single source of truth
    core/
      __init__.py
      scaffold.py      # create vault folders + templates
      index.py         # append_log, update_index
      sources.py       # create_source, triage_record, html_to_markdown
      claims.py        # create_claim, find_similar_claim, promote_claim (gate), set_claim_status, list_pending
      wiki.py          # create_wiki_page, update_wiki_page
      learning.py      # create_learning_item, list_due_reviews, record_review
    tools.py           # @tool wrappers + build_wiki_server(vault)
    permissions.py     # make_can_use_tool(vault)
    prompts/           # system.md + ingest.md/verify.md/answer.md/learning.md
    subagents.py       # build_subagents()
    agent.py           # build_options(vault), WikiSession
    app.py             # FastAPI app + routes
    web/index.html     # 4-tab UI (no build step)
  tests/
    conftest.py        # vault fixture
    test_schema.py test_scaffold.py test_index.py test_sources.py
    test_claims.py test_wiki.py test_learning.py test_permissions.py test_app.py
  pyproject.toml
  .gitignore
```

Each `core/` module = one responsibility, pure functions (take `vault: Path` + explicit `date_str`, no hidden global state, no LLM). `tools.py`/`app.py` are thin adapters over `core/`.

---

## Task 1: Project setup

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `wiki_agent/__init__.py`, `wiki_agent/core/__init__.py`, `tests/__init__.py`, `tests/test_smoke.py`

- [ ] **Step 1: Initialize git and uv project**

Run:
```bash
cd /Users/gyubin.son/workspace/dev/personal-wiki
git init
uv init --package --name wiki-agent --python 3.11 .
```
If `uv init` complains the directory is non-empty, skip it and create `pyproject.toml` manually in Step 2.

- [ ] **Step 2: Write `pyproject.toml`**

```toml
[project]
name = "wiki-agent"
version = "0.1.0"
description = "Personal AI Wiki + learning agent over a Markdown vault"
requires-python = ">=3.11"
dependencies = [
    "claude-agent-sdk>=0.1.0",
    "fastapi>=0.110",
    "uvicorn>=0.29",
    "pyyaml>=6.0",
    "httpx>=0.27",
    "markdownify>=0.11",
]

[project.scripts]
wiki = "wiki_agent.__main__:main"

[dependency-groups]
dev = ["pytest>=8.0", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
asyncio_mode = "auto"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"
```

- [ ] **Step 3: Write `.gitignore`**

```gitignore
__pycache__/
*.pyc
.venv/
.pytest_cache/
*.egg-info/
.obsidian/workspace*.json
.obsidian/cache
```

- [ ] **Step 4: Create package init files**

`wiki_agent/__init__.py`:
```python
"""Personal AI Wiki agent."""
```
`wiki_agent/core/__init__.py`:
```python
```
`tests/__init__.py`:
```python
```

- [ ] **Step 5: Write the smoke test** — `tests/test_smoke.py`

```python
def test_package_imports():
    import wiki_agent
    assert wiki_agent is not None
```

- [ ] **Step 6: Sync and run**

Run:
```bash
uv sync
uv run pytest tests/test_smoke.py -v
```
Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "chore: scaffold uv project for wiki-agent"
```

---

## Task 2: schema.py — enums, IDs, frontmatter

**Files:**
- Create: `wiki_agent/schema.py`, `tests/test_schema.py`

- [ ] **Step 1: Write the failing test** — `tests/test_schema.py`

```python
import pytest
from wiki_agent import schema


def test_enums_match_design():
    assert "technical_fact" in schema.CLAIM_TYPES
    assert "fact" not in schema.CLAIM_TYPES  # renamed in design
    assert "accepted_for_now" in schema.CLAIM_STATUSES
    assert "deprecated" in schema.CLAIM_STATUSES
    assert schema.SENSITIVITIES == ("personal", "work", "confidential")


def test_make_id():
    assert schema.make_id("claim", "2026-06-07", 1) == "claim-20260607-001"
    assert schema.make_id("source", "2026-06-07", 42) == "source-20260607-042"


def test_render_and_parse_roundtrip():
    meta = {"type": "claim", "id": "claim-20260607-001", "status": "unverified"}
    body = "## Claim\n\n어떤 주장이다.\n"
    text = schema.render_doc(meta, body)
    assert text.startswith("---\n")
    parsed_meta, parsed_body = schema.parse_doc(text)
    assert parsed_meta == meta
    assert parsed_body.strip() == body.strip()


def test_validate_rejects_unknown():
    with pytest.raises(ValueError):
        schema.validate_claim_type("nonsense")
    with pytest.raises(ValueError):
        schema.validate_status("nonsense")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schema.py -v`
Expected: FAIL (module/attrs missing).

- [ ] **Step 3: Write `wiki_agent/schema.py`**

```python
"""Single source of truth: enums, IDs, frontmatter (mirrors design doc §6)."""
from __future__ import annotations

import datetime as _dt
import yaml

CLAIM_TYPES = (
    "technical_fact", "person_claim", "opinion", "hypothesis",
    "decision", "observation", "instruction", "misconception",
)
CLAIM_STATUSES = (
    "unverified", "verified", "attributed", "opinion", "partially_true",
    "accepted_for_now", "disputed", "outdated", "deprecated", "rejected",
)
SENSITIVITIES = ("personal", "work", "confidential")
WIKI_PAGE_TYPES = ("concept", "pattern", "glossary", "comparison", "misconception")
LEARNING_LEVELS = ("unknown", "seen", "explained", "used", "reviewed", "can-teach")


def today_str() -> str:
    return _dt.date.today().isoformat()


def make_id(prefix: str, date_str: str, seq: int) -> str:
    compact = date_str.replace("-", "")
    return f"{prefix}-{compact}-{seq:03d}"


def render_doc(meta: dict, body: str) -> str:
    fm = yaml.safe_dump(meta, sort_keys=False, allow_unicode=True).rstrip("\n")
    return f"---\n{fm}\n---\n\n{body.rstrip()}\n"


def parse_doc(text: str) -> tuple[dict, str]:
    if not text.startswith("---"):
        return {}, text
    _, fm, body = text.split("---", 2)
    meta = yaml.safe_load(fm) or {}
    return meta, body.lstrip("\n")


def validate_claim_type(t: str) -> str:
    if t not in CLAIM_TYPES:
        raise ValueError(f"unknown claim_type: {t}")
    return t


def validate_status(s: str) -> str:
    if s not in CLAIM_STATUSES:
        raise ValueError(f"unknown status: {s}")
    return s
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schema.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/schema.py tests/test_schema.py
git commit -m "feat: schema enums, ids, frontmatter helpers"
```

---

## Task 3: Vault scaffold + test fixture

**Files:**
- Create: `wiki_agent/core/scaffold.py`, `tests/conftest.py`, `tests/test_scaffold.py`

- [ ] **Step 1: Write the failing test** — `tests/test_scaffold.py`

```python
from wiki_agent.core import scaffold


def test_scaffold_creates_dirs(tmp_path):
    scaffold.scaffold_vault(tmp_path)
    for d in [
        "00_Inbox/raw", "00_Inbox/browser-clips",
        "10_Claims/pending", "10_Claims/verified",
        "30_Learning/flashcards", "06_Metadata/indexes", "06_Metadata/logs",
        "03_Resources/Concepts",
    ]:
        assert (tmp_path / d).is_dir(), d
    assert (tmp_path / "06_Metadata/indexes/claim-index.md").exists()
    assert (tmp_path / "06_Metadata/logs/ingest-log.md").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_scaffold.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/core/scaffold.py`**

```python
"""Create the vault folder structure and seed index/log files."""
from __future__ import annotations

from pathlib import Path

DIRS = [
    "00_Inbox/raw", "00_Inbox/browser-clips", "00_Inbox/chatgpt-gemini-clips",
    "01_Projects", "02_Areas",
    "03_Resources/Concepts", "03_Resources/Patterns", "03_Resources/Glossary",
    "03_Resources/Comparisons", "03_Resources/Misconceptions",
    "10_Claims/pending", "10_Claims/verified", "10_Claims/attributed",
    "10_Claims/disputed", "10_Claims/rejected", "10_Claims/outdated",
    "30_Learning/skill-maps", "30_Learning/flashcards", "30_Learning/quizzes",
    "30_Learning/exercises", "30_Learning/weekly-synthesis",
    "06_Metadata/templates", "06_Metadata/schema",
    "06_Metadata/indexes", "06_Metadata/logs",
]

SEED_FILES = {
    "06_Metadata/indexes/claim-index.md": "# Claim Index\n\n",
    "06_Metadata/indexes/wiki-index.md": "# Wiki Index\n\n",
    "06_Metadata/indexes/learning-index.md": "# Learning Index\n\n",
    "06_Metadata/logs/ingest-log.md": "# Ingest Log\n\n",
}


def scaffold_vault(vault: Path) -> None:
    vault = Path(vault)
    for d in DIRS:
        (vault / d).mkdir(parents=True, exist_ok=True)
    for rel, content in SEED_FILES.items():
        p = vault / rel
        if not p.exists():
            p.write_text(content, encoding="utf-8")
```

- [ ] **Step 4: Write `tests/conftest.py`**

```python
import pytest
from wiki_agent.core import scaffold


@pytest.fixture
def vault(tmp_path):
    scaffold.scaffold_vault(tmp_path)
    return tmp_path
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_scaffold.py -v`
Expected: 1 passed.

- [ ] **Step 6: Commit**

```bash
git add wiki_agent/core/scaffold.py tests/conftest.py tests/test_scaffold.py
git commit -m "feat: vault scaffold and test fixture"
```

---

## Task 4: core/index.py — append_log, update_index

**Files:**
- Create: `wiki_agent/core/index.py`, `tests/test_index.py`

- [ ] **Step 1: Write the failing test** — `tests/test_index.py`

```python
from wiki_agent.core import index


def test_append_log(vault):
    index.append_log(vault, "ingest-log", "first entry")
    index.append_log(vault, "ingest-log", "second entry")
    text = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "first entry" in text
    assert "second entry" in text


def test_update_index_upserts(vault):
    index.update_index(vault, "claim-index", "claim-20260607-001", "claim A — unverified")
    index.update_index(vault, "claim-index", "claim-20260607-001", "claim A — verified")
    text = (vault / "06_Metadata/indexes/claim-index.md").read_text(encoding="utf-8")
    assert text.count("claim-20260607-001") == 1  # upsert, not duplicate
    assert "verified" in text
    assert "unverified" not in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_index.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/core/index.py`**

```python
"""Append-only logs and upsert-by-id index lines under 06_Metadata."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path


def append_log(vault: Path, logname: str, line: str) -> None:
    p = Path(vault) / "06_Metadata/logs" / f"{logname}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    ts = _dt.datetime.now().isoformat(timespec="seconds")
    with p.open("a", encoding="utf-8") as f:
        f.write(f"- {ts} — {line}\n")


def update_index(vault: Path, indexname: str, entry_id: str, line: str) -> None:
    p = Path(vault) / "06_Metadata/indexes" / f"{indexname}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    header = p.read_text(encoding="utf-8") if p.exists() else f"# {indexname}\n\n"
    kept = [
        ln for ln in header.splitlines()
        if not (ln.startswith("- ") and entry_id in ln)
    ]
    kept.append(f"- [{entry_id}] {line}")
    p.write_text("\n".join(kept) + "\n", encoding="utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_index.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/core/index.py tests/test_index.py
git commit -m "feat: core index/log helpers"
```

---

## Task 5: core/sources.py — capture + triage + html→md

**Files:**
- Create: `wiki_agent/core/sources.py`, `tests/test_sources.py`

- [ ] **Step 1: Write the failing test** — `tests/test_sources.py`

```python
import pytest
from wiki_agent.core import sources
from wiki_agent import schema


def test_create_source_personal(vault):
    path = sources.create_source(
        vault, origin="chatgpt", content="raw conversation text",
        sensitivity="personal", date_str="2026-06-07", seq=1, url="http://x",
    )
    assert path.exists()
    meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["type"] == "source"
    assert meta["id"] == "source-20260607-001"
    assert meta["sensitivity"] == "personal"
    assert "raw conversation text" in body
    log = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "source-20260607-001" in log


def test_create_source_refuses_work(vault):
    with pytest.raises(PermissionError):
        sources.create_source(
            vault, origin="coding_agent", content="company code",
            sensitivity="work", date_str="2026-06-07", seq=2,
        )


def test_triage_record(vault):
    sources.triage_record(vault, "source-20260607-001", "deep", "2026-06-07")
    log = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "triage" in log and "deep" in log


def test_html_to_markdown():
    md = sources.html_to_markdown("<h1>Title</h1><p>Hello <b>world</b></p>")
    assert "Title" in md
    assert "world" in md
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_sources.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/core/sources.py`**

```python
"""Raw capture (sources), triage records, and URL/html conversion."""
from __future__ import annotations

from pathlib import Path

from markdownify import markdownify

from .. import schema
from . import index


def create_source(
    vault: Path, *, origin: str, content: str, sensitivity: str = "personal",
    date_str: str, seq: int, url: str | None = None, subdir: str = "raw",
) -> Path:
    if sensitivity not in schema.SENSITIVITIES:
        raise ValueError(f"unknown sensitivity: {sensitivity}")
    if sensitivity != "personal":
        raise PermissionError(
            "work/confidential content must go to the work vault, not this personal vault"
        )
    sid = schema.make_id("source", date_str, seq)
    meta = {
        "type": "source", "id": sid, "origin": origin,
        "captured_at": date_str, "sensitivity": sensitivity, "url": url or "",
    }
    body = f"## Raw\n\n{content}\n"
    path = Path(vault) / "00_Inbox" / subdir / f"{sid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.append_log(vault, "ingest-log", f"captured {sid} from {origin}")
    return path


def triage_record(vault: Path, source_id: str, decision: str, date_str: str) -> None:
    if decision not in ("drop", "keep-as-link", "deep"):
        raise ValueError(f"unknown triage decision: {decision}")
    index.append_log(vault, "ingest-log", f"triage {source_id} -> {decision}")


def html_to_markdown(html: str) -> str:
    return markdownify(html, heading_style="ATX").strip()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_sources.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/core/sources.py tests/test_sources.py
git commit -m "feat: source capture, triage, html->md"
```

---

## Task 6: core/claims.py — create, dedup, promote (gate), status

**Files:**
- Create: `wiki_agent/core/claims.py`, `tests/test_claims.py`

- [ ] **Step 1: Write the failing test** — `tests/test_claims.py`

```python
import pytest
from wiki_agent.core import claims
from wiki_agent import schema


def _make(vault, seq=1, text="React useEffect runs after paint"):
    return claims.create_claim(
        vault, claim=text, claim_type="technical_fact",
        source_refs=["source-20260607-001"], date_str="2026-06-07", seq=seq,
    )


def test_create_claim_is_unverified(vault):
    path = _make(vault)
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["status"] == "unverified"
    assert meta["id"] == "claim-20260607-001"
    assert (vault / "10_Claims/pending/claim-20260607-001.md").exists()


def test_create_claim_validates_type(vault):
    with pytest.raises(ValueError):
        claims.create_claim(
            vault, claim="x", claim_type="bogus", source_refs=[],
            date_str="2026-06-07", seq=9,
        )


def test_promote_to_verified_requires_approval_or_evidence(vault):
    _make(vault)
    with pytest.raises(PermissionError):
        claims.promote_claim(
            vault, "claim-20260607-001", target_status="verified",
            date_str="2026-06-07",
        )


def test_promote_with_human_approval(vault):
    _make(vault)
    path = claims.promote_claim(
        vault, "claim-20260607-001", target_status="verified",
        approved_by_human=True, date_str="2026-06-07",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["status"] == "verified"
    assert (vault / "10_Claims/verified/claim-20260607-001.md").exists()
    assert not (vault / "10_Claims/pending/claim-20260607-001.md").exists()


def test_promote_with_evidence(vault):
    _make(vault)
    path = claims.promote_claim(
        vault, "claim-20260607-001", target_status="verified",
        evidence_refs=["repo:src/x.ts:12"], date_str="2026-06-07",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["evidence_refs"] == ["repo:src/x.ts:12"]


def test_find_similar_claim(vault):
    _make(vault, seq=1, text="React useEffect runs after paint")
    _make(vault, seq=2, text="react USEEFFECT runs after paint!!")
    hits = claims.find_similar_claim(vault, "React useEffect runs after paint")
    assert "claim-20260607-001" in hits


def test_list_pending(vault):
    _make(vault, seq=1)
    rows = claims.list_pending(vault)
    assert any(r["id"] == "claim-20260607-001" for r in rows)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_claims.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/core/claims.py`**

```python
"""Claim lifecycle: create (unverified), dedup, promote (gated), status changes."""
from __future__ import annotations

import re
from pathlib import Path

from .. import schema
from . import index

_STATUS_DIR = {
    "unverified": "pending", "verified": "verified", "attributed": "attributed",
    "disputed": "disputed", "rejected": "rejected", "outdated": "outdated",
    "deprecated": "outdated", "partially_true": "pending",
    "accepted_for_now": "pending", "opinion": "attributed",
}


def _find_file(vault: Path, claim_id: str) -> Path:
    for sub in set(_STATUS_DIR.values()):
        p = Path(vault) / "10_Claims" / sub / f"{claim_id}.md"
        if p.exists():
            return p
    raise FileNotFoundError(claim_id)


def normalize_key(text: str, speaker: str | None = None) -> str:
    toks = re.findall(r"[a-z0-9]+", text.lower())
    return " ".join(sorted(toks[:8])) + (f"|{speaker.lower()}" if speaker else "")


def create_claim(
    vault: Path, *, claim: str, claim_type: str, source_refs: list[str],
    date_str: str, seq: int, proposed_status: str | None = None,
    speaker: str | None = None,
) -> Path:
    schema.validate_claim_type(claim_type)
    cid = schema.make_id("claim", date_str, seq)
    meta = {
        "type": "claim", "id": cid, "claim_type": claim_type,
        "status": "unverified", "proposed_status": proposed_status or "",
        "claim": claim, "speaker": speaker or "", "source_refs": source_refs,
        "evidence_refs": [], "created": date_str, "updated": date_str,
    }
    path = Path(vault) / "10_Claims/pending" / f"{cid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema.render_doc(meta, f"## Claim\n\n{claim}\n"), encoding="utf-8")
    index.update_index(vault, "claim-index", cid, f"{claim[:60]} — unverified")
    return path


def find_similar_claim(vault: Path, claim_text: str, speaker: str | None = None) -> list[str]:
    key = normalize_key(claim_text, speaker)
    hits = []
    for p in (Path(vault) / "10_Claims").rglob("claim-*.md"):
        meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        if normalize_key(meta.get("claim", ""), meta.get("speaker") or None) == key:
            hits.append(meta["id"])
    return hits


def promote_claim(
    vault: Path, claim_id: str, *, target_status: str,
    evidence_refs: list[str] | None = None, approved_by_human: bool = False,
    date_str: str,
) -> Path:
    schema.validate_status(target_status)
    if target_status == "verified" and not approved_by_human and not evidence_refs:
        raise PermissionError(
            "verified requires human approval or evidence (design principle 9)"
        )
    src = _find_file(vault, claim_id)
    meta, body = schema.parse_doc(src.read_text(encoding="utf-8"))
    meta["status"] = target_status
    meta["updated"] = date_str
    if evidence_refs:
        meta["evidence_refs"] = evidence_refs
    if target_status == "verified":
        meta["last_verified"] = date_str
    dst_dir = Path(vault) / "10_Claims" / _STATUS_DIR[target_status]
    dst_dir.mkdir(parents=True, exist_ok=True)
    dst = dst_dir / f"{claim_id}.md"
    dst.write_text(schema.render_doc(meta, body), encoding="utf-8")
    if dst != src:
        src.unlink()
    index.update_index(vault, "claim-index", claim_id, f"{meta['claim'][:60]} — {target_status}")
    return dst


def set_claim_status(
    vault: Path, claim_id: str, *, status: str, superseded_by: str | None = None,
    date_str: str,
) -> Path:
    path = promote_claim(
        vault, claim_id, target_status=status, approved_by_human=True, date_str=date_str
    ) if status != "verified" else promote_claim(
        vault, claim_id, target_status=status, approved_by_human=True, date_str=date_str
    )
    if superseded_by:
        meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
        meta["superseded_by"] = [superseded_by]
        path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    return path


def list_pending(vault: Path) -> list[dict]:
    rows = []
    for p in (Path(vault) / "10_Claims/pending").glob("claim-*.md"):
        meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        rows.append({"id": meta["id"], "claim": meta.get("claim", ""),
                     "claim_type": meta.get("claim_type", ""),
                     "proposed_status": meta.get("proposed_status", "")})
    return sorted(rows, key=lambda r: r["id"])
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_claims.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/core/claims.py tests/test_claims.py
git commit -m "feat: claim lifecycle with verified gate and dedup"
```

---

## Task 7: core/wiki.py — wiki pages

**Files:**
- Create: `wiki_agent/core/wiki.py`, `tests/test_wiki.py`

- [ ] **Step 1: Write the failing test** — `tests/test_wiki.py`

```python
import pytest
from wiki_agent.core import wiki
from wiki_agent import schema


def test_create_wiki_page(vault):
    path = wiki.create_wiki_page(
        vault, name="useEffect timing", page_type="concept",
        body="## Verified Knowledge\n\nRuns after paint.\n",
        claim_refs=["claim-20260607-001"], date_str="2026-06-07",
    )
    assert path.exists()
    assert path.parent.name == "Concepts"
    meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["type"] == "concept"
    assert meta["claim_refs"] == ["claim-20260607-001"]
    wi = (vault / "06_Metadata/indexes/wiki-index.md").read_text(encoding="utf-8")
    assert "useEffect timing" in wi


def test_create_wiki_page_rejects_unknown_type(vault):
    with pytest.raises(ValueError):
        wiki.create_wiki_page(
            vault, name="x", page_type="bogus", body="b",
            claim_refs=[], date_str="2026-06-07",
        )


def test_update_wiki_page_adds_claim_refs(vault):
    path = wiki.create_wiki_page(
        vault, name="useEffect timing", page_type="concept",
        body="b", claim_refs=["claim-20260607-001"], date_str="2026-06-07",
    )
    wiki.update_wiki_page(path, add_claim_refs=["claim-20260607-002"])
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert "claim-20260607-002" in meta["claim_refs"]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_wiki.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/core/wiki.py`**

```python
"""Human-readable wiki pages with enforced frontmatter + index entry."""
from __future__ import annotations

import re
from pathlib import Path

from .. import schema
from . import index

_TYPE_DIR = {
    "concept": "Concepts", "pattern": "Patterns", "glossary": "Glossary",
    "comparison": "Comparisons", "misconception": "Misconceptions",
}


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-") or "page"


def create_wiki_page(
    vault: Path, *, name: str, page_type: str, body: str,
    claim_refs: list[str], date_str: str, domain: list[str] | None = None,
) -> Path:
    if page_type not in schema.WIKI_PAGE_TYPES:
        raise ValueError(f"unknown page_type: {page_type}")
    meta = {
        "type": page_type, "name": name, "domain": domain or [],
        "status": "draft", "created": date_str, "updated": date_str,
        "claim_refs": claim_refs, "code_refs": [],
    }
    path = Path(vault) / "03_Resources" / _TYPE_DIR[page_type] / f"{_slug(name)}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.update_index(vault, "wiki-index", _slug(name), f"{name} ({page_type})")
    return path


def update_wiki_page(
    path: Path, *, body: str | None = None,
    add_claim_refs: list[str] | None = None, status: str | None = None,
) -> Path:
    path = Path(path)
    meta, old_body = schema.parse_doc(path.read_text(encoding="utf-8"))
    if add_claim_refs:
        refs = list(meta.get("claim_refs", []))
        for r in add_claim_refs:
            if r not in refs:
                refs.append(r)
        meta["claim_refs"] = refs
    if status:
        meta["status"] = status
    path.write_text(schema.render_doc(meta, body if body is not None else old_body),
                    encoding="utf-8")
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_wiki.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/core/wiki.py tests/test_wiki.py
git commit -m "feat: wiki page create/update"
```

---

## Task 8: core/learning.py — items, due reviews, SRS record

**Files:**
- Create: `wiki_agent/core/learning.py`, `tests/test_learning.py`

- [ ] **Step 1: Write the failing test** — `tests/test_learning.py`

```python
from wiki_agent.core import learning
from wiki_agent import schema


def test_create_learning_item(vault):
    path = learning.create_learning_item(
        vault, topic="useEffect timing", skill_area="frontend",
        date_str="2026-06-07", seq=1, wiki_refs=["useeffect-timing"],
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["type"] == "learning_item"
    assert meta["level"] == "unknown"
    assert meta["next_review"] == "2026-06-07"  # due immediately


def test_due_reviews(vault):
    learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    due = learning.list_due_reviews(vault, "2026-06-08")
    assert any(d["id"] == "learning-20260607-001" for d in due)


def test_record_review_advances_level_and_schedules(vault):
    learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    path = learning.record_review(
        vault, "learning-20260607-001", passed=True, today_str="2026-06-08",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["level"] == "seen"          # advanced one step
    assert meta["next_review"] == "2026-06-09"  # +1 day at first stage


def test_record_review_fail_reschedules_next_day(vault):
    learning.create_learning_item(
        vault, topic="t", skill_area="frontend", date_str="2026-06-07", seq=1,
    )
    path = learning.record_review(
        vault, "learning-20260607-001", passed=False, today_str="2026-06-08",
    )
    meta, _ = schema.parse_doc(path.read_text(encoding="utf-8"))
    assert meta["level"] == "unknown"        # no advance
    assert meta["next_review"] == "2026-06-09"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_learning.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/core/learning.py`**

```python
"""Learning items + spaced-repetition review driver."""
from __future__ import annotations

import datetime as _dt
from pathlib import Path

from .. import schema
from . import index

_INTERVALS = [1, 3, 7, 16, 35]  # days per successful stage


def _add_days(date_str: str, days: int) -> str:
    return (_dt.date.fromisoformat(date_str) + _dt.timedelta(days=days)).isoformat()


def create_learning_item(
    vault: Path, *, topic: str, skill_area: str, date_str: str, seq: int,
    source_refs: list[str] | None = None, wiki_refs: list[str] | None = None,
) -> Path:
    lid = schema.make_id("learning", date_str, seq)
    meta = {
        "type": "learning_item", "id": lid, "topic": topic,
        "skill_area": skill_area, "level": "unknown",
        "source_refs": source_refs or [], "wiki_refs": wiki_refs or [],
        "created": date_str, "next_review": date_str,
    }
    path = Path(vault) / "30_Learning/flashcards" / f"{lid}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(schema.render_doc(meta, f"## Topic\n\n{topic}\n"), encoding="utf-8")
    index.update_index(vault, "learning-index", lid, f"{topic} — unknown")
    return path


def _find(vault: Path, learning_id: str) -> Path:
    for p in (Path(vault) / "30_Learning").rglob(f"{learning_id}.md"):
        return p
    raise FileNotFoundError(learning_id)


def list_due_reviews(vault: Path, today_str: str) -> list[dict]:
    due = []
    for p in (Path(vault) / "30_Learning").rglob("learning-*.md"):
        meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        nr = meta.get("next_review")
        if nr and nr <= today_str:
            due.append({"id": meta["id"], "topic": meta.get("topic", ""),
                        "level": meta.get("level", "unknown")})
    return sorted(due, key=lambda r: r["id"])


def record_review(vault: Path, learning_id: str, *, passed: bool, today_str: str) -> Path:
    path = _find(vault, learning_id)
    meta, body = schema.parse_doc(path.read_text(encoding="utf-8"))
    levels = list(schema.LEARNING_LEVELS)
    cur = levels.index(meta.get("level", "unknown"))
    if passed:
        new_idx = min(cur + 1, len(levels) - 1)
        meta["level"] = levels[new_idx]
        meta["next_review"] = _add_days(today_str, _INTERVALS[min(cur, len(_INTERVALS) - 1)])
    else:
        meta["next_review"] = _add_days(today_str, 1)
    path.write_text(schema.render_doc(meta, body), encoding="utf-8")
    index.update_index(vault, "learning-index", learning_id,
                       f"{meta.get('topic','')} — {meta['level']}")
    return path
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_learning.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/core/learning.py tests/test_learning.py
git commit -m "feat: learning items + SRS review driver"
```

---

## Task 9: tools.py — @tool wrappers + MCP server

**Files:**
- Create: `wiki_agent/tools.py`, `tests/test_tools.py`

- [ ] **Step 1: Write the failing test** — `tests/test_tools.py`

```python
from wiki_agent import tools


def test_build_wiki_server(vault):
    server = tools.build_wiki_server(vault)
    assert server is not None  # McpSdkServerConfig


def test_tool_names_list():
    names = tools.WIKI_TOOL_NAMES
    assert "mcp__wiki__create_claim" in names
    assert "mcp__wiki__promote_claim" in names
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_tools.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/tools.py`**

```python
"""Wrap pure core functions as in-process MCP @tools for the agent."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import schema
from .core import claims, learning, sources, wiki

WIKI_TOOL_NAMES = [
    "mcp__wiki__create_source", "mcp__wiki__triage_record",
    "mcp__wiki__create_claim", "mcp__wiki__find_similar_claim",
    "mcp__wiki__promote_claim", "mcp__wiki__set_claim_status",
    "mcp__wiki__list_pending", "mcp__wiki__create_wiki_page",
    "mcp__wiki__create_learning_item", "mcp__wiki__list_due_reviews",
    "mcp__wiki__record_review",
]


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def build_wiki_server(vault: Path):
    vault = Path(vault)

    @tool("create_source", "Capture a raw clip as a source in the Inbox",
          {"origin": str, "content": str, "sensitivity": str})
    async def create_source(args):
        p = sources.create_source(
            vault, origin=args["origin"], content=args["content"],
            sensitivity=args.get("sensitivity", "personal"),
            date_str=schema.today_str(), seq=_next_seq(vault, "00_Inbox/raw", "source"),
            url=args.get("url"),
        )
        return _ok(f"created {p.stem}")

    @tool("triage_record", "Record a triage decision (drop|keep-as-link|deep)",
          {"source_id": str, "decision": str})
    async def triage_record(args):
        sources.triage_record(vault, args["source_id"], args["decision"], schema.today_str())
        return _ok("recorded")

    @tool("create_claim", "Create an atomic claim (always unverified)",
          {"claim": str, "claim_type": str})
    async def create_claim(args):
        p = claims.create_claim(
            vault, claim=args["claim"], claim_type=args["claim_type"],
            source_refs=args.get("source_refs", []), date_str=schema.today_str(),
            seq=_next_seq(vault, "10_Claims/pending", "claim"),
            proposed_status=args.get("proposed_status"), speaker=args.get("speaker"),
        )
        return _ok(f"created {p.stem} (unverified)")

    @tool("find_similar_claim", "Find duplicate claims by normalized key",
          {"claim": str})
    async def find_similar_claim(args):
        hits = claims.find_similar_claim(vault, args["claim"], args.get("speaker"))
        return _ok(", ".join(hits) or "none")

    @tool("promote_claim", "Promote a claim's status (verified is gated)",
          {"claim_id": str, "target_status": str})
    async def promote_claim(args):
        p = claims.promote_claim(
            vault, args["claim_id"], target_status=args["target_status"],
            evidence_refs=args.get("evidence_refs"),
            approved_by_human=bool(args.get("approved_by_human", False)),
            date_str=schema.today_str(),
        )
        return _ok(f"promoted {p.stem} -> {args['target_status']}")

    @tool("set_claim_status", "Set a non-verified status (disputed/outdated/rejected)",
          {"claim_id": str, "status": str})
    async def set_claim_status(args):
        p = claims.set_claim_status(
            vault, args["claim_id"], status=args["status"],
            superseded_by=args.get("superseded_by"), date_str=schema.today_str(),
        )
        return _ok(f"set {p.stem} -> {args['status']}")

    @tool("list_pending", "List pending (unverified) claims", {})
    async def list_pending(args):
        rows = claims.list_pending(vault)
        return _ok("\n".join(f"{r['id']}: {r['claim'][:60]}" for r in rows) or "none")

    @tool("create_wiki_page", "Create a wiki page (concept/pattern/...)",
          {"name": str, "page_type": str, "body": str})
    async def create_wiki_page(args):
        p = wiki.create_wiki_page(
            vault, name=args["name"], page_type=args["page_type"], body=args["body"],
            claim_refs=args.get("claim_refs", []), date_str=schema.today_str(),
        )
        return _ok(f"created {p.name}")

    @tool("create_learning_item", "Create a learning item / flashcard",
          {"topic": str, "skill_area": str})
    async def create_learning_item(args):
        p = learning.create_learning_item(
            vault, topic=args["topic"], skill_area=args["skill_area"],
            date_str=schema.today_str(),
            seq=_next_seq(vault, "30_Learning/flashcards", "learning"),
            wiki_refs=args.get("wiki_refs", []),
        )
        return _ok(f"created {p.stem}")

    @tool("list_due_reviews", "List learning items due for review today", {})
    async def list_due_reviews(args):
        rows = learning.list_due_reviews(vault, schema.today_str())
        return _ok("\n".join(f"{r['id']}: {r['topic']}" for r in rows) or "none")

    @tool("record_review", "Record a review result (passed true/false)",
          {"learning_id": str, "passed": bool})
    async def record_review(args):
        p = learning.record_review(
            vault, args["learning_id"], passed=bool(args["passed"]),
            today_str=schema.today_str(),
        )
        return _ok(f"recorded {p.stem}")

    return create_sdk_mcp_server(
        name="wiki", version="0.1.0",
        tools=[create_source, triage_record, create_claim, find_similar_claim,
               promote_claim, set_claim_status, list_pending, create_wiki_page,
               create_learning_item, list_due_reviews, record_review],
    )


def _next_seq(vault: Path, subdir: str, prefix: str) -> int:
    d = Path(vault) / subdir
    n = len(list(d.glob(f"{prefix}-*.md"))) if d.exists() else 0
    return n + 1
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_tools.py -v`
Expected: 2 passed. (If `claude_agent_sdk` import fails, run `uv add claude-agent-sdk` and ensure the Claude Code CLI is installed.)

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/tools.py tests/test_tools.py
git commit -m "feat: MCP @tool wrappers over core"
```

---

## Task 10: permissions.py — verified + sensitivity gate

**Files:**
- Create: `wiki_agent/permissions.py`, `tests/test_permissions.py`

- [ ] **Step 1: Write the failing test** — `tests/test_permissions.py`

```python
import pytest
from wiki_agent import permissions


@pytest.mark.asyncio
async def test_deny_unapproved_verified(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__promote_claim",
                     {"claim_id": "c", "target_status": "verified"}, None)
    assert res.behavior == "deny"


@pytest.mark.asyncio
async def test_allow_approved_verified(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__promote_claim",
                     {"claim_id": "c", "target_status": "verified",
                      "approved_by_human": True}, None)
    assert res.behavior == "allow"


@pytest.mark.asyncio
async def test_deny_work_source(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__create_source",
                     {"origin": "x", "content": "y", "sensitivity": "work"}, None)
    assert res.behavior == "deny"


@pytest.mark.asyncio
async def test_allow_other_tools(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("Read", {"file_path": "x"}, None)
    assert res.behavior == "allow"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_permissions.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/permissions.py`**

```python
"""can_use_tool gate: verified promotion + sensitivity (mirrors core invariants)."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny


def make_can_use_tool(vault: Path):
    async def can_use_tool(tool_name: str, input_data: dict, context):
        if tool_name == "mcp__wiki__promote_claim":
            if input_data.get("target_status") == "verified":
                if not input_data.get("approved_by_human") and not input_data.get("evidence_refs"):
                    return PermissionResultDeny(
                        message="verified requires human approval or evidence (principle 9)"
                    )
        if tool_name == "mcp__wiki__create_source":
            if input_data.get("sensitivity", "personal") != "personal":
                return PermissionResultDeny(
                    message="work/confidential content must go to the work vault"
                )
        return PermissionResultAllow(updated_input=input_data)

    return can_use_tool
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_permissions.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/permissions.py tests/test_permissions.py
git commit -m "feat: can_use_tool gate for verified + sensitivity"
```

---

## Task 11: prompts/ + subagents.py

**Files:**
- Create: `wiki_agent/prompts/system.md`, `wiki_agent/prompts/ingest.md`, `wiki_agent/prompts/verify.md`, `wiki_agent/prompts/answer.md`, `wiki_agent/prompts/learning.md`, `wiki_agent/subagents.py`, `tests/test_subagents.py`

- [ ] **Step 1: Write `wiki_agent/prompts/system.md`**

```markdown
You are the brain of a personal AI Wiki + learning system over a Markdown vault.

Core principles (non-negotiable):
- Raw is not truth; it is a claim candidate.
- You PROPOSE; the human or deterministic tool evidence CONFIRMS. You may set a claim's
  proposed_status, but only the gated promote_claim with human approval or evidence makes it verified.
- Attributed claims are stored as `attributed`, not facts. Wrong info is kept as `rejected`, not deleted.
- Most raw should be dropped or kept-as-link (triage). Promotion is the exception.
- work/confidential content never enters this personal vault.

Always use the mcp__wiki__* tools for structured writes (sources, claims, wiki pages, learning items)
so schema/IDs/index stay consistent. Use Read/Grep/Glob to explore the vault.

When the user asks to ingest, verify, answer, or build learning material, delegate to the matching
subagent (ingest / verify / answer / learning).

When answering, separate: 확인된 내용 / 프로젝트 기준 / 아직 검증되지 않은 내용 /
특정인의 주장 / 내 판단 / 주의할 점 / 다음 학습 과제. New insights from an answer go back to the
claim ledger as unverified — never written straight into the wiki.
```

- [ ] **Step 2: Write the four subagent prompts**

`wiki_agent/prompts/ingest.md`:
```markdown
You ingest one raw clip. Steps: read the source; triage (drop|keep-as-link|deep);
for `deep`, extract atomic claims; classify each claim_type; check find_similar_claim for duplicates;
create each claim with create_claim (it is always unverified). Suggest a proposed_status only.
Never mark anything verified. Record the triage decision.
```

`wiki_agent/prompts/verify.md`:
```markdown
You verify pending claims. For each: determine what evidence is needed; check repo files, official
docs, or run tests via Bash/Grep/Glob; then call promote_claim with evidence_refs, or set_claim_status
for disputed/outdated/rejected. Do NOT mark verified without evidence or explicit human approval.
For verified claims worth surfacing, create or update a wiki page with claim_refs.
```

`wiki_agent/prompts/answer.md`:
```markdown
You answer questions from the wiki. Read index + candidate docs, expand relations one hop, and answer
using the epistemic format (확인된 내용 / 아직 검증되지 않은 내용 / 특정인의 주장 / 내 판단 / 주의할 점 /
다음 학습 과제). Any new useful insight is stored via create_claim as unverified — never written
directly into the wiki. You may not use Write.
```

`wiki_agent/prompts/learning.md`:
```markdown
You build learning material. From a session or wiki page, create learning items / flashcards via
create_learning_item, and drive review via list_due_reviews and record_review. Level transitions:
seen=summarized in own words, used=implemented a mini-exercise, can-teach=explained unaided + passed quiz.
```

- [ ] **Step 3: Write the failing test** — `tests/test_subagents.py`

```python
from wiki_agent import subagents


def test_build_subagents_has_four():
    agents = subagents.build_subagents()
    assert set(agents) == {"ingest", "verify", "answer", "learning"}
    assert "Read" in agents["answer"].tools
    # answer must not be able to Write
    assert "Write" not in (agents["answer"].tools or [])
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run pytest tests/test_subagents.py -v`
Expected: FAIL (module missing).

- [ ] **Step 5: Write `wiki_agent/subagents.py`**

```python
"""Subagent definitions; prompts loaded from prompts/."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import AgentDefinition

from .tools import WIKI_TOOL_NAMES

_PROMPTS = Path(__file__).parent / "prompts"


def _p(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def build_subagents() -> dict[str, AgentDefinition]:
    w = WIKI_TOOL_NAMES
    return {
        "ingest": AgentDefinition(
            description="Ingest a raw clip into triaged, unverified claims.",
            prompt=_p("ingest"),
            tools=["Read", "Grep"] + [t for t in w if any(
                k in t for k in ("create_source", "triage_record", "create_claim", "find_similar_claim"))],
            model="claude-opus-4-8",
        ),
        "verify": AgentDefinition(
            description="Verify pending claims with evidence; promote or block.",
            prompt=_p("verify"),
            tools=["Read", "Grep", "Glob", "Bash"] + [t for t in w if any(
                k in t for k in ("promote_claim", "set_claim_status", "create_wiki_page", "list_pending"))],
            model="claude-opus-4-8",
        ),
        "answer": AgentDefinition(
            description="Answer from the wiki with epistemic status; feed insights back as unverified.",
            prompt=_p("answer"),
            tools=["Read", "Grep", "Glob", "mcp__wiki__create_claim"],
            disallowedTools=["Write", "Edit"],
            model="claude-opus-4-8",
        ),
        "learning": AgentDefinition(
            description="Build learning material and drive spaced review.",
            prompt=_p("learning"),
            tools=["Read", "Grep"] + [t for t in w if any(
                k in t for k in ("create_learning_item", "list_due_reviews", "record_review"))],
            model="claude-opus-4-8",
        ),
    }
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_subagents.py -v`
Expected: 1 passed.

- [ ] **Step 7: Commit**

```bash
git add wiki_agent/prompts wiki_agent/subagents.py tests/test_subagents.py
git commit -m "feat: system + subagent prompts and definitions"
```

---

## Task 12: agent.py — options + session wrapper

**Files:**
- Create: `wiki_agent/agent.py`, `tests/test_agent.py`

- [ ] **Step 1: Write the failing test** — `tests/test_agent.py`

```python
from wiki_agent import agent


def test_build_options(vault):
    opts = agent.build_options(vault)
    assert opts.model == "claude-opus-4-8"
    assert str(vault) == str(opts.cwd)
    assert "wiki" in opts.mcp_servers
    assert "mcp__wiki__create_claim" in opts.allowed_tools
    assert set(opts.agents) == {"ingest", "verify", "answer", "learning"}
    assert opts.can_use_tool is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_agent.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/agent.py`**

```python
"""Assemble ClaudeAgentOptions and a thin multi-turn session wrapper."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage, ClaudeAgentOptions, ClaudeSDKClient, TextBlock,
)

from .permissions import make_can_use_tool
from .subagents import build_subagents
from .tools import WIKI_TOOL_NAMES, build_wiki_server

_SYSTEM = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")


def build_options(vault: Path) -> ClaudeAgentOptions:
    vault = Path(vault)
    server = build_wiki_server(vault)
    return ClaudeAgentOptions(
        system_prompt=_SYSTEM,
        model="claude-opus-4-8",
        cwd=str(vault),
        permission_mode="acceptEdits",
        mcp_servers={"wiki": server},
        allowed_tools=["Read", "Grep", "Glob", "Bash", "Write", "Edit", *WIKI_TOOL_NAMES],
        agents=build_subagents(),
        can_use_tool=make_can_use_tool(vault),
    )


class WikiSession:
    """One long-running conversational session over the vault."""

    def __init__(self, vault: Path):
        self._client = ClaudeSDKClient(options=build_options(vault))
        self._connected = False

    async def __aenter__(self):
        await self._client.connect()
        self._connected = True
        return self

    async def __aexit__(self, *exc):
        await self._client.disconnect()

    async def ask(self, prompt: str):
        """Send a turn; yield assistant text chunks."""
        await self._client.query(prompt)
        async for msg in self._client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        yield block.text
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_agent.py -v`
Expected: 1 passed. (Options construction does not require the CLI; only running `WikiSession` does.)

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/agent.py tests/test_agent.py
git commit -m "feat: agent options and session wrapper"
```

---

## Task 13: app.py — FastAPI routes (capture + queues)

**Files:**
- Create: `wiki_agent/app.py`, `tests/test_app.py`

- [ ] **Step 1: Write the failing test** — `tests/test_app.py`

```python
from fastapi.testclient import TestClient
from wiki_agent.app import create_app


def test_capture_and_pending(vault):
    app = create_app(vault)
    client = TestClient(app)

    r = client.post("/capture", json={"origin": "chatgpt", "content": "raw text"})
    assert r.status_code == 200
    sid = r.json()["id"]
    assert sid.startswith("source-")

    # create a claim directly via core to populate the verify queue
    from wiki_agent.core import claims
    from wiki_agent import schema
    claims.create_claim(vault, claim="some claim", claim_type="technical_fact",
                        source_refs=[sid], date_str=schema.today_str(), seq=1)

    r = client.get("/claims/pending")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["claim"] == "some claim" for row in rows)


def test_approve_claim(vault):
    app = create_app(vault)
    client = TestClient(app)
    from wiki_agent.core import claims
    from wiki_agent import schema
    claims.create_claim(vault, claim="c", claim_type="technical_fact",
                        source_refs=[], date_str=schema.today_str(), seq=1)
    cid = "claim-" + schema.today_str().replace("-", "") + "-001"

    r = client.post(f"/claims/{cid}/approve")
    assert r.status_code == 200
    assert (vault / "10_Claims/verified" / f"{cid}.md").exists()


def test_due_reviews_route(vault):
    app = create_app(vault)
    client = TestClient(app)
    from wiki_agent.core import learning
    from wiki_agent import schema
    learning.create_learning_item(vault, topic="t", skill_area="frontend",
                                  date_str=schema.today_str(), seq=1)
    r = client.get("/reviews/due")
    assert r.status_code == 200
    assert len(r.json()) >= 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py -v`
Expected: FAIL (module missing).

- [ ] **Step 3: Write `wiki_agent/app.py`**

```python
"""FastAPI app: capture + deterministic queue routes (core, no LLM) + chat (SSE)."""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import schema
from .core import claims, learning, sources

_WEB = Path(__file__).parent / "web"


class CaptureBody(BaseModel):
    origin: str = "manual"
    content: str | None = None
    url: str | None = None
    sensitivity: str = "personal"


def _next_seq(vault: Path, subdir: str, prefix: str) -> int:
    d = vault / subdir
    return (len(list(d.glob(f"{prefix}-*.md"))) if d.exists() else 0) + 1


def create_app(vault: Path) -> FastAPI:
    vault = Path(vault)
    app = FastAPI(title="Personal AI Wiki")

    @app.post("/capture")
    def capture(body: CaptureBody):
        content = body.content
        if body.url and not content:
            html = httpx.get(body.url, follow_redirects=True, timeout=20).text
            content = sources.html_to_markdown(html)
        path = sources.create_source(
            vault, origin=body.origin, content=content or "",
            sensitivity=body.sensitivity, date_str=schema.today_str(),
            seq=_next_seq(vault, "00_Inbox/raw", "source"), url=body.url,
        )
        return {"id": path.stem}

    @app.get("/claims/pending")
    def pending():
        return claims.list_pending(vault)

    @app.post("/claims/{cid}/approve")
    def approve(cid: str):
        p = claims.promote_claim(vault, cid, target_status="verified",
                                 approved_by_human=True, date_str=schema.today_str())
        return {"id": cid, "status": "verified", "path": str(p)}

    @app.post("/claims/{cid}/reject")
    def reject(cid: str):
        p = claims.set_claim_status(vault, cid, status="rejected",
                                    date_str=schema.today_str())
        return {"id": cid, "status": "rejected", "path": str(p)}

    @app.get("/reviews/due")
    def due():
        return learning.list_due_reviews(vault, schema.today_str())

    @app.post("/reviews/{lid}/record")
    def record(lid: str, passed: bool = True):
        p = learning.record_review(vault, lid, passed=passed, today_str=schema.today_str())
        return {"id": lid, "path": str(p)}

    @app.get("/")
    def home():
        return FileResponse(_WEB / "index.html")

    if _WEB.exists():
        app.mount("/static", StaticFiles(directory=_WEB), name="static")

    # chat route added in Task 14
    _attach_chat(app, vault)
    return app


def _attach_chat(app: FastAPI, vault: Path) -> None:
    # Implemented in Task 14.
    pass
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add wiki_agent/app.py tests/test_app.py
git commit -m "feat: FastAPI capture and queue routes over core"
```

---

## Task 14: Chat SSE route

**Files:**
- Modify: `wiki_agent/app.py` (replace `_attach_chat`)
- Create/Modify: `tests/test_app.py` (add a chat-route presence test)

- [ ] **Step 1: Write the failing test** — append to `tests/test_app.py`

```python
def test_chat_route_exists(vault):
    app = create_app(vault)
    routes = {r.path for r in app.routes}
    assert "/chat" in routes
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_app.py::test_chat_route_exists -v`
Expected: FAIL (`/chat` not registered).

- [ ] **Step 3: Replace `_attach_chat` in `wiki_agent/app.py`**

Replace the stub with:
```python
def _attach_chat(app: FastAPI, vault: Path) -> None:
    from .agent import WikiSession

    class ChatBody(BaseModel):
        prompt: str

    @app.post("/chat")
    async def chat(body: ChatBody):
        async def stream():
            async with WikiSession(vault) as session:
                async for chunk in session.ask(body.prompt):
                    yield f"data: {chunk}\n\n"
            yield "data: [DONE]\n\n"
        return StreamingResponse(stream(), media_type="text/event-stream")
```
Also remove the now-unused trailing `pass` stub definition (the function above replaces it).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_app.py::test_chat_route_exists -v`
Expected: PASS. (The route registers without the CLI; actually streaming a turn requires the Claude Code CLI at runtime — covered in Task 16's manual check.)

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git add wiki_agent/app.py tests/test_app.py
git commit -m "feat: chat SSE route wired to WikiSession"
```

---

## Task 15: web/index.html + __main__.py entry

**Files:**
- Create: `wiki_agent/web/index.html`, `wiki_agent/__main__.py`

- [ ] **Step 1: Write `wiki_agent/web/index.html`**

```html
<!doctype html>
<html lang="ko">
<head>
  <meta charset="utf-8" />
  <title>Personal AI Wiki</title>
  <style>
    body { font: 14px/1.5 system-ui, sans-serif; margin: 0; }
    nav button { padding: .6rem 1rem; border: 0; background: #eee; cursor: pointer; }
    nav button.active { background: #ddd; font-weight: 600; }
    main { padding: 1rem; }
    .panel { display: none; } .panel.active { display: block; }
    #log { white-space: pre-wrap; border: 1px solid #ccc; padding: .5rem; min-height: 8rem; }
    textarea { width: 100%; height: 6rem; }
    .row { border-bottom: 1px solid #eee; padding: .4rem 0; }
    button.act { margin-left: .5rem; }
  </style>
</head>
<body>
  <nav>
    <button data-tab="chat" class="active">Chat</button>
    <button data-tab="capture">Capture</button>
    <button data-tab="verify">Verify</button>
    <button data-tab="review">Review</button>
  </nav>
  <main>
    <section id="chat" class="panel active">
      <div id="log"></div>
      <input id="prompt" style="width:80%" placeholder="이거 인제스트해줘 / X에 대해 답해줘" />
      <button onclick="send()">Send</button>
    </section>
    <section id="capture" class="panel">
      <textarea id="capContent" placeholder="대화/텍스트 붙여넣기"></textarea>
      <input id="capUrl" style="width:60%" placeholder="또는 URL" />
      <button onclick="capture()">Capture → Inbox</button>
      <div id="capMsg"></div>
    </section>
    <section id="verify" class="panel">
      <button onclick="loadPending()">새로고침</button>
      <div id="pending"></div>
    </section>
    <section id="review" class="panel">
      <button onclick="loadDue()">새로고침</button>
      <div id="due"></div>
    </section>
  </main>
  <script>
    document.querySelectorAll('nav button').forEach(b => b.onclick = () => {
      document.querySelectorAll('nav button').forEach(x => x.classList.remove('active'));
      document.querySelectorAll('.panel').forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      document.getElementById(b.dataset.tab).classList.add('active');
    });
    async function send() {
      const prompt = document.getElementById('prompt').value;
      const log = document.getElementById('log');
      log.textContent += '\n> ' + prompt + '\n';
      const res = await fetch('/chat', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({prompt})});
      const reader = res.body.getReader(); const dec = new TextDecoder();
      while (true) { const {value, done} = await reader.read(); if (done) break;
        dec.decode(value).split('\n').forEach(l => {
          if (l.startsWith('data: ') && l !== 'data: [DONE]') log.textContent += l.slice(6);
        });
      }
    }
    async function capture() {
      const content = document.getElementById('capContent').value;
      const url = document.getElementById('capUrl').value || null;
      const r = await fetch('/capture', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({origin: 'manual', content, url})});
      document.getElementById('capMsg').textContent = JSON.stringify(await r.json());
    }
    async function loadPending() {
      const rows = await (await fetch('/claims/pending')).json();
      document.getElementById('pending').innerHTML = rows.map(r =>
        `<div class="row">${r.id}: ${r.claim}
         <button class="act" onclick="approve('${r.id}')">승인</button>
         <button class="act" onclick="reject('${r.id}')">거부</button></div>`).join('') || '없음';
    }
    async function approve(id) { await fetch(`/claims/${id}/approve`, {method: 'POST'}); loadPending(); }
    async function reject(id) { await fetch(`/claims/${id}/reject`, {method: 'POST'}); loadPending(); }
    async function loadDue() {
      const rows = await (await fetch('/reviews/due')).json();
      document.getElementById('due').innerHTML = rows.map(r =>
        `<div class="row">${r.id}: ${r.topic} (${r.level})
         <button class="act" onclick="rec('${r.id}',true)">통과</button>
         <button class="act" onclick="rec('${r.id}',false)">실패</button></div>`).join('') || '없음';
    }
    async function rec(id, passed) { await fetch(`/reviews/${id}/record?passed=${passed}`, {method: 'POST'}); loadDue(); }
  </script>
</body>
</html>
```

- [ ] **Step 2: Write `wiki_agent/__main__.py`**

```python
"""CLI entry: `uv run wiki init` (scaffold) | `uv run wiki serve` (default)."""
from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .core import scaffold


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "serve"
    vault = Path(args[1]) if len(args) > 1 else Path.cwd()

    if cmd == "init":
        scaffold.scaffold_vault(vault)
        print(f"scaffolded vault at {vault}")
        return
    if cmd == "serve":
        scaffold.scaffold_vault(vault)  # idempotent
        app = create_app(vault)
        uvicorn.run(app, host="127.0.0.1", port=8765)
        return
    print(f"unknown command: {cmd}; use 'init' or 'serve'")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Verify the app boots and serves the UI (no LLM needed for this check)**

Run:
```bash
uv run python -c "from fastapi.testclient import TestClient; from wiki_agent.app import create_app; import pathlib; c=TestClient(create_app(pathlib.Path('.'))); r=c.get('/'); print(r.status_code); assert r.status_code==200 and 'Personal AI Wiki' in r.text"
```
Expected: prints `200`, no assertion error.

- [ ] **Step 4: Commit**

```bash
git add wiki_agent/web/index.html wiki_agent/__main__.py
git commit -m "feat: web UI and CLI entry (init/serve)"
```

---

## Task 16: End-to-end manual verification + Web Clipper config

**Files:**
- Create: `docs/web-clipper-setup.md`

- [ ] **Step 1: Confirm Claude Code CLI is available (runtime requirement)**

Run: `claude --version`
Expected: prints a version. If missing, install Claude Code CLI before the live run.

- [ ] **Step 2: Launch the app**

Run: `uv run wiki serve`
Expected: uvicorn serving on `http://127.0.0.1:8765`. Open it in a browser.

- [ ] **Step 3: Run the end-to-end loop (matches spec §검증)**

1. **Capture** tab → paste a ChatGPT conversation → "Capture → Inbox" → confirm a `source-*` id is returned and the file appears under `00_Inbox/raw/` (also visible in Obsidian).
2. **Chat** tab → "방금 캡처한 소스 인제스트해줘" → confirm unverified `claim-*` files appear under `10_Claims/pending/`.
3. **Verify** tab → 새로고침 → a pending claim appears → "승인" → confirm it moves to `10_Claims/verified/` and `claim-index.md` updates.
4. **Chat** tab → "X에 대해 위키에서 답해줘" → confirm the answer uses the epistemic sections.
5. **Chat** tab → "이 주제로 학습 카드 만들어줘" → confirm a `learning-*` file under `30_Learning/flashcards/`.
6. **Review** tab → 새로고침 → the new card appears as due.

- [ ] **Step 4: Write `docs/web-clipper-setup.md`**

```markdown
# Obsidian Web Clipper → Inbox

1. Install the Obsidian Web Clipper browser extension.
2. Set the vault to this folder and the default save location to `00_Inbox/browser-clips/`.
3. Use a Markdown template that includes a frontmatter block:
   - `type: source`
   - `origin: browser`
   - `sensitivity: personal`
   - `url: {{url}}`
   - `captured_at: {{date}}`
4. Clip a page; it lands in `00_Inbox/browser-clips/`. In the Chat tab, say
   "Inbox의 새 브라우저 클립 인제스트해줘" to run the ingest subagent over it.
```

- [ ] **Step 5: Commit**

```bash
git add docs/web-clipper-setup.md
git commit -m "docs: web clipper setup and e2e verification"
```

---

## Self-Review

**Spec coverage:**
- uv + pyproject → Task 1. schema single source → Task 2. vault scaffold → Task 3.
- Integrity core (sources/claims/wiki/learning/index) → Tasks 4–8, with verified gate in Task 6 + Task 10.
- MCP @tool wrappers → Task 9. Subagents (ingest/verify/answer/learning) → Task 11. Options/session → Task 12.
- Web app (capture incl. URL fetch, verify queue, review queue) → Task 13; chat SSE → Task 14; UI + entry → Task 15.
- Capture via Web Clipper → Task 16 doc. Permissions verified + sensitivity gate → Task 10.
- Non-goals (wrap-feature, lint, search, watcher) correctly excluded.
- "wrap twice" pattern: core funcs called by both `tools.py` (Task 9) and `app.py` (Task 13). ✓

**Placeholder scan:** No "TBD/TODO" left. The only deferred stub (`_attach_chat`) is explicitly created in Task 13 and replaced with real code in Task 14 — not a placeholder, a planned two-step.

**Type/name consistency:** `make_id`, `render_doc`/`parse_doc`, `create_source`, `create_claim`/`promote_claim`/`set_claim_status`/`list_pending`, `find_similar_claim`, `create_wiki_page`/`update_wiki_page`, `create_learning_item`/`list_due_reviews`/`record_review`, `build_wiki_server`/`WIKI_TOOL_NAMES`, `make_can_use_tool`, `build_subagents`, `build_options`/`WikiSession`, `create_app` — names are used consistently across tasks. Tool names use the `mcp__wiki__<tool>` convention everywhere.

**Known runtime caveats (documented, not gaps):** `/chat` streaming and any `WikiSession` run require the Claude Code CLI installed; unit tests avoid the LLM by testing `core/` directly and constructing (not running) options.
