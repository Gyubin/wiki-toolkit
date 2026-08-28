from wiki_toolkit.core import index


def test_append_log(vault):
    index.append_log(vault, "ingest-log", "first entry")
    index.append_log(vault, "ingest-log", "second entry")
    text = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "first entry" in text
    assert "second entry" in text


def test_update_index_upserts(vault):
    index.update_index(vault, "claim-index", "claim-20260607-001", "claim A - unverified")
    index.update_index(vault, "claim-index", "claim-20260607-001", "claim A - verified")
    text = (vault / "06_Metadata/indexes/claim-index.md").read_text(encoding="utf-8")
    assert text.count("claim-20260607-001") == 1  # upsert, not duplicate
    assert "verified" in text
    assert "unverified" not in text


def test_update_index_does_not_delete_lines_mentioning_the_id(vault):
    index.update_index(vault, "claim-index", "claim-20260607-002",
                       "claim B supersedes claim-20260607-001")
    index.update_index(vault, "claim-index", "claim-20260607-001", "claim A - verified")
    text = (vault / "06_Metadata/indexes/claim-index.md").read_text(encoding="utf-8")
    assert "claim B supersedes" in text  # 언급만 된 줄은 살아남아야 한다
    assert "claim A - verified" in text


def test_log_lines_contain_no_em_dash(vault):
    index.append_log(vault, "ingest-log", "captured something")
    text = (vault / "06_Metadata/logs/ingest-log.md").read_text(encoding="utf-8")
    assert "—" not in text


def test_update_index_flattens_newlines(vault):
    """줄 단위 upsert에서 두 줄짜리 항목은 둘째 줄이 고아로 영원히 남는다 (감사에서 재현)."""
    index.update_index(vault, "claim-index", "claim-20260828-001",
                       "첫 줄\n둘째 줄 - unverified")
    index.update_index(vault, "claim-index", "claim-20260828-001", "갱신된 줄 - attributed")
    text = (vault / "06_Metadata/indexes/claim-index.md").read_text(encoding="utf-8")
    assert "둘째 줄" not in text
    assert text.count("claim-20260828-001") == 1
