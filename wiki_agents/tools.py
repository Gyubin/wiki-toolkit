"""Wrap pure core functions as in-process MCP @tools for the agent."""
from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import schema
from .core import claims, git, ids, learning, projects, search, sources, wiki

WIKI_TOOL_NAMES = [
    "mcp__wiki__create_source", "mcp__wiki__triage_record",
    "mcp__wiki__create_claim", "mcp__wiki__find_similar_claim",
    "mcp__wiki__promote_claim", "mcp__wiki__set_claim_status",
    "mcp__wiki__list_pending", "mcp__wiki__create_wiki_page",
    "mcp__wiki__update_wiki_page",
    "mcp__wiki__create_learning_item", "mcp__wiki__list_due_reviews",
    "mcp__wiki__record_review",
    "mcp__wiki__collect_git_session",
    "mcp__wiki__create_session_summary",
    "mcp__wiki__create_decision",
    "mcp__wiki__search_wiki",
]


def _ok(text: str) -> dict:
    return {"content": [{"type": "text", "text": text}]}


def _schema(required: dict, optional: dict | None = None) -> dict:
    """선택 인자가 있는 도구용 완전한 JSON 스키마.

    dict 축약형({이름: 타입})은 SDK가 모든 키를 required로 만들어 선택 인자를
    모델에게 광고하지 못한다. evidence_refs, source_refs가 그렇게 묻혀 있었다.
    """
    props = dict(required)
    props.update(optional or {})
    return {"type": "object", "properties": props, "required": list(required)}


_STR = {"type": "string"}
_INT = {"type": "integer"}
_STR_LIST = {"type": "array", "items": {"type": "string"}}


def resolve_wiki_page_path(vault: Path, rel: str) -> Path:
    """update_wiki_page 대상은 03_Resources 하위로만 한정한다.

    vault 전체를 열어두면 클레임 파일의 status를 게이트 없이 바꾸는 우회로가 된다.
    """
    root = (Path(vault) / "03_Resources").resolve()
    p = (Path(vault) / rel).resolve()
    if not p.is_relative_to(root):
        raise ValueError("update_wiki_page can only touch pages under 03_Resources")
    return p


def build_wiki_server(vault: Path):
    vault = Path(vault)

    def _done(text: str, paths: list[str]) -> dict:
        # 쓰기 도구 공통: 감사 추적용 vault 자동 커밋 (git repo 아니면 무동작).
        # paths로 스테이징을 한정해 사용자의 무관한 수동 편집을 쓸어 담지 않는다.
        git.commit_vault(vault, f"wiki: {text}", paths=[*paths, "06_Metadata"])
        return _ok(text)

    @tool("create_source", "Capture a raw clip as a source in the Inbox",
          _schema({"origin": _STR, "content": _STR},
                  {"sensitivity": _STR, "url": _STR}))
    async def create_source(args):
        p = sources.create_source(
            vault, origin=args["origin"], content=args["content"],
            sensitivity=args.get("sensitivity", "personal"),
            date_str=schema.today_str(),
            seq=ids.next_seq(vault, "source", schema.today_str(), ["00_Inbox"]),
            url=args.get("url"),
        )
        return _done(f"created {p.stem}", ["00_Inbox"])

    @tool("triage_record", "Record a triage decision (drop|keep-as-link|deep)",
          {"source_id": str, "decision": str})
    async def triage_record(args):
        sources.triage_record(vault, args["source_id"], args["decision"], schema.today_str())
        return _done("recorded", [])

    @tool("create_claim", "Create an atomic claim (always unverified). "
          "Always pass source_refs so the claim stays source-linked.",
          _schema({"claim": _STR, "claim_type": _STR},
                  {"source_refs": _STR_LIST, "proposed_status": _STR, "speaker": _STR}))
    async def create_claim(args):
        p = claims.create_claim(
            vault, claim=args["claim"], claim_type=args["claim_type"],
            source_refs=args.get("source_refs", []), date_str=schema.today_str(),
            seq=ids.next_seq(vault, "claim", schema.today_str(), ["10_Claims"]),
            proposed_status=args.get("proposed_status"), speaker=args.get("speaker"),
        )
        return _done(f"created {p.stem} (unverified)", ["10_Claims"])

    @tool("find_similar_claim", "Find duplicate claims by normalized key",
          _schema({"claim": _STR}, {"speaker": _STR}))
    async def find_similar_claim(args):
        hits = claims.find_similar_claim(vault, args["claim"], args.get("speaker"))
        return _ok(", ".join(hits) or "none")

    @tool("promote_claim", "Promote a claim's status. verified requires evidence_refs; "
          "human approval exists only in the web Verify tab, never as a tool argument.",
          _schema({"claim_id": _STR, "target_status": _STR},
                  {"evidence_refs": _STR_LIST}))
    async def promote_claim(args):
        # approved_by_human은 의도적으로 전달하지 않는다: 에이전트 경로의 verified는
        # evidence_refs가 유일한 통로다 (사람 승인은 app.py의 /approve 라우트).
        p = claims.promote_claim(
            vault, args["claim_id"], target_status=args["target_status"],
            evidence_refs=args.get("evidence_refs"),
            date_str=schema.today_str(),
        )
        return _done(f"promoted {p.stem} -> {args['target_status']}", ["10_Claims"])

    @tool("set_claim_status", "Set a non-verified status (disputed/outdated/rejected)",
          _schema({"claim_id": _STR, "status": _STR}, {"superseded_by": _STR}))
    async def set_claim_status(args):
        p = claims.set_claim_status(
            vault, args["claim_id"], status=args["status"],
            superseded_by=args.get("superseded_by"), date_str=schema.today_str(),
        )
        return _done(f"set {p.stem} -> {args['status']}", ["10_Claims"])

    @tool("list_pending", "List pending (unverified) claims", {})
    async def list_pending(args):
        rows = claims.list_pending(vault)
        return _ok("\n".join(f"{r['id']}: {r['claim'][:60]}" for r in rows) or "none")

    @tool("create_wiki_page", "Create a wiki page (concept/pattern/...). "
          "Fails if the page exists; then use update_wiki_page instead.",
          _schema({"name": _STR, "page_type": _STR, "body": _STR},
                  {"claim_refs": _STR_LIST, "domain": _STR_LIST}))
    async def create_wiki_page(args):
        p = wiki.create_wiki_page(
            vault, name=args["name"], page_type=args["page_type"], body=args["body"],
            claim_refs=args.get("claim_refs", []), date_str=schema.today_str(),
            domain=args.get("domain"),
        )
        return _done(f"created {p.name}", ["03_Resources"])

    @tool("update_wiki_page", "Update an existing wiki page (body, claim_refs, status)",
          _schema({"path": _STR},
                  {"body": _STR, "add_claim_refs": _STR_LIST, "status": _STR}))
    async def update_wiki_page(args):
        p = resolve_wiki_page_path(vault, args["path"])
        wiki.update_wiki_page(
            p, body=args.get("body"),
            add_claim_refs=args.get("add_claim_refs"), status=args.get("status"),
        )
        return _done(f"updated {p.name}", ["03_Resources"])

    @tool("create_learning_item", "Create a learning item / flashcard",
          _schema({"topic": _STR, "skill_area": _STR},
                  {"wiki_refs": _STR_LIST, "source_refs": _STR_LIST}))
    async def create_learning_item(args):
        p = learning.create_learning_item(
            vault, topic=args["topic"], skill_area=args["skill_area"],
            date_str=schema.today_str(),
            seq=ids.next_seq(vault, "learning", schema.today_str(), ["30_Learning"]),
            wiki_refs=args.get("wiki_refs", []), source_refs=args.get("source_refs", []),
        )
        return _done(f"created {p.stem}", ["30_Learning"])

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
        return _done(f"recorded {p.stem}", ["30_Learning"])

    @tool("collect_git_session",
          "Read a repo's diff/commits/changed files for base..head (read-only)",
          _schema({"repo": _STR, "base": _STR}, {"head": _STR}))
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
        return _done(f"created {p.stem}", ["01_Projects"])

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
        return _done(f"created {p.stem}", ["01_Projects"])

    _index_cache = search.IndexCache(vault)

    @tool("search_wiki", "Hybrid semantic+lexical search over the vault",
          _schema({"query": _STR}, {"k": _INT}))
    async def search_wiki(args):
        results = await asyncio.to_thread(
            lambda: _index_cache.get().query(args["query"], int(args.get("k", 8))))
        text = "\n".join(f"- [{r['ref']}] {r['title']} (score {r['score']})"
                         for r in results) or "no results"
        return _ok(text)

    return create_sdk_mcp_server(
        name="wiki", version="0.1.0",
        tools=[create_source, triage_record, create_claim, find_similar_claim,
               promote_claim, set_claim_status, list_pending, create_wiki_page,
               update_wiki_page, create_learning_item, list_due_reviews, record_review,
               collect_git_session, create_session_summary, create_decision, search_wiki],
    )
