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
