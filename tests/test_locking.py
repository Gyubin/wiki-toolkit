"""프로세스 간 vault 쓰기 락 테스트.

한 프로세스 안에서는 쓰기 핸들러에 await가 없어 이벤트 루프가 중간에 못 끼어들므로,
이 경쟁은 단일 프로세스 테스트로는 재현되지 않는다. multiprocessing으로 프로세스 둘을
띄워서 잰다. 라운드마다 Barrier로 두 프로세스를 같은 순간에 풀어 경쟁 창을 넓힌다.

느린 테스트다 (spawn 두 번 + git 커밋 수십 개, 수 초).
"""
from __future__ import annotations

import asyncio
import multiprocessing as mp
import os
import queue
import subprocess
from pathlib import Path

import pytest

from wiki_toolkit import schema, tools
from wiki_toolkit.core import locking, scaffold

# ---------------------------------------------------------------- 워커 (spawn 대상)


def _worker(vault_str: str, tag: str, n_claims: int, n_sources: int,
            barrier, errors, disable_lock: bool) -> None:
    if disable_lock:
        os.environ[locking.DISABLE_ENV] = "1"
    handlers = {t.name: t.handler for t in tools.build_wiki_tools(Path(vault_str))}

    def _round(name: str, args: dict) -> None:
        # barrier 실패(하네스 고장)는 잡지 않는다: 워커가 죽어 exitcode != 0으로
        # 드러나야 한다. errs에 섞이면 음성 테스트가 경쟁의 증거로 오독한다.
        barrier.wait(timeout=60)
        try:
            asyncio.run(handlers[name](args))
        except Exception as e:  # noqa: BLE001 - 핸들러 예외는 부모가 판정한다
            errors.put(f"{tag}/{name}: {type(e).__name__}: {e}")

    for i in range(n_claims):
        _round("create_claim",
               {"claim": f"경쟁 테스트 주장 {tag} {i}", "claim_type": "opinion"})
    for i in range(n_sources):
        _round("create_source",
               {"origin": "browser", "title": f"race-{tag}-{i}",
                "content": f"경쟁 테스트 본문 {tag} {i} " * 30})


def _hold_lock(vault_str: str, acquired, release) -> None:
    with locking.vault_write_lock(Path(vault_str)):
        acquired.set()
        release.wait(timeout=60)


# ---------------------------------------------------------------- 헬퍼


def _git(vault: Path, *args: str) -> str:
    r = subprocess.run(["git", "-C", str(vault), *args],
                       check=True, capture_output=True, text=True)
    return r.stdout


@pytest.fixture(autouse=True)
def _isolated_lock_dir(monkeypatch, tmp_path_factory):
    """테스트마다 락 디렉터리를 분리한다 (~/.cache에 테스트 락 파일이 쌓이지 않게).

    spawn된 자식 프로세스는 부모의 환경을 물려받으므로 env로 넘긴다.
    """
    monkeypatch.setenv(locking.LOCK_DIR_ENV, str(tmp_path_factory.mktemp("locks")))


@pytest.fixture
def git_vault(tmp_path):
    vault = tmp_path / "vault"
    vault.mkdir()
    scaffold.scaffold_vault(vault)
    for a in (["init"], ["config", "user.email", "t@t"], ["config", "user.name", "t"]):
        subprocess.run(["git", "-C", str(vault), *a], check=True, capture_output=True)
    _git(vault, "add", "-A")
    _git(vault, "commit", "-m", "seed")
    return vault


def _run_two(vault: Path, n_claims: int, n_sources: int, disable_lock: bool) -> list[str]:
    ctx = mp.get_context("spawn")
    barrier = ctx.Barrier(2)
    errors = ctx.Queue()
    procs = [ctx.Process(target=_worker,
                         args=(str(vault), tag, n_claims, n_sources,
                               barrier, errors, disable_lock))
             for tag in ("a", "b")]
    for p in procs:
        p.start()
    for p in procs:
        p.join(timeout=240)
    alive = [p for p in procs if p.is_alive()]
    for p in alive:
        p.terminate()
    assert not alive, "워커가 제 시간에 안 끝났다 (barrier 데드락?)"
    codes = [p.exitcode for p in procs]
    assert codes == [0, 0], f"워커가 죽었다 (하네스 고장): exitcodes {codes}"
    out: list[str] = []
    while True:
        try:
            out.append(errors.get(timeout=0.5))
        except queue.Empty:
            return out


def _ids_under(vault: Path, top: str, prefix: str) -> list[str]:
    ids_ = []
    for p in (vault / top).rglob("*.md"):
        try:
            meta, _ = schema.parse_doc(p.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001 - 템플릿 등 파싱 불가 파일은 대상이 아니다
            continue
        if str(meta.get("id", "")).startswith(f"{prefix}-"):
            ids_.append(str(meta["id"]))
    return ids_


# ---------------------------------------------------------------- 본 테스트


def test_two_processes_write_safely_with_lock(git_vault):
    """프로세스 둘이 동시에 써도 (a) id 중복 0건, (b) 커밋 수 = 쓰기 수,
    (c) 커밋마다 자기 파일 하나만 (함정 3: 스코프 git add가 남의 파일을 쓸어 담는 것)."""
    n_claims, n_sources = 5, 3
    errs = _run_two(git_vault, n_claims, n_sources, disable_lock=False)
    assert errs == []

    # (a) id 중복 0건
    claim_ids = _ids_under(git_vault, "10_Claims", "claim")
    source_ids = _ids_under(git_vault, "00_Inbox", "source")
    assert len(claim_ids) == 2 * n_claims
    assert len(set(claim_ids)) == len(claim_ids)
    assert len(source_ids) == 2 * n_sources
    assert len(set(source_ids)) == len(source_ids)

    # (b) 커밋 수 = 쓰기 수
    log = [ln for ln in _git(git_vault, "log", "--format=%H%x09%s").splitlines()
           if "\twiki: created" in ln]
    assert len(log) == 2 * (n_claims + n_sources)

    # (c) 커밋마다 06_Metadata 밖 파일이 정확히 하나 (자기가 만든 파일)
    for ln in log:
        sha = ln.split("\t", 1)[0]
        files = [f for f in _git(git_vault, "show", "--name-only", "--format=", sha)
                 .splitlines() if f.strip()]
        payload = [f for f in files if not f.startswith("06_Metadata")]
        assert len(payload) == 1, (sha, payload)


def test_race_reproduces_without_lock(git_vault):
    """락을 끄면 같은 하네스가 경쟁을 실제로 재현해야 한다.

    이 테스트가 실패하면(이상 0건) 하네스가 경쟁을 재현하지 못하는 것이고, 그러면
    위의 통과 테스트도 아무것도 증명하지 않는다. source는 파일명이 제목이라 id가
    겹쳐도 파일 둘이 조용히 살아남으므로, 중복 id가 파일에 증거로 남는다.
    """
    n_sources = 12
    errs = _run_two(git_vault, 0, n_sources, disable_lock=True)
    source_ids = _ids_under(git_vault, "00_Inbox", "source")
    # 하네스가 실제로 일을 다 했는지 먼저 확인한다. 시도한 쓰기는 파일이 되거나
    # 핸들러 예외가 됐어야 한다. 이게 없으면 "아무것도 안 했는데 통과"가 가능하다.
    assert len(source_ids) + len(errs) == 2 * n_sources, (source_ids, errs)
    duplicated = len(source_ids) != len(set(source_ids))
    assert duplicated or errs, "경쟁이 재현되지 않았다: 하네스(barrier/라운드 수)를 의심해라"


def test_write_lock_times_out_with_a_clear_error(vault):
    """다른 프로세스가 락을 쥐고 있으면 조용히 기다리지 않고 TimeoutError로 죽는다."""
    ctx = mp.get_context("spawn")
    acquired, release = ctx.Event(), ctx.Event()
    p = ctx.Process(target=_hold_lock, args=(str(vault), acquired, release))
    p.start()
    try:
        assert acquired.wait(timeout=60)
        with pytest.raises(TimeoutError, match="쓰기 락"):
            with locking.vault_write_lock(vault, timeout=0.3):
                pass
    finally:
        release.set()
        p.join(timeout=60)


def test_write_handler_takes_the_lock_and_read_handler_does_not(vault, monkeypatch):
    """쓰기 핸들러는 락을 잡고(막히면 TimeoutError), 읽기 핸들러는 락과 무관하다."""
    ctx = mp.get_context("spawn")
    acquired, release = ctx.Event(), ctx.Event()
    p = ctx.Process(target=_hold_lock, args=(str(vault), acquired, release))
    p.start()
    try:
        assert acquired.wait(timeout=60)
        monkeypatch.setenv(locking.TIMEOUT_ENV, "0.3")
        h = {t.name: t.handler for t in tools.build_wiki_tools(vault)}
        with pytest.raises(TimeoutError):
            asyncio.run(h["create_claim"]({"claim": "x", "claim_type": "opinion"}))
        out = asyncio.run(h["list_pending"]({}))
        assert "none" in out["content"][0]["text"]
    finally:
        release.set()
        p.join(timeout=60)


def test_lock_path_is_outside_the_vault_and_stable(vault, monkeypatch):
    p1, p2 = locking.lock_path(vault), locking.lock_path(vault)
    assert p1 == p2
    assert not p1.is_relative_to(vault)  # 함정 1: 자동 커밋에 쓸려 들어갈 수 없다
    # 기본값은 ~/.cache 밑이다. tempdir는 나이 기반 청소가 락 파일을 지울 수 있어 금지
    # (flock을 쥐고 있어도 타임스탬프가 안 바뀐다. locking.py 모듈 docstring 참조).
    monkeypatch.delenv(locking.LOCK_DIR_ENV, raising=False)
    assert locking.lock_path(vault).is_relative_to(Path.home() / ".cache")


def test_disable_env_makes_lock_a_noop(vault, monkeypatch):
    monkeypatch.setenv(locking.DISABLE_ENV, "1")
    # 진짜 락이면 두 번째 획득(같은 프로세스, 다른 fd)이 타임아웃으로 죽는다
    with locking.vault_write_lock(vault, timeout=0.3), \
         locking.vault_write_lock(vault, timeout=0.3):
        pass


def test_disable_env_zero_keeps_the_lock(vault, monkeypatch):
    """"0"이나 "false"는 락을 끄지 않는다 (truthiness가 아니라 긍정값 화이트리스트).

    WIKI_WRITE_LOCK_DISABLE=0을 "켜 둔다"는 뜻으로 export한 래퍼가 락을 조용히
    꺼버리면 네 가지 경쟁이 도로 살아난다 (2026-08-30 검토에서 확정된 발견).
    """
    monkeypatch.setenv(locking.DISABLE_ENV, "0")
    with locking.vault_write_lock(vault, timeout=0.3):
        with pytest.raises(TimeoutError):
            with locking.vault_write_lock(vault, timeout=0.1):
                pass
