"""Read-only git session collection for wrap-feature."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    try:
        # fixed `git` argv on PATH, no shell, controlled args — deliberate.
        out = subprocess.run(  # noqa: S603
            ["git", "-C", str(repo), *args],  # noqa: S607
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise ValueError(f"git failed in {repo}: {e}") from e
    return out.stdout


def commit_vault(vault: Path, message: str) -> bool:
    """vault가 git repo면 변경을 커밋한다 (설계 문서의 인식론적 감사 추적).

    실패는 조용히 False: 감사 추적이 쓰기 자체를 막으면 안 된다.
    """
    vault = Path(vault)
    if not (vault / ".git").exists():
        return False
    try:
        subprocess.run(  # noqa: S603
            ["git", "-C", str(vault), "add", "-A"],  # noqa: S607
            capture_output=True, check=True,
        )
        r = subprocess.run(  # noqa: S603
            ["git", "-C", str(vault), "commit", "--no-verify", "-m", message],  # noqa: S607
            capture_output=True,
        )
        return r.returncode == 0
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False


def collect_session(repo: Path, base: str, head: str = "HEAD") -> dict:
    repo = Path(repo)
    if not (repo / ".git").exists():
        raise ValueError(f"not a git repo: {repo}")
    rng = f"{base}..{head}"
    diff = _git(repo, "diff", rng)
    files = [f for f in _git(repo, "diff", "--name-only", rng).splitlines() if f]
    commits = []
    for ln in _git(repo, "log", "--format=%H%x09%s", rng).splitlines():
        if "\t" in ln:
            sha, subject = ln.split("\t", 1)
            commits.append({"sha": sha, "subject": subject})
    return {"diff": diff, "changed_files": files, "commits": commits}
