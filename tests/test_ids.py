from wiki_agents.core import claims, ids


def test_next_seq_empty_vault(vault):
    assert ids.next_seq(vault, "claim", "2026-08-22", ["10_Claims"]) == 1


def test_next_seq_survives_promotion(vault):
    claims.create_claim(
        vault, claim="a", claim_type="technical_fact", source_refs=[],
        date_str="2026-08-22", seq=1,
    )
    claims.promote_claim(
        vault, "claim-20260822-001", target_status="verified",
        evidence_refs=["repo:src/x.ts:12"], date_str="2026-08-22",
    )
    # 승격으로 pending이 비어도 시퀀스는 재사용되면 안 된다
    assert ids.next_seq(vault, "claim", "2026-08-22", ["10_Claims"]) == 2


def test_next_seq_survives_deletion(vault):
    for seq in (1, 2):
        claims.create_claim(
            vault, claim=f"c{seq}", claim_type="technical_fact", source_refs=[],
            date_str="2026-08-22", seq=seq,
        )
    (vault / "10_Claims/pending/claim-20260822-001.md").unlink()
    assert ids.next_seq(vault, "claim", "2026-08-22", ["10_Claims"]) == 3


def test_next_seq_scoped_to_date_and_prefix(vault):
    claims.create_claim(
        vault, claim="yesterday", claim_type="technical_fact", source_refs=[],
        date_str="2026-08-21", seq=7,
    )
    assert ids.next_seq(vault, "claim", "2026-08-22", ["10_Claims"]) == 1
    assert ids.next_seq(vault, "source", "2026-08-21", ["00_Inbox"]) == 1


def test_next_seq_reads_ids_from_frontmatter_when_filenames_are_titles(vault):
    """source 파일명을 사람이 읽을 제목으로 바꿔도 번호가 리셋되면 안 된다.

    파일명으로만 세면 이름을 바꾼 순간 next_seq가 1을 돌려주고, 다음 create_source가
    이미 있는 id를 다시 발급한다. 2026-08-28에 실제로 재현했다 (004까지 있는데 1이 나왔다).
    id의 단일 출처는 frontmatter다 (AGENTS.md §2).
    """
    from wiki_agents.core import sources
    for seq in (1, 2):
        sources.create_source(vault, origin="browser", content="본문" * 200,
                              date_str="2026-08-27", seq=seq)
    raw = vault / "00_Inbox/raw"
    (raw / "source-20260827-001.md").rename(raw / "Expert Parallel Deployment 이해하기.md")
    (raw / "source-20260827-002.md").rename(raw / "Quantization for LLM Inference.md")
    assert ids.next_seq(vault, "source", "2026-08-27", ["00_Inbox"]) == 3


def test_next_seq_still_reads_id_shaped_filenames(vault):
    """claim은 파일명이 곧 id다. frontmatter를 안 읽어도 세져야 한다."""
    (vault / "10_Claims/pending/claim-20260827-007.md").write_text("본문만 있고 frontmatter 없음",
                                                                   encoding="utf-8")
    assert ids.next_seq(vault, "claim", "2026-08-27", ["10_Claims"]) == 8
