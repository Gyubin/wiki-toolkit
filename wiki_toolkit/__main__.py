"""CLI entry: `uv run wiki init|mcp|lint|search`.

The vault lives outside this code repo. Resolution order: explicit positional arg >
`$WIKI_VAULT` > cwd. Every subcommand goes through `resolve_vault` so none silently
operates on the wrong directory. Only `init` creates or modifies the vault structure;
the other subcommands refuse a directory that does not look like a vault.

기본 서브커맨드는 없다. 예전에는 인자가 없으면 `serve`(웹 앱)였는데 웹 앱을 지웠고,
`mcp`를 기본값으로 두면 `wiki`만 쳤을 때 stdio 서버가 조용히 매달린다. 그냥 usage를 낸다.

환경값은 셸에서 오는 것이 기본이고, 없으면 `$WIKI_ENV_FILE`(기본값: 이 repo 루트의 `.env`)에서
채운다. MCP 서버는 Claude Code가 띄우기 때문에 셸 rc 파일을 거치지 않을 수 있어서 이 통로가 있다.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import schema
from .core import lint as lint_core
from .core import scaffold
from .core import search as search_core


def env_file_path() -> Path:
    override = os.environ.get("WIKI_ENV_FILE")
    return Path(override) if override else Path(__file__).resolve().parent.parent / ".env"


def load_env_file(path: Path | None = None) -> list[str]:
    """`.env`의 KEY=VALUE를 os.environ에 채운다. 이미 있는 값은 덮어쓰지 않는다.

    셸이 우선이다: 셸에 있는 값을 파일이 조용히 바꿔버리면 어느 값으로 돌고 있는지 알 수 없다.
    반환값은 이번에 채운 키 목록 (값은 절대 로그에 남기지 않는다).
    """
    target = Path(path) if path else env_file_path()
    try:
        raw_text = target.read_text(encoding="utf-8")
    except OSError:
        return []
    filled: list[str] = []
    for raw in raw_text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        key, sep, value = line.partition("=")
        if not sep:
            continue
        key, value = key.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if key and key not in os.environ:
            os.environ[key] = value
            filled.append(key)
    return filled


def resolve_vault(explicit: str | None = None) -> Path:
    """Resolve the vault path: explicit arg > $WIKI_VAULT > cwd.

    .env에서 온 $WIKI_VAULT는 셸을 거치지 않아 ~가 그대로 남을 수 있다. 펼쳐 준다.
    """
    return Path(explicit or os.environ.get("WIKI_VAULT") or Path.cwd()).expanduser()


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
    load_env_file()
    args = sys.argv[1:]
    if not args:
        print("usage: wiki init|mcp|lint|search [vault] ...")
        sys.exit(2)
    cmd = args[0]

    if cmd == "init":
        vault = resolve_vault(args[1] if len(args) > 1 else None)
        scaffold.scaffold_vault(vault)
        print(f"scaffolded vault at {vault}")
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
        try:
            idx = search_core.build_index(vault)
        except search_core.EmbeddingUnavailable as e:
            # 일시적 실패(네트워크, 5xx 소진)는 검색을 죽이지 말고 BM25로 강등한다.
            # 설정 오류(키 없음/거부)는 아래에서 지금처럼 안내 + exit 2.
            print(f"(임베딩 불가, BM25 결과만 보여준다: {e})")
            idx = search_core.build_index(vault, embed_fn=search_core._empty_embedder,
                                          vec_cache=None)
        except RuntimeError as e:  # 임베딩 provider 설정 문제는 트레이스백 없이 안내한다
            print(str(e))
            sys.exit(2)
        for r in idx.query(" ".join(rest), 8):
            print(f"[{r['score']}] {r['title']} ({r['ref']})")
        if getattr(idx, "query_degraded", False):
            # 웜 캐시면 빌드는 API 없이 성공하고 첫 원격 호출이 쿼리 임베딩이라,
            # 장애가 여기서 처음 드러난다. SearchIndex.query가 BM25로 강등해 준다.
            print("(임베딩 불가, BM25 결과만 보여준다)")
        return
    if cmd == "mcp":
        vault = _require_vault(resolve_vault(args[1] if len(args) > 1 else None))
        _run_mcp_stdio(vault)
        return
    print(f"unknown command: {cmd}; use 'init', 'mcp', 'lint', or 'search'")
    sys.exit(2)


if __name__ == "__main__":
    main()
