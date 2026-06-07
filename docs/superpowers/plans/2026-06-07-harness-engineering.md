# Harness Engineering 적용 Implementation Plan

> **For agentic workers:** Steps use `- [ ]`. Small scope (1 guard test + 2 docs); no existing code changes — current layers already comply. Per `docs/superpowers/specs/2026-06-07-harness-engineering-design.md`.

**Goal:** Add the missing harness artifacts — a mechanical layering-lint test, `ARCHITECTURE.md` (code map), `AGENTS.md` (golden principles).

**Tech Stack:** stdlib `ast` + pytest. `uv run pytest`. Branch `main`. Commit only touched files.

---

## Task 1: tests/test_architecture.py (mechanical layer lint)

**Files:** Create `tests/test_architecture.py`

- [ ] **Step 1: Write the test (includes a self-test proving the checker catches violations)** — full code:

```python
"""Mechanical enforcement of the module dependency layering (harness engineering)."""
import ast
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent / "wiki_agent"
FORBIDDEN_EXTERNAL = {"claude_agent_sdk", "fastapi", "uvicorn", "starlette"}
ORCH = {"tools", "agent", "app", "subagents", "permissions", "__main__"}


def _pkg_of(path: Path) -> str:
    rel = path.resolve().relative_to(PKG_ROOT.parent)
    parts = list(rel.with_suffix("").parts)
    return ".".join(parts[:-1])


def referenced_modules(source: str, pkg: str) -> set[str]:
    tree = ast.parse(source)
    pkg_parts = pkg.split(".")
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0:
                base = node.module or ""
                if base:
                    out.add(base)
                for a in node.names:
                    out.add(f"{base}.{a.name}" if base else a.name)
            else:
                base_parts = pkg_parts[: len(pkg_parts) - (node.level - 1)]
                base = ".".join(base_parts + ([node.module] if node.module else []))
                out.add(base)
                for a in node.names:
                    out.add(f"{base}.{a.name}")
    return {m for m in out if m}


def core_violations(source: str, pkg: str) -> list[str]:
    bad = set()
    for m in referenced_modules(source, pkg):
        if m.split(".")[0] in FORBIDDEN_EXTERNAL:
            bad.add(m)
        for orch in ORCH:
            if m == f"wiki_agent.{orch}" or m.startswith(f"wiki_agent.{orch}."):
                bad.add(m)
    return sorted(bad)


def test_core_is_pure():
    offenders = {}
    for f in (PKG_ROOT / "core").rglob("*.py"):
        v = core_violations(f.read_text(encoding="utf-8"), _pkg_of(f))
        if v:
            offenders[str(f.relative_to(PKG_ROOT))] = v
    assert not offenders, offenders


def test_schema_is_base():
    f = PKG_ROOT / "schema.py"
    refs = referenced_modules(f.read_text(encoding="utf-8"), _pkg_of(f))
    assert not [m for m in refs if m.split(".")[0] == "wiki_agent"], refs


def test_only_app_imports_web():
    offenders = {}
    for f in PKG_ROOT.rglob("*.py"):
        if f.name == "app.py":
            continue
        refs = referenced_modules(f.read_text(encoding="utf-8"), _pkg_of(f))
        web = [m for m in refs if m.split(".")[0] in {"fastapi", "starlette"}]
        if web:
            offenders[str(f.relative_to(PKG_ROOT))] = web
    assert not offenders, offenders


def test_checker_catches_violation():
    assert "claude_agent_sdk" in core_violations(
        "from claude_agent_sdk import tool\nfrom .. import schema\n", "wiki_agent.core")
    assert any("wiki_agent.tools" in m for m in core_violations(
        "from ..tools import WIKI_TOOL_NAMES\n", "wiki_agent.core"))
    assert core_violations("from .. import schema\nfrom . import index\n",
                           "wiki_agent.core") == []
```

- [ ] **Step 2: Run** `uv run pytest tests/test_architecture.py -v` — Expected: 4 passed (current code complies; `test_checker_catches_violation` proves the checker is not vacuous).
- [ ] **Step 3: Commit** `git add tests/test_architecture.py && git commit -m "test: mechanical layering lint (harness engineering)"`

---

## Task 2: ARCHITECTURE.md (map, not manual)

**Files:** Create `ARCHITECTURE.md` — content per spec §"ARCHITECTURE.md 설계": one-line purpose, the layer diagram (L0 schema → L1 core → L2 tools/permissions → L3 subagents → L4 agent → L5 app/__main__), one-line responsibility per module, a "What is NOT here" section (core has no LLM/web deps; lint checks code layers not vault; persistent state = vault files + git, not chat history), and a pointer to `docs/superpowers/` ExecPlans for research→plan→execute→verify.

- [ ] **Step 1: Write `ARCHITECTURE.md`** (see Task content below in this plan / spec).
- [ ] **Step 2: Commit** `git add ARCHITECTURE.md && git commit -m "docs: ARCHITECTURE.md code map"`

---

## Task 3: AGENTS.md (golden principles)

**Files:** Create `AGENTS.md` — the 6 golden principles per spec §"AGENTS.md 설계" (uv/CLI env, integrity via core only, gates/sensitivity, layering enforced by test_architecture, spec→plan→TDD→commit workflow, security: no public push).

- [ ] **Step 1: Write `AGENTS.md`**.
- [ ] **Step 2: Commit** `git add AGENTS.md && git commit -m "docs: AGENTS.md golden principles"`

---

## Verify
`uv run pytest -q` green (incl. new architecture test). Docs read for accuracy.
