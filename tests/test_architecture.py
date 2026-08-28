"""Mechanical enforcement of the module dependency layering (harness engineering)."""
import ast
from pathlib import Path

PKG_ROOT = Path(__file__).resolve().parent.parent / "wiki_toolkit"
FORBIDDEN_EXTERNAL = {"claude_agent_sdk", "fastapi", "uvicorn", "starlette"}
ORCH = {"tools", "__main__"}


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
            if m == f"wiki_toolkit.{orch}" or m.startswith(f"wiki_toolkit.{orch}."):
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
    assert not [m for m in refs if m.split(".")[0] == "wiki_toolkit"], refs


def test_no_module_imports_a_web_framework():
    """웹 앱을 지운 뒤로 이 테스트는 약해진 게 아니라 강해졌다.

    예전에는 app.py만 예외로 빼고 나머지를 검사했다. 지금은 예외가 없다.
    fastapi나 starlette가 다시 들어오면 여기서 걸린다.
    """
    offenders = {}
    for f in PKG_ROOT.rglob("*.py"):
        refs = referenced_modules(f.read_text(encoding="utf-8"), _pkg_of(f))
        web = [m for m in refs if m.split(".")[0] in {"fastapi", "starlette", "uvicorn"}]
        if web:
            offenders[str(f.relative_to(PKG_ROOT))] = web
    assert not offenders, offenders


_LAYER = {"__init__": 0, "schema": 0, "core": 1, "tools": 2, "__main__": 3}


def _layer_of(f: Path) -> str:
    rel = f.resolve().relative_to(PKG_ROOT)
    return "core" if rel.parts[0] == "core" else rel.stem


def test_imports_flow_upward_only():
    """문서가 주장하는 전체 레이어 순서를 전부 기계적으로 강제한다."""
    offenders = {}
    for f in PKG_ROOT.rglob("*.py"):
        src = _layer_of(f)
        if src not in _LAYER:
            continue
        bad = []
        for m in referenced_modules(f.read_text(encoding="utf-8"), _pkg_of(f)):
            parts = m.split(".")
            if parts[0] != "wiki_toolkit" or len(parts) < 2:
                continue
            tgt = parts[1]
            if tgt in _LAYER and _LAYER[tgt] > _LAYER[src]:
                bad.append(m)
        if bad:
            offenders[str(f.relative_to(PKG_ROOT))] = sorted(set(bad))
    assert not offenders, offenders


def test_checker_catches_violation():
    assert "claude_agent_sdk" in core_violations(
        "from claude_agent_sdk import tool\nfrom .. import schema\n", "wiki_toolkit.core")
    assert any("wiki_toolkit.tools" in m for m in core_violations(
        "from ..tools import WIKI_TOOL_NAMES\n", "wiki_toolkit.core"))
    assert core_violations("from .. import schema\nfrom . import index\n",
                           "wiki_toolkit.core") == []
