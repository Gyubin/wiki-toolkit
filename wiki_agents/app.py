"""FastAPI app: capture + deterministic queue routes (core, no LLM) + chat (SSE)."""
from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import schema
from .core import claims, ids, learning, lint, search, sources

_WEB = Path(__file__).parent / "web"


class CaptureBody(BaseModel):
    origin: str = "manual"
    content: str | None = None
    url: str | None = None
    sensitivity: str = "personal"


def create_app(vault: Path, embed_fn=None) -> FastAPI:
    vault = Path(vault)
    app = FastAPI(title="Personal AI Wiki")

    @app.post("/capture")
    def capture(body: CaptureBody):
        content = body.content
        if body.url and not content:
            html = httpx.get(body.url, follow_redirects=True, timeout=20).text
            content = sources.html_to_markdown(html)
        path = sources.create_source(
            vault, origin=body.origin, content=content or "",
            sensitivity=body.sensitivity, date_str=schema.today_str(),
            seq=ids.next_seq(vault, "source", schema.today_str(), ["00_Inbox"]),
            url=body.url,
        )
        return {"id": path.stem}

    @app.get("/claims/pending")
    def pending():
        return claims.list_pending(vault)

    @app.post("/claims/{cid}/approve")
    def approve(cid: str):
        p = claims.promote_claim(vault, cid, target_status="verified",
                                 approved_by_human=True, date_str=schema.today_str())
        return {"id": cid, "status": "verified", "path": str(p)}

    @app.post("/claims/{cid}/reject")
    def reject(cid: str):
        p = claims.set_claim_status(vault, cid, status="rejected",
                                    date_str=schema.today_str())
        return {"id": cid, "status": "rejected", "path": str(p)}

    @app.get("/reviews/due")
    def due():
        return learning.list_due_reviews(vault, schema.today_str())

    @app.post("/reviews/{lid}/record")
    def record(lid: str, passed: bool = True):
        p = learning.record_review(vault, lid, passed=passed, today_str=schema.today_str())
        return {"id": lid, "path": str(p)}

    @app.get("/lint")
    def lint_check():
        return lint.run_checks(vault, schema.today_str())

    _search_index: dict = {}

    @app.get("/search")
    def search_route(q: str = "", k: int = 8, reindex: bool = False):
        if reindex or "idx" not in _search_index:
            _search_index["idx"] = search.build_index(vault, embed_fn=embed_fn)
        return _search_index["idx"].query(q, k)

    @app.get("/")
    def home():
        return FileResponse(_WEB / "index.html")

    if _WEB.exists():
        app.mount("/static", StaticFiles(directory=_WEB), name="static")

    _attach_chat(app, vault)
    return app


def _attach_chat(app: FastAPI, vault: Path) -> None:
    from .agent import WikiSession

    class ChatBody(BaseModel):
        prompt: str

    class WrapBody(BaseModel):
        repo: str
        base: str
        head: str = "HEAD"
        transcript: str | None = None

    async def _stream(prompt: str):
        async with WikiSession(vault) as session:
            async for chunk in session.ask(prompt):
                yield f"data: {chunk}\n\n"
        yield "data: [DONE]\n\n"

    @app.post("/chat")
    async def chat(body: ChatBody):
        return StreamingResponse(_stream(body.prompt), media_type="text/event-stream")

    @app.post("/wrap")
    async def wrap(body: WrapBody):
        prompt = (
            "Use the wrap subagent to wrap up this coding session. "
            f"repo={body.repo}, range={body.base}..{body.head}. "
            "First call collect_git_session, then produce a session summary, any ADRs, "
            "generalized concept/pattern pages, and learning items."
        )
        if body.transcript:
            prompt += f"\n\nTranscript (optional context):\n{body.transcript}"
        return StreamingResponse(_stream(prompt), media_type="text/event-stream")

    @app.post("/lint/contradictions")
    async def lint_contradictions():
        prompt = ("Use the lint subagent to audit the claim ledger for contradictions and report "
                  "the conflicting pairs. Report only — do not modify any claim.")
        return StreamingResponse(_stream(prompt), media_type="text/event-stream")
