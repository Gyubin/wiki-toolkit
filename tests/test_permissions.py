import pytest
from wiki_agent import permissions


@pytest.mark.asyncio
async def test_deny_unapproved_verified(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__promote_claim",
                     {"claim_id": "c", "target_status": "verified"}, None)
    assert res.behavior == "deny"


@pytest.mark.asyncio
async def test_allow_approved_verified(vault):
    gate = permissions.make_can_use_tool(vault)
    res = await gate("mcp__wiki__promote_claim",
                     {"claim_id": "c", "target_status": "verified",
                      "approved_by_human": True}, None)
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
