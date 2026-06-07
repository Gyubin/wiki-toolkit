"""can_use_tool gate: verified promotion + sensitivity (mirrors core invariants)."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import PermissionResultAllow, PermissionResultDeny


def make_can_use_tool(vault: Path):
    async def can_use_tool(tool_name: str, input_data: dict, context):
        if tool_name == "mcp__wiki__promote_claim":
            if input_data.get("target_status") == "verified":
                if not input_data.get("approved_by_human") and not input_data.get("evidence_refs"):
                    return PermissionResultDeny(
                        message="verified requires human approval or evidence (principle 9)"
                    )
        return PermissionResultAllow(updated_input=input_data)

    return can_use_tool
