"""CLI entry: `uv run wiki init|serve|lint|search|mcp` (default `serve`).

The vault lives outside this code repo. Resolution order: explicit positional arg >
`$WIKI_VAULT` > cwd. Every subcommand goes through `resolve_vault` so none silently
operates on the wrong directory. Only `init` creates or modifies the vault structure;
the other subcommands refuse a directory that does not look like a vault.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

from . import schema
from .app import create_app
from .core import lint as lint_core
from .core import scaffold
from .core import search as search_core


def resolve_vault(explicit: str | None = None) -> Path:
    """Resolve the vault path: explicit arg > $WIKI_VAULT > cwd."""
    return Path(explicit or os.environ.get("WIKI_VAULT") or Path.cwd())


def _require_vault(vault: Path) -> Path:
    if not (Path(vault) / "06_Metadata").is_dir():
        print(f"{vault} does not look like a vault (no 06_Metadata/).")
        print("Run 'uv run wiki init <path>' first, or set $WIKI_VAULT / pass the vault path.")
        sys.exit(2)
    return vault


def _run_mcp_stdio(vault: Path) -> None:
    """같은 wiki 도구 세트를 stdio MCP 서버로 노출한다 (Claude Code에 등록용).

    예: claude mcp add wiki -- uv run --directory <이 repo> wiki mcp <vault>
    """
    import anyio
    from mcp.server.stdio import stdio_server

    from .tools import build_wiki_server

    server = build_wiki_server(vault)["instance"]

    async def _serve() -> None:
        async with stdio_server() as (read, write):
            await server.run(read, write, server.create_initialization_options())

    anyio.run(_serve)


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "serve"

    if cmd == "init":
        vault = resolve_vault(args[1] if len(args) > 1 else None)
        scaffold.scaffold_vault(vault)
        print(f"scaffolded vault at {vault}")
        return
    if cmd == "serve":
        vault = _require_vault(resolve_vault(args[1] if len(args) > 1 else None))
        app = create_app(vault)
        uvicorn.run(app, host="127.0.0.1", port=8765)
        return
    if cmd == "lint":
        vault = _require_vault(resolve_vault(args[1] if len(args) > 1 else None))
        findings = lint_core.run_checks(vault, schema.today_str())
        for f in findings:
            print(f"[{f['severity']}] {f['check']} - {f['ref']}: {f['message']}")
        errors = sum(1 for f in findings if f["severity"] == "error")
        print(f"{len(findings)} finding(s), {errors} error(s)")
        sys.exit(1 if errors else 0)
    if cmd == "search":
        rest = args[1:]
        explicit = None
        if rest and Path(rest[0]).is_dir():
            explicit, rest = rest[0], rest[1:]
        if not rest:
            print("usage: wiki search [vault] <query...>")
            sys.exit(2)
        vault = _require_vault(resolve_vault(explicit))
        idx = search_core.build_index(vault)
        for r in idx.query(" ".join(rest), 8):
            print(f"[{r['score']}] {r['title']} ({r['ref']})")
        return
    if cmd == "mcp":
        vault = _require_vault(resolve_vault(args[1] if len(args) > 1 else None))
        _run_mcp_stdio(vault)
        return
    print(f"unknown command: {cmd}; use 'init', 'serve', 'lint', 'search', or 'mcp'")
    sys.exit(2)


if __name__ == "__main__":
    main()
