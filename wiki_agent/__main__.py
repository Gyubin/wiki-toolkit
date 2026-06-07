"""CLI entry: `uv run wiki init` (scaffold) | `uv run wiki serve` (default).

The vault lives outside this code repo. Resolution order: explicit positional arg >
`$WIKI_VAULT` > cwd. Every subcommand goes through `resolve_vault` so none silently
operates on the wrong directory.
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


def main() -> None:
    args = sys.argv[1:]
    cmd = args[0] if args else "serve"

    if cmd == "init":
        vault = resolve_vault(args[1] if len(args) > 1 else None)
        scaffold.scaffold_vault(vault)
        print(f"scaffolded vault at {vault}")
        return
    if cmd == "serve":
        vault = resolve_vault(args[1] if len(args) > 1 else None)
        scaffold.scaffold_vault(vault)  # idempotent
        app = create_app(vault)
        uvicorn.run(app, host="127.0.0.1", port=8765)
        return
    if cmd == "lint":
        vault = resolve_vault(args[1] if len(args) > 1 else None)
        scaffold.scaffold_vault(vault)
        for f in lint_core.run_checks(vault, schema.today_str()):
            print(f"[{f['severity']}] {f['check']} — {f['ref']}: {f['message']}")
        return
    if cmd == "search":
        query = " ".join(args[1:])
        idx = search_core.build_index(resolve_vault())
        for r in idx.query(query, 8):
            print(f"[{r['score']}] {r['title']} ({r['ref']})")
        return
    print(f"unknown command: {cmd}; use 'init', 'serve', 'lint', or 'search'")


if __name__ == "__main__":
    main()
