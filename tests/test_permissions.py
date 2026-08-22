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


@pytest.mark.asyncio
async def test_main_agent_raw_exec_denied(vault):
    # allowed_tools에서 뺀 것만으로는 부족하다: 콜백이 Allow를 돌려주면 그대로 실행된다
    gate = permissions.make_can_use_tool(vault)
    for tool in ("Bash", "Write", "Edit"):
        res = await gate(tool, {"command": "rm -rf /"}, None)
        assert res.behavior == "deny", tool


@pytest.mark.asyncio
async def test_subagent_bash_still_allowed(vault):
    # verify/wrap 서브에이전트는 Bash가 필요하다 (테스트 실행, 증거 수집)
    from types import SimpleNamespace
    gate = permissions.make_can_use_tool(vault)
    res = await gate("Bash", {"command": "pytest"},
                     SimpleNamespace(agent_id="verify-abc"))
    assert res.behavior == "allow"
