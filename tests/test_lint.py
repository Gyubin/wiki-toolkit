from wiki_agent.core import lint, claims, wiki
from wiki_agent import schema


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
