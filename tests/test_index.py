from wiki_agent.core import index


def test_append_log(vault):
    index.append_log(vault, "ingest-log", "first entry")
    index.append_log(vault, "ingest-log", "second entry")
    text = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "first entry" in text
    assert "second entry" in text


def test_update_index_upserts(vault):
    index.update_index(vault, "claim-index", "claim-20260607-001", "claim A — unverified")
    index.update_index(vault, "claim-index", "claim-20260607-001", "claim A — verified")
    text = (vault / "06_Metadata/indexes/claim-index.md").read_text(encoding="utf-8")
    assert text.count("claim-20260607-001") == 1  # upsert, not duplicate
    assert "verified" in text
    assert "unverified" not in text
