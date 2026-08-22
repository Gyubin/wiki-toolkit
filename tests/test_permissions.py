import pytest

from wiki_agents import permissions


@pytest.mark.asyncio
async def test_deny_unapproved_verified(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__promote_claim",
                     {"claim_id": "c", "target_status": "verified"}, None)
    assert res.behavior == "deny"


@pytest.mark.asyncio
async def test_model_cannot_spoof_human_approval(vault):
    # approved_by_human은 모델이 지어낼 수 있는 인자가 아니다: 입력에서 제거되고 거부된다
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__promote_claim",
                     {"claim_id": "c", "target_status": "verified",
                      "approved_by_human": True}, None)
    assert res.behavior == "deny"


@pytest.mark.asyncio
async def test_allow_verified_with_evidence(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__promote_claim",
                     {"claim_id": "c", "target_status": "verified",
                      "evidence_refs": ["repo:src/x.ts:12"]}, None)
    assert res.behavior == "allow"
    assert "approved_by_human" not in res.updated_input


@pytest.mark.asyncio
async def test_deny_set_claim_status_verified(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__set_claim_status",
                     {"claim_id": "c", "status": "verified"}, None)
    assert res.behavior == "deny"


@pytest.mark.asyncio
async def test_allow_set_claim_status_disputed(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__set_claim_status",
                     {"claim_id": "c", "status": "disputed"}, None)
    assert res.behavior == "allow"


@pytest.mark.asyncio
async def test_allow_work_source(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__create_source",
                     {"origin": "x", "content": "y", "sensitivity": "work"}, None)
    assert res.behavior == "allow"


@pytest.mark.asyncio
async def test_allow_other_tools(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("Read", {"file_path": "x"}, None)
    assert res.behavior == "allow"
