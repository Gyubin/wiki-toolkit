import subprocess

import pytest

from wiki_agents.core import git


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


def test_commit_vault_nothing_to_commit(vault):
    _git_vault(vault)
    git.commit_vault(vault, "first")
    assert git.commit_vault(vault, "empty") is False
