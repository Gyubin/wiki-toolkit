"""CLI entry: `uv run wiki init` (scaffold) | `uv run wiki serve` (default)."""
from __future__ import annotations

import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .core import scaffold
from .core import lint as lint_core
from .core import search as search_core
from . import schema


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
    if cmd == "lint":
        scaffold.scaffold_vault(vault)
        for f in lint_core.run_checks(vault, schema.today_str()):
            print(f"[{f['severity']}] {f['check']} — {f['ref']}: {f['message']}")
        return
    if cmd == "search":
        query = " ".join(args[1:])
        idx = search_core.build_index(Path.cwd())
        for r in idx.query(query, 8):
            print(f"[{r['score']}] {r['title']} ({r['ref']})")
        return
    print(f"unknown command: {cmd}; use 'init' or 'serve'")


if __name__ == "__main__":
    main()
