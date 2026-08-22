"""can_use_tool gate: verified promotion (mirrors core invariants).

이 콜백은 allowed_tools로 사전 승인되지 않은 도구에만 호출된다 (SDK 0.2.x 동작).
그래서 GATED_TOOLS는 agent.py의 allowed_tools에서 반드시 빠져 있어야 게이트가 산다.
사람 승인(approved_by_human)은 웹 UI의 /claims/{id}/approve 경로에만 존재한다.
모델이 인자로 넘긴 approved_by_human은 스푸핑이므로 입력에서 제거한다.
"""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny

GATED_TOOLS = ("mcp__wiki__promote_claim", "mcp__wiki__set_claim_status")


def make_can_use_tool(vault: Path):
    async def can_use_tool(tool_name: str, input_data: dict, context):
        if tool_name not in GATED_TOOLS:
            return PermissionResultAllow(updated_input=input_data)
        data = {k: v for k, v in input_data.items() if k != "approved_by_human"}
        target = data.get("target_status") or data.get("status")
        if target == "verified":
            if tool_name == "mcp__wiki__set_claim_status":
                return PermissionResultDeny(
                    message="verified must go through promote_claim (principle 9)"
                )
            if not data.get("evidence_refs"):
                return PermissionResultDeny(
                    message="verified requires evidence_refs; human approval happens "
                            "in the web Verify tab, not via this tool (principle 9)"
                )
        return PermissionResultAllow(updated_input=data)

    return can_use_tool
