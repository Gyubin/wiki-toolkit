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
