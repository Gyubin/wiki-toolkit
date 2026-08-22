from wiki_agents import schema
from wiki_agents.core import claims, index, lint, wiki


def _seed(vault):
    (vault / "10_Claims/verified/claim-20260101-001.md").write_text(
        schema.render_doc(
            {"type": "claim", "id": "claim-20260101-001", "claim_type": "technical_fact",
             "status": "unverified", "claim": "misfiled", "speaker": "",
             "source_refs": ["s1"], "evidence_refs": [], "sensitivity": "personal"},
            "## Claim\n\nmisfiled\n"), encoding="utf-8")
    claims.create_claim(vault, claim="needs source", claim_type="technical_fact",
                        source_refs=[], date_str="2026-01-02", seq=1)
    (vault / "10_Claims/verified/claim-20260103-001.md").write_text(
        schema.render_doc(
            {"type": "claim", "id": "claim-20260103-001", "claim_type": "technical_fact",
             "status": "verified", "claim": "ev", "speaker": "",
             "source_refs": ["s1"], "evidence_refs": [], "sensitivity": "personal"},
            "## Claim\n\nev\n"), encoding="utf-8")
    claims.create_claim(vault, claim="dup one two three", claim_type="opinion",
                        source_refs=["s"], date_str="2026-01-04", seq=1)
    claims.create_claim(vault, claim="DUP one two three!!", claim_type="opinion",
                        source_refs=["s"], date_str="2026-01-04", seq=2)
    wiki.create_wiki_page(vault, name="orphan page", page_type="concept", body="b",
                         claim_refs=[], date_str="2026-01-05")
    (vault / "10_Claims/pending/claim-20260106-001.md").write_text(
        schema.render_doc(
            {"type": "claim", "id": "claim-20260106-001", "claim_type": "technical_fact",
             "status": "unverified", "claim": "stale item", "speaker": "",
             "source_refs": ["s"], "evidence_refs": [], "review_after": "2026-01-01"},
            "## Claim\n\nstale\n"), encoding="utf-8")


def test_run_checks_catches_all(vault):
    _seed(vault)
    checks = {f["check"] for f in lint.run_checks(vault, "2026-06-07")}
    assert {"status_folder_mismatch", "missing_source_refs", "verified_without_evidence",
            "duplicate_claim", "orphan_wiki", "stale"} <= checks


def test_findings_sorted_by_severity(vault):
    _seed(vault)
    sev = [f["severity"] for f in lint.run_checks(vault, "2026-06-07")]
    order = {"error": 0, "warning": 1, "info": 2}
    assert sev == sorted(sev, key=lambda s: order[s])


def test_clean_vault_no_findings(vault):
    claims.create_claim(vault, claim="clean unique claim", claim_type="technical_fact",
                        source_refs=["s1"], date_str="2026-01-02", seq=1)
    assert lint.run_checks(vault, "2026-06-07") == []


def test_unparseable_file_is_reported_not_skipped(vault):
    (vault / "10_Claims/pending/claim-20260101-009.md").write_text(
        "---\nfoo: [unclosed\n---\n\nbody\n", encoding="utf-8")
    findings = lint.run_checks(vault, "2026-06-07")
    hits = [f for f in findings if f["check"] == "unparseable"]
    assert hits and hits[0]["severity"] == "error"
    assert "claim-20260101-009" in hits[0]["ref"]


def test_duplicate_id_across_folders_is_reported(vault):
    meta = {"type": "claim", "id": "claim-20260101-001", "claim_type": "technical_fact",
            "status": "unverified", "claim": "one two three", "speaker": "",
            "source_refs": ["s"], "evidence_refs": [], "sensitivity": "personal"}
    doc = schema.render_doc(meta, "## Claim\n\nx\n")
    (vault / "10_Claims/pending/claim-20260101-001.md").write_text(doc, encoding="utf-8")
    (vault / "10_Claims/verified/claim-20260101-001.md").write_text(doc, encoding="utf-8")
    findings = lint.run_checks(vault, "2026-06-07")
    assert any(f["check"] == "duplicate_id" and f["severity"] == "error"
               for f in findings)


def test_dangling_index_entry_is_reported(vault):
    index.update_index(vault, "claim-index", "claim-19990101-001", "ghost - unverified")
    findings = lint.run_checks(vault, "2026-06-07")
    hits = [f for f in findings if f["check"] == "index_dangling"]
    assert hits and hits[0]["ref"] == "claim-19990101-001"


def test_inbox_clip_without_frontmatter_is_visible(vault):
    (vault / "00_Inbox/raw/some-web-clip.md").write_text(
        "# Clipped page\n\nno frontmatter here\n", encoding="utf-8")
    findings = lint.run_checks(vault, "2026-06-07")
    assert any(f["check"] == "inbox_unstructured" and f["severity"] == "info"
               for f in findings)


def test_unclosed_fence_file_is_reported(vault):
    # 닫는 펜스가 없으면 parse_doc이 조용히 ({}, text)를 돌려준다: lint가 잡아야 한다
    (vault / "10_Claims/pending/claim-20260101-011.md").write_text(
        "---\ntype: claim\nid: claim-20260101-011\nno closing fence", encoding="utf-8")
    findings = lint.run_checks(vault, "2026-06-07")
    assert any(f["check"] == "unparseable" and "claim-20260101-011" in f["ref"]
               for f in findings)


def test_per_project_session_ids_are_not_duplicates(vault):
    from wiki_agents.core import projects
    projects.create_session_summary(vault, repo="/tmp/repo-a", title="a", body="b",
                                    date_str="2026-01-01", seq=1)
    projects.create_session_summary(vault, repo="/tmp/repo-b", title="b", body="b",
                                    date_str="2026-01-01", seq=1)
    findings = lint.run_checks(vault, "2026-06-07")
    assert not any(f["check"] == "duplicate_id" for f in findings)


def test_dangling_id_shaped_refs_are_reported(vault):
    claims.create_claim(vault, claim="refs a ghost source", claim_type="technical_fact",
                        source_refs=["source-19990101-001"], date_str="2026-01-01", seq=1)
    findings = lint.run_checks(vault, "2026-06-07")
    assert any(f["check"] == "dangling_ref" for f in findings)


def test_non_id_refs_are_not_flagged(vault):
    claims.create_claim(vault, claim="refs a url", claim_type="technical_fact",
                        source_refs=["https://example.com/post"], date_str="2026-01-01", seq=1)
    findings = lint.run_checks(vault, "2026-06-07")
    assert not any(f["check"] == "dangling_ref" for f in findings)


def test_inbox_clip_with_foreign_frontmatter_is_still_flagged(vault):
    # Obsidian Web Clipper는 자체 frontmatter(title 등)를 붙이지만 wiki 스키마(id)는 없다
    (vault / "00_Inbox/browser-clips/clipped.md").write_text(
        '---\ntitle: "Some page"\nsource: "https://x.com/a"\n---\n\nbody\n',
        encoding="utf-8")
    findings = lint.run_checks(vault, "2026-06-07")
    assert any(f["check"] == "inbox_unstructured" for f in findings)
