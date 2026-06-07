"""Mechanical enforcement of the module dependency layering (harness engineering)."""
import ast
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent / "wiki_agents"
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
            if m == f"wiki_agents.{orch}" or m.startswith(f"wiki_agents.{orch}."):
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
    assert not [m for m in refs if m.split(".")[0] == "wiki_agents"], refs


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
        "from claude_agent_sdk import tool\nfrom .. import schema\n", "wiki_agents.core")
    assert any("wiki_agents.tools" in m for m in core_violations(
        "from ..tools import WIKI_TOOL_NAMES\n", "wiki_agents.core"))
    assert core_violations("from .. import schema\nfrom . import index\n",
                           "wiki_agents.core") == []
