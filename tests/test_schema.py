import pytest

from wiki_agents import schema


def test_enums_match_design():
    assert "technical_fact" in schema.CLAIM_TYPES
    assert "fact" not in schema.CLAIM_TYPES  # renamed in design
    assert "accepted_for_now" in schema.CLAIM_STATUSES
    assert "deprecated" in schema.CLAIM_STATUSES
    assert schema.SENSITIVITIES == ("personal", "work", "confidential")


def test_make_id():
    assert schema.make_id("claim", "2026-06-07", 1) == "claim-20260607-001"
    assert schema.make_id("source", "2026-06-07", 42) == "source-20260607-042"


def test_render_and_parse_roundtrip():
    meta = {"type": "claim", "id": "claim-20260607-001", "status": "unverified"}
    body = "## Claim\n\n어떤 주장이다.\n"
    text = schema.render_doc(meta, body)
    assert text.startswith("---\n")
    parsed_meta, parsed_body = schema.parse_doc(text)
    assert parsed_meta == meta
    assert parsed_body.strip() == body.strip()


def test_validate_rejects_unknown():
    with pytest.raises(ValueError):
        schema.validate_claim_type("nonsense")
    with pytest.raises(ValueError):
        schema.validate_status("nonsense")
