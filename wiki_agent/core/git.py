"""Read-only git session collection for wrap-feature."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _git(repo: Path, *args: str) -> str:
    try:
        out = subprocess.run(
            ["git", "-C", str(repo), *args],
            capture_output=True, text=True, check=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        raise ValueError(f"git failed in {repo}: {e}") from e
    return out.stdout


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
