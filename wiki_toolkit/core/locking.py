"""프로세스 간 vault 쓰기 락.

`wiki mcp` 프로세스가 둘 이상 한 vault에 붙으면 쓰기 경로 네 곳이 같이 깨진다:
`ids.next_seq`가 같은 번호를 두 번 발급하고, `.git/index.lock`을 다투고, 스코프
`git add -A`가 다른 프로세스의 미커밋 파일을 내 감사 커밋에 쓸어 담고,
`index.update_index`의 read-modify-write에서 갱신 하나가 사라진다.

그래서 임계구역은 쓰기 핸들러 전체다: 번호 따기 -> 파일 쓰기 -> 인덱스/로그 갱신 ->
git add -> git commit (tools.py의 `_locked`). 짧은 쓰기 구간만 직렬화되므로 비싼
부분(클립 통독, 교차검증, 페이지 초안)은 프로세스끼리 겹쳐 돌 수 있다.

- 락 파일은 vault 밖에 둔다 (기본 ~/.cache/wiki-toolkit/locks/, vault 절대경로의
  해시). vault 안에 두면 쓰기마다 도는 자동 커밋(`git.commit_vault`)에 쓸려 들어갈
  자리를 골라야 하고, vault가 git repo가 아닐 수도 있다. tempdir는 안 된다: macOS와
  systemd의 청소가 오래된 파일을 나이로 지우는데, flock을 쥐고 있어도 타임스탬프가
  안 바뀌어 활발히 쓰는 락 파일도 3일이면 청소 대상으로 보인다. 지워지면 다음
  open()이 새 inode를 만들어 "둘 다 획득"이 된다.
- 락 파일은 절대 지우지 않는다. A가 flock을 쥔 inode를 B가 지우고 다시 만들면
  서로 다른 inode를 쥔 "둘 다 획득"이 된다. 스테일 락 청소는 필요 없다:
  flock은 프로세스가 죽으면 커널이 자동으로 푼다.
- 획득은 블로킹이다(짧은 폴링). 핸들러에 await가 없어 한 프로세스 안에서 쓰기는
  어차피 직렬이지만, 다른 프로세스가 락을 오래 쥐면 이 프로세스의 MCP 서버가 통째로
  기다리게 된다. 그래서 조용히 기다리는 대신 타임아웃을 넘기면 TimeoutError로 죽는다.
"""
from __future__ import annotations

import fcntl
import hashlib
import os
import time
from contextlib import contextmanager
from pathlib import Path

DEFAULT_TIMEOUT = 30.0
_POLL_INTERVAL = 0.05

# 경쟁 재현 테스트 전용. 운영에서 켜면 위의 네 가지가 도로 깨진다.
DISABLE_ENV = "WIKI_WRITE_LOCK_DISABLE"
TIMEOUT_ENV = "WIKI_WRITE_LOCK_TIMEOUT"
LOCK_DIR_ENV = "WIKI_LOCK_DIR"  # 기본 ~/.cache/wiki-toolkit/locks (테스트 격리용 오버라이드)


def lock_path(vault: Path) -> Path:
    """vault 하나당 락 파일 하나. vault 밖이라 커밋에 못 쓸려 들어간다.

    나이 기반 청소가 없는 곳이어야 한다 (모듈 docstring). tempdir 금지.
    """
    base = os.environ.get(LOCK_DIR_ENV, "").strip()
    d = Path(base) if base else Path.home() / ".cache/wiki-toolkit/locks"
    key = hashlib.sha256(str(Path(vault).resolve()).encode("utf-8")).hexdigest()[:16]
    d.mkdir(parents=True, exist_ok=True)
    return d / f"vault-{key}.lock"


@contextmanager
def vault_write_lock(vault: Path, timeout: float | None = None):
    """쓰기 임계구역 하나를 감싼다. 예외가 나도 flock은 반드시 풀린다."""
    if (os.environ.get(DISABLE_ENV) or "").strip().lower() in ("1", "true", "yes"):
        yield
        return
    if timeout is None:
        timeout = float(os.environ.get(TIMEOUT_ENV, DEFAULT_TIMEOUT))
    path = lock_path(vault)
    with path.open("a") as f:
        deadline = time.monotonic() + timeout
        while True:
            try:
                fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"vault 쓰기 락을 {timeout:.1f}초 안에 못 얻었다: {path}\n"
                        "다른 wiki 프로세스가 vault에 쓰는 중이다. 끝나면 다시 시도해라. "
                        f"대기 한도는 {TIMEOUT_ENV}(초)로 조절한다."
                    ) from None
                time.sleep(_POLL_INTERVAL)
        try:
            yield
        finally:
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
