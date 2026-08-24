"""CLI vault-path resolution: every subcommand must honor the passed vault / $WIKI_VAULT,
never hardcode cwd. Guards the code/vault separation (harness engineering)."""
import os
from pathlib import Path

import pytest

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


class _Idx:
    def query(self, q, k):
        return []


def test_search_uses_resolved_vault(monkeypatch, vault):
    """`search` must index the resolved vault, not Path.cwd()."""
    monkeypatch.setenv("WIKI_VAULT", str(vault))
    seen = {}

    def fake_build_index(path):
        seen["path"] = path
        return _Idx()

    monkeypatch.setattr(cli.search_core, "build_index", fake_build_index)
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "search", "hello", "world"])
    cli.main()
    assert seen["path"] == vault


def test_search_accepts_leading_vault_dir(monkeypatch, vault):
    seen = {}

    def fake_build_index(path):
        seen["path"] = path
        return _Idx()

    monkeypatch.delenv("WIKI_VAULT", raising=False)
    monkeypatch.setattr(cli.search_core, "build_index", fake_build_index)
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "search", str(vault), "hello"])
    cli.main()
    assert seen["path"] == vault


def test_serve_uses_passed_vault(monkeypatch, vault):
    """`serve <vault>` must serve the passed path, not cwd."""
    seen = {}
    monkeypatch.setattr(cli, "create_app", lambda v: seen.setdefault("app", v))
    monkeypatch.setattr(cli.uvicorn, "run", lambda *a, **k: None)
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "serve", str(vault)])
    cli.main()
    assert seen["app"] == vault


def test_serve_refuses_non_vault_dir(monkeypatch, tmp_path):
    """scaffold는 init 전용: serve가 아무 디렉토리나 vault 구조로 오염시키면 안 된다."""
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "serve", str(tmp_path)])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2
    assert not (tmp_path / "06_Metadata").exists()  # 아무것도 만들지 않았다


def test_lint_is_report_only_and_refuses_non_vault(monkeypatch, tmp_path):
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "lint", str(tmp_path)])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2
    assert list(tmp_path.iterdir()) == []  # lint가 디렉토리를 만들면 안 된다


def test_lint_exit_code_reflects_errors(monkeypatch, vault):
    monkeypatch.setattr(cli.lint_core, "run_checks",
                        lambda v, d: [{"severity": "error", "check": "x",
                                       "ref": "r", "message": "m"}])
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "lint", str(vault)])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 1


def test_unknown_command_exits_nonzero(monkeypatch):
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "frobnicate"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2


def test_mcp_subcommand_dispatches(monkeypatch, vault):
    seen = {}
    monkeypatch.setattr(cli, "_run_mcp_stdio", lambda v: seen.setdefault("vault", v))
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "mcp", str(vault)])
    cli.main()
    assert seen["vault"] == vault


def test_search_reports_embedder_config_error(vault, monkeypatch, capsys):
    """임베딩 provider 설정 문제는 트레이스백이 아니라 안내 + exit 2로 나와야 한다."""
    def boom(path):
        raise RuntimeError("OPENAI_API_KEY가 없다")

    monkeypatch.setattr(cli.search_core, "build_index", boom)
    monkeypatch.setattr(cli.sys, "argv", ["wiki", "search", str(vault), "질의"])
    with pytest.raises(SystemExit) as e:
        cli.main()
    assert e.value.code == 2
    assert "OPENAI_API_KEY" in capsys.readouterr().out


def test_load_env_file_fills_only_missing_keys(tmp_path, monkeypatch):
    """.env는 셸에 없는 값만 채운다. 셸이 항상 이긴다."""
    monkeypatch.setattr(cli.os, "environ", dict(os.environ))  # 실제 환경 오염 방지
    env = tmp_path / ".env"
    env.write_text(
        "# 주석\n\n"
        'export OPENAI_API_KEY="sk-from-file"\n'
        "WIKI_EMBED_MODEL='text-embedding-3-small'\n"
        "WIKI_EMBED_DIM=1024\n"
        "BROKEN_LINE_WITHOUT_EQUALS\n",
        encoding="utf-8")
    monkeypatch.setenv("WIKI_ENV_FILE", str(env))
    monkeypatch.setenv("WIKI_EMBED_DIM", "256")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("WIKI_EMBED_MODEL", raising=False)

    filled = cli.load_env_file()
    assert cli.os.environ["OPENAI_API_KEY"] == "sk-from-file"      # 따옴표 제거 + export 허용
    assert cli.os.environ["WIKI_EMBED_MODEL"] == "text-embedding-3-small"
    assert cli.os.environ["WIKI_EMBED_DIM"] == "256"               # 셸 값을 덮지 않는다
    assert set(filled) == {"OPENAI_API_KEY", "WIKI_EMBED_MODEL"}


def test_load_env_file_absent_is_noop(tmp_path, monkeypatch):
    monkeypatch.setenv("WIKI_ENV_FILE", str(tmp_path / "no-such.env"))
    assert cli.load_env_file() == []


def test_env_file_path_defaults_to_repo_root(monkeypatch):
    monkeypatch.delenv("WIKI_ENV_FILE", raising=False)
    p = cli.env_file_path()
    assert p.name == ".env"
    assert (p.parent / "pyproject.toml").exists()  # repo 루트
