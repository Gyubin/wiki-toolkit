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

# 메인 에이전트가 스키마/게이트를 우회해 vault를 직접 고치는 경로.
# allowed_tools에서 빼는 것만으로는 부족하다: 사전 승인이 안 된 도구는 이 콜백으로
# 오는데 기본이 Allow면 그대로 실행된다. 서브에이전트(agent_id 있음)는 verify/wrap의
# Bash처럼 필요해서 허용하고, 각자의 AgentDefinition.tools로 범위가 잡힌다.
RAW_MUTATION_TOOLS = ("Bash", "Write", "Edit", "NotebookEdit")


def make_can_use_tool(vault: Path):
    async def can_use_tool(tool_name: str, input_data: dict, context):
        if tool_name in RAW_MUTATION_TOOLS and getattr(context, "agent_id", None) is None:
            return PermissionResultDeny(
                message="main agent must go through mcp__wiki__* tools; "
                        "raw exec/write bypasses schema, IDs, and the verified gate"
            )
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
