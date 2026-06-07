from wiki_agents.core import scaffold


def test_scaffold_creates_dirs(tmp_path):
    scaffold.scaffold_vault(tmp_path)
    for d in [
        "00_Inbox/raw", "00_Inbox/browser-clips",
        "10_Claims/pending", "10_Claims/verified",
        "30_Learning/flashcards", "06_Metadata/indexes", "06_Metadata/logs",
        "03_Resources/Concepts",
    ]:
        assert (tmp_path / d).is_dir(), d
    assert (tmp_path / "06_Metadata/indexes/claim-index.md").exists()
    assert (tmp_path / "06_Metadata/logs/ingest-log.md").exists()
