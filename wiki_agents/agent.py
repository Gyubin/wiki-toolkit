"""Assemble ClaudeAgentOptions and a thin multi-turn session wrapper."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ClaudeSDKClient,
    TextBlock,
)

from .permissions import GATED_TOOLS, make_can_use_tool
from .subagents import build_subagents, model_name
from .tools import WIKI_TOOL_NAMES, build_wiki_server

_SYSTEM = (Path(__file__).parent / "prompts" / "system.md").read_text(encoding="utf-8")


def build_options(vault: Path) -> ClaudeAgentOptions:
    vault = Path(vault)
    server = build_wiki_server(vault)
    # Bash/Write/Edit 없음: 구조화 쓰기는 mcp__wiki__* 도구 경로만 허용해 스키마와
    # 게이트를 우회하지 못하게 한다. GATED_TOOLS는 사전 승인에서 빼야 can_use_tool이 불린다.
    allowed = ["Read", "Grep", "Glob",
               *[t for t in WIKI_TOOL_NAMES if t not in GATED_TOOLS]]
    return ClaudeAgentOptions(
        system_prompt=_SYSTEM,
        model=model_name(),
        cwd=str(vault),
        permission_mode="acceptEdits",
        mcp_servers={"wiki": server},
        allowed_tools=allowed,
        agents=build_subagents(),
        can_use_tool=make_can_use_tool(vault),
    )


class WikiSession:
    """One long-running conversational session over the vault."""

    def __init__(self, vault: Path):
        self._client = ClaudeSDKClient(options=build_options(vault))
        self._connected = False

    async def __aenter__(self):
        await self._client.connect()
        self._connected = True
        return self

    async def __aexit__(self, *exc):
        await self._client.disconnect()

    async def ask(self, prompt: str):
        """Send a turn; yield assistant text chunks."""
        await self._client.query(prompt)
        async for msg in self._client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        yield block.text
