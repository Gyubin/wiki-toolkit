import subprocess
import pytest
from wiki_agent.core import git


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
