"""Subagent definitions; prompts loaded from prompts/."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import AgentDefinition

from .tools import WIKI_TOOL_NAMES

_PROMPTS = Path(__file__).parent / "prompts"


def _p(name: str) -> str:
    return (_PROMPTS / f"{name}.md").read_text(encoding="utf-8")


def build_subagents() -> dict[str, AgentDefinition]:
    w = WIKI_TOOL_NAMES
    return {
        "ingest": AgentDefinition(
            description="Ingest a raw clip into triaged, unverified claims.",
            prompt=_p("ingest"),
            tools=["Read", "Grep"] + [t for t in w if any(
                k in t for k in ("create_source", "triage_record", "create_claim", "find_similar_claim"))],
            model="claude-opus-4-8",
        ),
        "verify": AgentDefinition(
            description="Verify pending claims with evidence; promote or block.",
            prompt=_p("verify"),
            tools=["Read", "Grep", "Glob", "Bash"] + [t for t in w if any(
                k in t for k in ("promote_claim", "set_claim_status", "create_wiki_page", "list_pending"))],
            model="claude-opus-4-8",
        ),
        "answer": AgentDefinition(
            description="Answer from the wiki with epistemic status; feed insights back as unverified.",
            prompt=_p("answer"),
            tools=["Read", "Grep", "Glob", "mcp__wiki__create_claim"],
            disallowedTools=["Write", "Edit"],
            model="claude-opus-4-8",
        ),
        "learning": AgentDefinition(
            description="Build learning material and drive spaced review.",
            prompt=_p("learning"),
            tools=["Read", "Grep"] + [t for t in w if any(
                k in t for k in ("create_learning_item", "list_due_reviews", "record_review"))],
            model="claude-opus-4-8",
        ),
        "wrap": AgentDefinition(
            description="Wrap a coding session into session summary, ADRs, concepts, and learning.",
            prompt=_p("wrap"),
            tools=["Read", "Grep", "Glob", "Bash"] + [t for t in w if any(
                k in t for k in ("collect_git_session", "create_session_summary",
                                 "create_decision", "create_wiki_page", "create_claim",
                                 "create_learning_item"))],
            model="claude-opus-4-8",
        ),
        "lint": AgentDefinition(
            description="Read-only audit: find contradictions among claims and report them.",
            prompt=_p("lint"),
            tools=["Read", "Grep", "Glob"],
            disallowedTools=["Write", "Edit", "Bash"],
            model="claude-opus-4-8",
        ),
    }
