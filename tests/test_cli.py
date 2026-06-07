"""CLI vault-path resolution: every subcommand must honor the passed vault / $WIKI_VAULT,
never hardcode cwd. Guards the code/vault separation (harness engineering)."""
from pathlib import Path

import wiki_agents.__main__ as cli


def test_resolve_vault_explicit_wins(monkeypatch):
    monkeypatch.setenv("WIKI_VAULT", "/from/env")
    assert cli.resolve_vault("/explicit") == Path("/explicit")


def test_resolve_vault_env_fallback(monkeypatch):
    monkeypatch.setenv("WIKI_VAULT", "/from/env")
    assert cli.resolve_vault(None) == Path("/from/env")


def test_resolve_vault_cwd_default(monkeypatch):
    monkeypatch.delenv("WIKI_VAULT", raising=False)
    assert cli.resolve_vault(None) == Path.cwd()


def test_search_uses_resolved_vault(monkeypatch, tmp_path):
    """`search` must index the resolved vault, not Path.cwd()."""
    monkeypatch.setenv("WIKI_VAULT", str(tmp_path))
    seen = {}

    class _Idx:
        def query(self, q, k):
            return []

    def fake_build_index(path):
        seen["path"] = path
        return _Idx()

    monkeypatch.setattr(cli.search_core, "build_index", fake_build_index)
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "search", "hello", "world"])
    cli.main()
    assert seen["path"] == tmp_path


def test_serve_uses_passed_vault(monkeypatch, tmp_path):
    """`serve <vault>` must scaffold/serve the passed path, not cwd."""
    seen = {}
    monkeypatch.setattr(cli.scaffold, "scaffold_vault", lambda v: seen.setdefault("scaffold", v))
    monkeypatch.setattr(cli, "create_app", lambda v: seen.setdefault("app", v))
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "serve", str(tmp_path)])
    cli.main()
    assert seen["scaffold"] == tmp_path
    assert seen["app"] == tmp_path
