from wiki_toolkit import schema
from wiki_toolkit.core import claims, index, lint, sources, wiki


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
    from wiki_toolkit.core import projects
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


def test_thin_source_is_reported(vault):
    """봇월 문구 없이 껍데기만 내려온 캡처는 create_source가 못 막으므로 lint가 본다."""
    sources.create_source(vault, origin="browser", content="빈 껍데기",
                          date_str="2026-06-07", seq=1, url="https://example.com")
    checks = {f["check"] for f in lint.run_checks(vault, "2026-06-07")}
    assert "thin_source" in checks


def test_normal_length_source_is_not_reported(vault):
    sources.create_source(vault, origin="browser", content="가" * 300,
                          date_str="2026-06-07", seq=2, url="https://example.com")
    thin = [f for f in lint.run_checks(vault, "2026-06-07") if f["check"] == "thin_source"]
    assert thin == []


def test_malformed_inbox_clip_is_reported_not_crashed(vault):
    """제목에 콜론이 든 Web Clipper 클립 하나가 lint 전체를 죽이면 안 된다.

    thin_source 검사를 넣으면서 schema.parse_doc을 직접 부르고 OSError만 잡았더니
    yaml.ScannerError가 그대로 올라와 lint가 죽었다. 그것도 unparseable을 보고하는
    순회보다 먼저 돌아서 보고 대신 트레이스백이 나갔다. 파싱 경로는 _parse_full 하나다.
    """
    (vault / "00_Inbox/clip.md").write_text(
        "---\ntitle: Rust 1.0: what changed\nsource: https://x.com\n---\n\nclipped body\n",
        encoding="utf-8")
    checks = {f["check"] for f in lint.run_checks(vault, "2026-06-07")}
    assert "unparseable" in checks


def test_binary_inbox_file_does_not_crash_lint(vault):
    (vault / "00_Inbox/blob.md").write_bytes(b"\xff\xfe\x00\x00binary junk")
    checks = {f["check"] for f in lint.run_checks(vault, "2026-06-07")}
    assert "unparseable" in checks


def _seed_quote(vault, quote):
    """source 하나와 그 source를 인용하는 claim 하나."""
    sources.create_source(
        vault, origin="browser",
        content="앞부분입니다. " * 10 + "The harness owns the loop. " + "뒷부분입니다. " * 10,
        date_str="2026-08-27", seq=1, url="http://x")
    claims.create_claim(vault, claim="harness가 루프를 소유한다", claim_type="technical_fact",
                        source_refs=["source-20260827-001"], date_str="2026-08-27", seq=1,
                        quote=quote)


def test_quote_not_in_source_is_silent_when_verbatim(vault):
    _seed_quote(vault, "The harness owns the loop.")
    checks = {f["check"] for f in lint.run_checks(vault, "2026-08-27")}
    assert "quote_not_in_source" not in checks


def test_quote_not_in_source_flags_a_drifted_quote(vault):
    """원문에 없는 문자열이 인용문으로 들어가면 보고한다 (2026-08-27 실제 사고)."""
    _seed_quote(vault, "The harness owns the loops.")
    found = [f for f in lint.run_checks(vault, "2026-08-27")
             if f["check"] == "quote_not_in_source"]
    assert len(found) == 1
    assert found[0]["ref"] == "claim-20260827-001"
    assert found[0]["severity"] == "warning"


def test_quote_not_in_source_ignores_line_wrapping(vault):
    """줄바꿈 위치는 판정 대상이 아니다. 공백만 접어서 비교한다."""
    _seed_quote(vault, "The harness\nowns   the loop.")
    checks = {f["check"] for f in lint.run_checks(vault, "2026-08-27")}
    assert "quote_not_in_source" not in checks


def test_quote_not_in_source_allows_elision_marker(vault):
    _seed_quote(vault, "앞부분입니다. (...) The harness owns the loop.")
    checks = {f["check"] for f in lint.run_checks(vault, "2026-08-27")}
    assert "quote_not_in_source" not in checks


def test_quote_not_in_source_skips_claims_whose_source_is_absent(vault):
    """source가 vault에 없으면 판정하지 않는다 (dangling_ref가 이미 보고한다)."""
    claims.create_claim(vault, claim="주장", claim_type="opinion",
                        source_refs=["source-20990101-001"], date_str="2026-08-27", seq=1,
                        quote="아무 원문")
    checks = {f["check"] for f in lint.run_checks(vault, "2026-08-27")}
    assert "quote_not_in_source" not in checks


def test_quote_not_in_source_skips_claims_without_a_quote(vault):
    sources.create_source(vault, origin="browser", content="본문" * 200,
                          date_str="2026-08-27", seq=1)
    claims.create_claim(vault, claim="인용 없는 주장", claim_type="opinion",
                        source_refs=["source-20260827-001"], date_str="2026-08-27", seq=1)
    checks = {f["check"] for f in lint.run_checks(vault, "2026-08-27")}
    assert "quote_not_in_source" not in checks


def test_verified_with_blank_evidence_is_flagged(vault):
    """[""]는 근거가 아니다. 게이트가 뚫렸을 때 안전망까지 같이 침묵하면 안 된다."""
    p = vault / "10_Claims/verified/claim-20260828-001.md"
    p.write_text(
        schema.render_doc(
            {"type": "claim", "id": "claim-20260828-001", "claim_type": "technical_fact",
             "status": "verified", "claim": "구멍", "speaker": "",
             "source_refs": ["source-20260828-001"], "evidence_refs": [""],
             "sensitivity": "personal"},
            "## Claim\n\n구멍\n"), encoding="utf-8")
    checks = [f["check"] for f in lint.run_checks(vault, "2026-08-28")
              if f["ref"] == "claim-20260828-001"]
    assert "verified_without_evidence" in checks


def test_ingested_leftover_clip_is_classified_separately(vault):
    """ingest 끝난 클립 원본은 "needs ingest"가 아니라 삭제 대기로 보고한다."""
    (vault / "00_Inbox/browser-clips/clip.md").write_text(
        "---\ntitle: 글\nurl: http://example.com/a\n---\n\n본문\n", encoding="utf-8")
    sources.create_source(vault, origin="browser", content="본문 " * 200,
                          date_str="2026-08-28", seq=1, url="http://example.com/a")
    rows = [f for f in lint.run_checks(vault, "2026-08-28")
            if f["ref"].endswith("clip.md")]
    checks = {f["check"] for f in rows}
    assert "inbox_ingested_leftover" in checks
    assert "inbox_unstructured" not in checks
