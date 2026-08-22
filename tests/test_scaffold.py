from wiki_agents.core import scaffold


def test_scaffold_creates_dirs(tmp_path):
    scaffold.scaffold_vault(tmp_path)
    for d in [
        "00_Inbox/raw", "00_Inbox/browser-clips",
        "00_Inbox/coding-agent-sessions", "00_Inbox/unprocessed",
        "10_Claims/pending", "10_Claims/verified",
        "30_Learning/flashcards", "06_Metadata/indexes", "06_Metadata/logs",
        "03_Resources/Concepts",
    ]:
        assert (tmp_path / d).is_dir(), d
    assert (tmp_path / "06_Metadata/indexes/claim-index.md").exists()
    assert (tmp_path / "06_Metadata/logs/ingest-log.md").exists()


def test_scaffold_seeds_templates(tmp_path):
    scaffold.scaffold_vault(tmp_path)
    for name in ("source", "claim", "wiki-page", "learning-item", "session", "decision"):
        p = tmp_path / "06_Metadata/templates" / f"{name}.md"
        assert p.exists(), name
        assert p.read_text(encoding="utf-8").startswith("---\n")


def test_scaffold_keeps_empty_dirs_trackable(tmp_path):
    # git은 빈 디렉토리를 추적하지 못한다: .gitkeep이 있어야 clone 후에도 구조가 산다
    scaffold.scaffold_vault(tmp_path)
    assert (tmp_path / "02_Areas/.gitkeep").exists()
    assert (tmp_path / "10_Claims/rejected/.gitkeep").exists()
