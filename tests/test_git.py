import subprocess

import pytest

from wiki_toolkit.core import git


@pytest.fixture
def repo(tmp_path):
    r = tmp_path / "myrepo"
    r.mkdir()
    def run(*a):
        subprocess.run(["git", "-C", str(r), *a], check=True, capture_output=True)
    run("init")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    (r / "a.txt").write_text("hello\n")
    run("add", ".")
    run("commit", "-m", "first")
    (r / "a.txt").write_text("hello world\n")
    run("add", ".")
    run("commit", "-m", "second: change a.txt")
    return r


def test_collect_session(repo):
    s = git.collect_session(repo, "HEAD~1", "HEAD")
    assert "a.txt" in s["changed_files"]
    assert any("second" in c["subject"] for c in s["commits"])
    assert "hello world" in s["diff"]


def test_collect_session_rejects_non_git(tmp_path):
    with pytest.raises(ValueError):
        git.collect_session(tmp_path, "HEAD~1", "HEAD")


def _git_vault(vault):
    def run(*a):
        subprocess.run(["git", "-C", str(vault), *a], check=True, capture_output=True)
    run("init")
    run("config", "user.email", "t@t")
    run("config", "user.name", "t")
    return vault


def test_commit_vault_records_changes(vault):
    _git_vault(vault)
    (vault / "10_Claims/pending/claim-20260101-001.md").write_text("x", encoding="utf-8")
    assert git.commit_vault(vault, "wiki: created claim-20260101-001") is True
    log = subprocess.run(["git", "-C", str(vault), "log", "--oneline"],
                         capture_output=True, text=True).stdout
    assert "claim-20260101-001" in log


def test_commit_vault_noop_outside_git(vault):
    # git repo가 아니면 조용히 False (예외 없음)
    assert git.commit_vault(vault, "msg") is False


def test_commit_vault_nothing_to_commit_is_not_a_failure(vault):
    """같은 내용을 다시 쓰면 커밋할 변경이 없다. 그건 감사 추적 실패가 아니므로
    False(경고 대상)가 아니라 True를 돌려준다."""
    _git_vault(vault)
    git.commit_vault(vault, "first")
    assert git.commit_vault(vault, "empty") is True


def test_commit_vault_scoped_paths_leave_user_edits_alone(vault):
    _git_vault(vault)
    git.commit_vault(vault, "seed")
    user_note = vault / "02_Areas" / "my-note.md"
    user_note.write_text("사용자가 Obsidian에서 고치는 중\n", encoding="utf-8")
    (vault / "10_Claims/pending/claim-20260101-001.md").write_text("x", encoding="utf-8")
    assert git.commit_vault(vault, "wiki: created claim",
                            paths=["10_Claims", "06_Metadata"]) is True
    status = subprocess.run(["git", "-C", str(vault), "status", "--short"],
                            capture_output=True, text=True).stdout
    assert "my-note.md" in status  # 사용자 편집은 커밋되지 않고 남아 있어야 한다


def test_commit_vault_does_not_sweep_user_staged_files(vault):
    """add만 paths로 한정하고 commit에 pathspec이 없으면, 사용자가 커밋하려고
    스테이징해 둔 무관한 파일이 에이전트의 감사 커밋에 쓸려 들어간다 (감사 발견)."""
    _git_vault(vault)
    git.commit_vault(vault, "seed")
    staged = vault / "02_Areas" / "staged-by-user.md"
    staged.write_text("사용자가 add까지 해둔 파일\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(vault), "add", "02_Areas"],
                   check=True, capture_output=True)
    (vault / "10_Claims/pending/claim-20260101-001.md").write_text("x", encoding="utf-8")
    assert git.commit_vault(vault, "wiki: created claim",
                            paths=["10_Claims", "06_Metadata"]) is True
    show = subprocess.run(["git", "-C", str(vault), "show", "--name-only", "HEAD"],
                          capture_output=True, text=True).stdout
    assert "claim-20260101-001" in show
    assert "staged-by-user" not in show
    status = subprocess.run(["git", "-C", str(vault), "status", "--short"],
                            capture_output=True, text=True).stdout
    assert "staged-by-user" in status  # 스테이징된 채 그대로 남아 있다
