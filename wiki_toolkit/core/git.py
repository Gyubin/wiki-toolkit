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


def commit_vault(vault: Path, message: str, paths: list[str] | None = None) -> bool:
    """vault가 git repo면 변경을 커밋한다 (설계 문서의 인식론적 감사 추적).

    paths는 이번 쓰기가 건드린 최상위 디렉터리 목록. 경로를 한정해야 사용자가
    Obsidian에서 고치던 무관한 파일이 에이전트 커밋에 쓸려 들어가지 않는다.
    실패는 조용히 False: 감사 추적이 쓰기 자체를 막으면 안 된다.
    --no-verify: 에이전트의 감사 커밋이 사용자 훅 실패로 막히지 않게 한다.
    """
    vault = Path(vault)
    if not (vault / ".git").exists():
        return False
    scope = [p for p in (paths or ["."]) if (vault / p).exists()]
    if not scope:
        return False
    try:
        subprocess.run(  # noqa: S603
            ["git", "-C", str(vault), "add", "-A", "--", *scope],  # noqa: S607
            capture_output=True, check=True,
        )
        check = subprocess.run(  # noqa: S603
            ["git", "-C", str(vault), "diff", "--cached", "--quiet", "--", *scope],  # noqa: S607
            capture_output=True,
        )
        if check.returncode == 0:
            # 스코프에 커밋할 변경이 없다 (같은 내용을 다시 쓴 경우 등). 감사 추적이
            # 빠진 게 아니므로 실패로 보고하지 않는다. 보고하면 도구가 멀쩡한 vault를
            # 두고 "git 상태를 확인해라"라고 경고한다.
            return True
        # commit에도 pathspec을 건다. add만 한정하면 사용자가 미리 스테이징해 둔
        # 무관한 파일이 이 커밋에 쓸려 들어간다 (감사 발견; docstring의 약속 위반).
        # 알려진 한계: merge 진행 중(MERGE_HEAD)에는 git이 partial commit을 거부해
        # False가 되고 경고가 붙는다. merge를 끝내면 다음 쓰기부터 다시 커밋된다.
        r = subprocess.run(  # noqa: S603
            ["git", "-C", str(vault), "commit", "--no-verify",  # noqa: S607
             "-m", message, "--", *scope],
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
