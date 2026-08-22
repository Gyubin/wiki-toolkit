"""Wrap pure core functions as in-process MCP @tools for the agent."""
from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import schema
from .core import claims, git, ids, learning, projects, search, sources, wiki

WIKI_TOOL_NAMES = [
    "mcp__wiki__create_source", "mcp__wiki__triage_record",
    "mcp__wiki__create_claim", "mcp__wiki__find_similar_claim",
    "mcp__wiki__promote_claim", "mcp__wiki__set_claim_status",
    "mcp__wiki__list_pending", "mcp__wiki__create_wiki_page",
    "mcp__wiki__create_learning_item", "mcp__wiki__list_due_reviews",
    "mcp__wiki__record_review",
    "mcp__wiki__collect_git_session",
    "mcp__wiki__create_session_summary",
    "mcp__wiki__create_decision",
    "mcp__wiki__search_wiki",
]


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def build_wiki_server(vault: Path):
    vault = Path(vault)

    @tool("create_source", "Capture a raw clip as a source in the Inbox",
          {"origin": str, "content": str, "sensitivity": str})
    async def create_source(args):
        p = sources.create_source(
            vault, origin=args["origin"], content=args["content"],
            sensitivity=args.get("sensitivity", "personal"),
            date_str=schema.today_str(),
            seq=ids.next_seq(vault, "source", schema.today_str(), ["00_Inbox"]),
            url=args.get("url"),
        )
        return _ok(f"created {p.stem}")

    @tool("triage_record", "Record a triage decision (drop|keep-as-link|deep)",
          {"source_id": str, "decision": str})
    async def triage_record(args):
        sources.triage_record(vault, args["source_id"], args["decision"], schema.today_str())
        return _ok("recorded")

    @tool("create_claim", "Create an atomic claim (always unverified)",
          {"claim": str, "claim_type": str})
    async def create_claim(args):
        p = claims.create_claim(
            vault, claim=args["claim"], claim_type=args["claim_type"],
            source_refs=args.get("source_refs", []), date_str=schema.today_str(),
            seq=ids.next_seq(vault, "claim", schema.today_str(), ["10_Claims"]),
            proposed_status=args.get("proposed_status"), speaker=args.get("speaker"),
        )
        return _ok(f"created {p.stem} (unverified)")

    @tool("find_similar_claim", "Find duplicate claims by normalized key",
          {"claim": str})
    async def find_similar_claim(args):
        hits = claims.find_similar_claim(vault, args["claim"], args.get("speaker"))
        return _ok(", ".join(hits) or "none")

    @tool("promote_claim", "Promote a claim's status (verified is gated)",
          {"claim_id": str, "target_status": str})
    async def promote_claim(args):
        p = claims.promote_claim(
            vault, args["claim_id"], target_status=args["target_status"],
            evidence_refs=args.get("evidence_refs"),
            approved_by_human=bool(args.get("approved_by_human", False)),
            date_str=schema.today_str(),
        )
        return _ok(f"promoted {p.stem} -> {args['target_status']}")

    @tool("set_claim_status", "Set a non-verified status (disputed/outdated/rejected)",
          {"claim_id": str, "status": str})
    async def set_claim_status(args):
        p = claims.set_claim_status(
            vault, args["claim_id"], status=args["status"],
            superseded_by=args.get("superseded_by"), date_str=schema.today_str(),
        )
        return _ok(f"set {p.stem} -> {args['status']}")

    @tool("list_pending", "List pending (unverified) claims", {})
    async def list_pending(args):
        rows = claims.list_pending(vault)
        return _ok("\n".join(f"{r['id']}: {r['claim'][:60]}" for r in rows) or "none")

    @tool("create_wiki_page", "Create a wiki page (concept/pattern/...)",
          {"name": str, "page_type": str, "body": str})
    async def create_wiki_page(args):
        p = wiki.create_wiki_page(
            vault, name=args["name"], page_type=args["page_type"], body=args["body"],
            claim_refs=args.get("claim_refs", []), date_str=schema.today_str(),
        )
        return _ok(f"created {p.name}")

    @tool("create_learning_item", "Create a learning item / flashcard",
          {"topic": str, "skill_area": str})
    async def create_learning_item(args):
        p = learning.create_learning_item(
            vault, topic=args["topic"], skill_area=args["skill_area"],
            date_str=schema.today_str(),
            seq=ids.next_seq(vault, "learning", schema.today_str(), ["30_Learning"]),
            wiki_refs=args.get("wiki_refs", []),
        )
        return _ok(f"created {p.stem}")

    @tool("list_due_reviews", "List learning items due for review today", {})
    async def list_due_reviews(args):
        rows = learning.list_due_reviews(vault, schema.today_str())
        return _ok("\n".join(f"{r['id']}: {r['topic']}" for r in rows) or "none")

    @tool("record_review", "Record a review result (passed true/false)",
          {"learning_id": str, "passed": bool})
    async def record_review(args):
        p = learning.record_review(
            vault, args["learning_id"], passed=bool(args["passed"]),
            today_str=schema.today_str(),
        )
        return _ok(f"recorded {p.stem}")

    @tool("collect_git_session",
          "Read a repo's diff/commits/changed files for base..head (read-only)",
          {"repo": str, "base": str, "head": str})
    async def collect_git_session(args):
        s = git.collect_session(args["repo"], args["base"], args.get("head", "HEAD"))
        text = (
            "commits:\n" + "\n".join(f"- {c['sha'][:8]} {c['subject']}" for c in s["commits"])
            + "\n\nchanged_files:\n" + "\n".join(s["changed_files"])
            + "\n\ndiff:\n" + s["diff"][:20000]
        )
        return _ok(text)

    @tool("create_session_summary",
          "Write a session summary under 01_Projects/<repo>/sessions (sensitivity=work)",
          {"repo": str, "title": str, "body": str})
    async def create_session_summary(args):
        slug = projects.project_slug(args["repo"])
        p = projects.create_session_summary(
            vault, repo=args["repo"], title=args["title"], body=args["body"],
            date_str=schema.today_str(),
            seq=ids.next_seq(vault, "session", schema.today_str(), [f"01_Projects/{slug}"]),
        )
        return _ok(f"created {p.stem}")

    @tool("create_decision",
          "Write an ADR under 01_Projects/<repo>/decisions (sensitivity=work)",
          {"repo": str, "title": str, "context": str, "decision": str,
           "alternatives": str, "consequences": str})
    async def create_decision(args):
        slug = projects.project_slug(args["repo"])
        p = projects.create_decision(
            vault, repo=args["repo"], title=args["title"], context=args["context"],
            decision=args["decision"], alternatives=args["alternatives"],
            consequences=args["consequences"], date_str=schema.today_str(),
            seq=ids.next_seq(vault, "decision", schema.today_str(), [f"01_Projects/{slug}"]),
        )
        return _ok(f"created {p.stem}")

    _index_cache = search.IndexCache(vault)

    @tool("search_wiki", "Hybrid semantic+lexical search over the vault",
          {"query": str})
    async def search_wiki(args):
        results = _index_cache.get().query(args["query"], int(args.get("k", 8)))
        text = "\n".join(f"- [{r['ref']}] {r['title']} (score {r['score']})"
                         for r in results) or "no results"
        return _ok(text)

    return create_sdk_mcp_server(
        name="wiki", version="0.1.0",
        tools=[create_source, triage_record, create_claim, find_similar_claim,
               promote_claim, set_claim_status, list_pending, create_wiki_page,
               create_learning_item, list_due_reviews, record_review,
               collect_git_session, create_session_summary, create_decision, search_wiki],
    )
