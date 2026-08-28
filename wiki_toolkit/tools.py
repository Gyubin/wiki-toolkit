"""Wrap pure core functions as in-process MCP @tools for the agent."""
from __future__ import annotations

import asyncio
from pathlib import Path

from claude_agent_sdk import create_sdk_mcp_server, tool

from . import schema
from .core import claims, git, ids, learning, pipeline, projects, search, sources, wiki

WIKI_TOOL_NAMES = [
    "mcp__wiki__create_source", "mcp__wiki__triage_record",
    "mcp__wiki__update_source_raw", "mcp__wiki__update_claim_quote", "mcp__wiki__update_claim_text",
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
    "mcp__wiki__vault_next_step",
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


def resolve_content(args: dict) -> str:
    """`content` 또는 `content_path` 중 정확히 하나를 받아 본문 문자열을 돌려준다.

    긴 클립을 `content`로 넘기려면 모델이 원문을 도구 인자로 다시 타이핑해야 하고,
    거기서 조용히 뒤틀린다. 2026-08-27에 119KB짜리 클립 4개를 그렇게 넣다가 곱슬따옴표
    18개를 곧은 따옴표로 바꿔 적었고 한 곳은 단어를 바꿨다. 파일에서 읽으면 그 단계가
    아예 없어진다.

    둘 다 주거나 둘 다 안 주면 거부한다. 조용히 하나를 고르면 어느 쪽이 쓰였는지
    나중에 알 수 없다.
    """
    text, path = args.get("content"), args.get("content_path")
    if (text is None) == (path is None):
        raise ValueError("pass exactly one of content or content_path")
    if path is not None:
        p = Path(path).expanduser()
        if not p.is_file():
            raise FileNotFoundError(f"content_path is not a file: {p}")
        return p.read_text(encoding="utf-8")
    return text


def resolve_optional_body(args: dict) -> str | None:
    """`body` 또는 `body_path` 중 최대 하나. 둘 다 없으면 None (본문은 그대로 둔다)."""
    text, path = args.get("body"), args.get("body_path")
    if text is not None and path is not None:
        raise ValueError("pass at most one of body or body_path")
    if path is None:
        return text
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"body_path is not a file: {p}")
    return p.read_text(encoding="utf-8")


def resolve_wiki_page_path(vault: Path, rel: str) -> Path:
    """update_wiki_page 대상은 03_Resources 하위로만 한정한다.

    vault 전체를 열어두면 클레임 파일의 status를 게이트 없이 바꾸는 우회로가 된다.
    """
    root = (Path(vault) / "03_Resources").resolve()
    p = (Path(vault) / rel).resolve()
    if not p.is_relative_to(root):
        raise ValueError("update_wiki_page can only touch pages under 03_Resources")
    return p


def build_wiki_tools(vault: Path) -> list:
    """vault에 묶인 @tool 객체 목록. 테스트가 핸들러를 직접 부를 수 있게 분리했다."""
    vault = Path(vault)

    def _with_next_step(text: str) -> str:
        """결과 뒤에 "다음에 할 일"을 붙인다.

        사람이 파이프라인 단계를 외우지 않아도 되게 하는 장치. 프롬프트가 아니라 도구
        반환값에 두어 Claude Code든 CLI든 어디로 들어와도 똑같이 나온다.
        """
        try:
            hint = pipeline.next_step(vault, schema.today_str())
        except Exception:  # noqa: BLE001
            # vault 상태 계산 실패가 쓰기 성공을 가리면 안 된다. OSError만 잡았더니
            # 깨진 학습카드 하나가 yaml 예외를 올려서, 파일은 이미 만들어졌는데 도구는
            # 실패로 보였다. 모델은 실패로 알고 다시 써서 중복 claim을 만든다.
            # 힌트는 부가 정보다. 무슨 이유로든 못 만들면 조용히 생략한다.
            return text
        return f"{text}\n{hint}" if hint else text

    def _done(text: str, paths: list[str]) -> dict:
        # 쓰기 도구 공통: 감사 추적용 vault 자동 커밋 (git repo 아니면 무동작).
        # paths로 스테이징을 한정해 사용자의 무관한 수동 편집을 쓸어 담지 않는다.
        committed = git.commit_vault(vault, f"wiki: {text}", paths=[*paths, "06_Metadata"])
        out = _with_next_step(text)
        if not committed and (vault / ".git").exists():
            # 커밋 실패를 조용히 삼키면 감사 추적이 끊긴 채 쓰기가 쌓이고, 나중에 다른
            # 커밋이 엉뚱한 메시지로 쓸어 담는다. 쓰기는 비차단, 실패는 보이게.
            out += "\n(경고: vault 자동 커밋이 실패했다. vault의 git 상태를 확인해라)"
        return _ok(out)

    @tool("create_source",
          "Capture a raw clip as a source in the Inbox. Pass content_path (a file) "
          "instead of content for anything long: retyping a clip into the argument is "
          "where verbatim capture silently drifts. Pass title with a short human-readable "
          "name: it becomes the filename, which is what Obsidian shows in the graph and "
          "the file explorer. The id still lives in frontmatter.",
          _schema({"origin": _STR},
                  {"content": _STR, "content_path": _STR, "sensitivity": _STR,
                   "url": _STR, "title": _STR}))
    async def create_source(args):
        today = schema.today_str()
        seq = ids.next_seq(vault, "source", today, ["00_Inbox"])
        sid = schema.make_id("source", today, seq)
        p = sources.create_source(
            vault, origin=args["origin"], content=resolve_content(args),
            sensitivity=args.get("sensitivity", "personal"),
            title=args.get("title"),
            date_str=today, seq=seq,
            url=args.get("url"),
        )
        # id를 반환에 넣는다. 파일명(사람이 읽는 제목)만 돌려주면 다음 호출 전부
        # (triage_record, create_claim의 source_refs, 검토표)가 요구하는 id를 grep으로
        # 되찾아야 한다. 병렬 ingest에서 기억으로 짝지으면 claim이 엉뚱한 source에 붙는다.
        name = f" ({p.stem})" if p.stem != sid else ""
        return _done(f"created {sid}{name}", ["00_Inbox"])

    @tool("triage_record", "Record a triage decision (drop|keep-as-link|deep) "
          "for an existing source id",
          {"source_id": str, "decision": str})
    async def triage_record(args):
        sources.triage_record(vault, args["source_id"], args["decision"], schema.today_str())
        return _done(f"recorded triage {args['source_id']} -> {args['decision']}", [])

    @tool("update_source_raw",
          "Rewrite a source's ## Raw body; frontmatter is untouched. Requires a reason. "
          "Use content_path to restore from the original capture without retyping it.",
          _schema({"source_id": _STR, "reason": _STR},
                  {"content": _STR, "content_path": _STR}))
    async def update_source_raw(args):
        p = sources.update_source_raw(
            vault, args["source_id"], content=resolve_content(args), reason=args["reason"])
        return _done(f"updated {p.stem} raw body", ["00_Inbox"])

    @tool("update_claim_quote",
          "Replace a claim's ## 원문 block so it matches the source verbatim. "
          "Never touches the claim text, its status, or which folder it lives in. "
          "Requires a reason.",
          _schema({"claim_id": _STR, "quote": _STR, "reason": _STR}))
    async def update_claim_quote(args):
        p = claims.update_claim_quote(
            vault, args["claim_id"], quote=args["quote"], reason=args["reason"],
            date_str=schema.today_str())
        return _done(f"updated {p.stem} quote", ["10_Claims"])

    @tool("update_claim_text",
          "Rewrite an unverified claim's assertion when it overstates its source (a dropped "
          "hedge like can/usually/may, or a single benchmark written as a general fact). "
          "Never touches the quote, the status, the folder, or source_refs. Requires a "
          "reason. Refuses once a status has been assigned: that judgement was about the "
          "old sentence.",
          _schema({"claim_id": _STR, "claim": _STR, "reason": _STR}))
    async def update_claim_text(args):
        p = claims.update_claim_text(
            vault, args["claim_id"], claim=args["claim"], reason=args["reason"],
            date_str=schema.today_str())
        return _done(f"updated {p.stem} claim text", ["10_Claims"])

    @tool("create_claim", "Create an atomic claim (always unverified). "
          "Always pass source_refs so the claim stays source-linked, and quote with the "
          "source passage this claim came from, copied verbatim (do not summarize or "
          "translate it) so the claim can be checked without reopening the source. "
          "Sensitivity is inherited from the most sensitive referenced source unless "
          "passed explicitly.",
          _schema({"claim": _STR, "claim_type": _STR},
                  {"source_refs": _STR_LIST, "proposed_status": _STR, "speaker": _STR,
                   "quote": _STR, "sensitivity": _STR}))
    async def create_claim(args):
        refs = args.get("source_refs", [])
        # claim은 원문 인용을 담으므로 source의 민감도를 상속해야 한다. 안 그러면
        # confidential source의 인용문이 personal claim에 실려 임베딩 API로 나간다.
        sens = args.get("sensitivity") or sources.max_sensitivity(vault, refs)
        p = claims.create_claim(
            vault, claim=args["claim"], claim_type=args["claim_type"],
            source_refs=refs, date_str=schema.today_str(),
            seq=ids.next_seq(vault, "claim", schema.today_str(), ["10_Claims"]),
            proposed_status=args.get("proposed_status"), speaker=args.get("speaker"),
            quote=args.get("quote"), sensitivity=sens,
        )
        tag = " (unverified)" if sens == "personal" else f" (unverified, {sens})"
        return _done(f"created {p.stem}{tag}", ["10_Claims"])

    @tool("find_similar_claim", "Find duplicate claims by normalized key",
          _schema({"claim": _STR}, {"speaker": _STR}))
    async def find_similar_claim(args):
        hits = claims.find_similar_claim(vault, args["claim"], args.get("speaker"))
        return _ok(", ".join(hits) or "none")

    @tool("promote_claim", "Promote a claim's status. verified requires evidence_refs. "
          "사람 판단으로 올릴 때는 그 판단을 evidence_refs에 문장으로 적는다.",
          _schema({"claim_id": _STR, "target_status": _STR},
                  {"evidence_refs": _STR_LIST}))
    async def promote_claim(args):
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
        return _ok(_with_next_step(
            "\n".join(f"{r['id']}: {r['claim'][:60]}" for r in rows) or "none"))

    @tool("create_wiki_page", "Create a wiki page (concept/pattern/...). "
          "Pass aliases for the page's other names (e.g. the English original of a "
          "Korean title) so search and Obsidian's quick switcher find both. "
          "Fails if the page exists; then use update_wiki_page instead.",
          _schema({"name": _STR, "page_type": _STR, "body": _STR},
                  {"claim_refs": _STR_LIST, "domain": _STR_LIST, "aliases": _STR_LIST}))
    async def create_wiki_page(args):
        p = wiki.create_wiki_page(
            vault, name=args["name"], page_type=args["page_type"], body=args["body"],
            claim_refs=args.get("claim_refs", []), date_str=schema.today_str(),
            domain=args.get("domain"), aliases=args.get("aliases"),
        )
        return _done(f"created {p.name}", ["03_Resources"])

    @tool("update_wiki_page",
          "Update an existing wiki page (body, claim_refs, status, aliases). aliases "
          "replaces the whole list, so pass every alias the page should keep. Pass "
          "body_path instead of body to take the new body from a file: retyping a long "
          "page to change one line is how wording silently drifts.",
          _schema({"path": _STR},
                  {"body": _STR, "body_path": _STR, "add_claim_refs": _STR_LIST,
                   "status": _STR, "aliases": _STR_LIST}))
    async def update_wiki_page(args):
        p = resolve_wiki_page_path(vault, args["path"])
        wiki.update_wiki_page(
            p, body=resolve_optional_body(args),
            add_claim_refs=args.get("add_claim_refs"), status=args.get("status"),
            aliases=args.get("aliases"), date_str=schema.today_str(),
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
        diff = s["diff"]
        shown = diff[:20000]
        if len(diff) > 20000:
            # 절단을 표시 없이 하면 요약과 ADR이 뒷부분 파일들의 변경을 조용히 누락한다
            shown += (f"\n[diff truncated: showing 20000 of {len(diff)} chars; "
                      f"changed_files above is complete]")
        text = (
            "commits:\n" + "\n".join(f"- {c['sha'][:8]} {c['subject']}" for c in s["commits"])
            + "\n\nchanged_files:\n" + "\n".join(s["changed_files"])
            + "\n\ndiff:\n" + shown
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

    @tool("vault_next_step",
          "파이프라인에서 지금 사람이 해야 할 다음 한 가지와 각 단계의 대기 개수", {})
    async def vault_next_step(args):
        s = pipeline.vault_state(vault, schema.today_str())
        hint = pipeline.next_step(vault, schema.today_str()) or "대기 중인 단계 없음"
        return _ok("\n".join([
            hint, "",
            f"ingest 대기 클립: {len(s['unstructured_inbox'])}",
            f"ingest 끝나 삭제만 남은 클립 원본: {len(s['ingested_leftovers'])}",
            f"아직 검토 안 한 claim: {len(s['unverified_claims'])}",
            f"verified claim: {len(s['verified_claims'])}",
            f"검토는 끝났는데 wiki page에 안 실린 claim: {len(s['citable_unlinked'])}",
            f"wiki page: {len(s['wiki_pages'])}",
            f"학습카드: {len(s['learning_items'])} (오늘 복습 도래: {len(s['due_reviews'])})",
        ]))

    @tool("search_wiki", "Hybrid semantic+lexical search over the vault",
          _schema({"query": _STR}, {"k": _INT}))
    async def search_wiki(args):
        def _q():
            idx = _index_cache.get()
            return idx, idx.query(args["query"], int(args.get("k", 8)))

        idx, results = await asyncio.to_thread(_q)
        text = "\n".join(f"- [{r['ref']}] {r['title']} (score {r['score']})"
                         for r in results) or "no results"
        if getattr(idx, "degraded", False) or getattr(idx, "query_degraded", False):
            text += "\n(경고: 임베딩을 쓸 수 없어 BM25 결과만이다. 키/네트워크를 확인해라)"
        return _ok(text)

    return [create_source, triage_record, update_source_raw, update_claim_quote,
            update_claim_text,
            create_claim, find_similar_claim,
            promote_claim, set_claim_status, list_pending, create_wiki_page,
            update_wiki_page, create_learning_item, list_due_reviews, record_review,
            collect_git_session, create_session_summary, create_decision, search_wiki,
            vault_next_step]


def build_wiki_server(vault: Path):
    return create_sdk_mcp_server(
        name="wiki", version="0.1.0", tools=build_wiki_tools(vault),
    )
