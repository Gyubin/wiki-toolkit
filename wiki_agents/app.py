"""FastAPI app: capture + deterministic queue routes (core, no LLM) + chat (SSE)."""
from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import schema
from .core import claims, git, ids, learning, lint, search, sources

_WEB = Path(__file__).parent / "web"

# 브라우저 확장(웹 클리퍼)과 이 앱 자신만 허용. 임의 웹페이지가 localhost로
# 쏘는 drive-by 요청(/chat이 에이전트를 실행한다)을 Origin 헤더로 차단한다.
_EXTENSION_SCHEMES = ("chrome-extension://", "moz-extension://", "safari-web-extension://")
_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}


def _origin_allowed(origin: str) -> bool:
    if origin.startswith(_EXTENSION_SCHEMES):
        return True
    return urlparse(origin).hostname in _LOCAL_HOSTS


def _host_allowed(host_header: str) -> bool:
    # DNS 리바인딩 방어: 공격자 도메인이 127.0.0.1로 리졸브되면 Origin 없는 GET이
    # 같은 오리진으로 취급돼 응답까지 읽힌다. Host가 로컬이 아니면 거부한다.
    # "testserver"는 FastAPI TestClient의 기본 Host (브라우저로는 보낼 수 없는 값).
    host = urlparse(f"//{host_header}").hostname
    return host in (_LOCAL_HOSTS | {"testserver"})


# HTTP 200으로 내려오는 봇 차단 페이지는 저장해봐야 쓰레기다 (실제 사고 사례: x.com)
_BOTWALL_MARKERS = (
    "JavaScript is not available",
    "Enable JavaScript and cookies to continue",
    "Attention Required! | Cloudflare",
    "Checking if the site connection is secure",
)
_MIN_CAPTURE_CHARS = 200


class CaptureBody(BaseModel):
    origin: str = "manual"
    content: str | None = None
    url: str | None = None
    sensitivity: str = "personal"


# 주의: 요청 모델은 반드시 모듈 레벨에 둔다. `from __future__ import annotations`
# 아래에서 함수 안에 정의하면 FastAPI가 문자열 어노테이션을 해석하지 못해
# body가 query 필드로 강등되고 모든 요청이 422가 된다 (기존 /chat, /wrap이 그랬다).
class ChatBody(BaseModel):
    prompt: str


class WrapBody(BaseModel):
    repo: str
    base: str
    head: str = "HEAD"
    transcript: str | None = None


def create_app(vault: Path, embed_fn=None) -> FastAPI:
    vault = Path(vault)
    app = FastAPI(title="Personal AI Wiki")

    @app.middleware("http")
    async def origin_guard(request: Request, call_next):
        origin = request.headers.get("origin")
        if origin and not _origin_allowed(origin):
            return JSONResponse({"detail": "forbidden origin"}, status_code=403)
        host = request.headers.get("host")
        if host and not _host_allowed(host):
            return JSONResponse({"detail": "forbidden host"}, status_code=403)
        return await call_next(request)

    @app.exception_handler(FileNotFoundError)
    async def not_found(request: Request, exc: FileNotFoundError):
        return JSONResponse({"detail": f"not found: {exc}"}, status_code=404)

    @app.exception_handler(PermissionError)
    async def forbidden(request: Request, exc: PermissionError):
        return JSONResponse({"detail": str(exc)}, status_code=403)

    @app.exception_handler(ValueError)
    async def bad_request(request: Request, exc: ValueError):
        return JSONResponse({"detail": str(exc)}, status_code=400)

    @app.exception_handler(FileExistsError)
    async def conflict(request: Request, exc: FileExistsError):
        return JSONResponse({"detail": str(exc)}, status_code=409)

    @app.exception_handler(RuntimeError)
    async def unavailable(request: Request, exc: RuntimeError):
        # 임베딩 provider 설정 문제(키 부재 등)를 500 대신 읽을 수 있는 503으로
        return JSONResponse({"detail": str(exc)}, status_code=503)

    @app.post("/capture")
    def capture(body: CaptureBody):
        content = body.content
        if body.url and not content:
            try:
                resp = httpx.get(body.url, follow_redirects=True, timeout=20)
                resp.raise_for_status()
            except httpx.HTTPError as e:
                return JSONResponse({"detail": f"failed to fetch URL: {e}"}, status_code=502)
            content = sources.html_to_markdown(resp.text)
            if len(content) < _MIN_CAPTURE_CHARS or any(m in content for m in _BOTWALL_MARKERS):
                return JSONResponse(
                    {"detail": "capture looks like a bot-wall or near-empty page; not saved"},
                    status_code=422)
        path = sources.create_source(
            vault, origin=body.origin, content=content or "",
            sensitivity=body.sensitivity, date_str=schema.today_str(),
            seq=ids.next_seq(vault, "source", schema.today_str(), ["00_Inbox"]),
            url=body.url,
        )
        git.commit_vault(vault, f"wiki: captured {path.stem}", paths=["00_Inbox", "06_Metadata"])
        return {"id": path.stem}

    @app.get("/claims/pending")
    def pending():
        return claims.list_pending(vault)

    @app.post("/claims/{cid}/approve")
    def approve(cid: str):
        p = claims.promote_claim(vault, cid, target_status="verified",
                                 approved_by_human=True, date_str=schema.today_str())
        git.commit_vault(vault, f"wiki: human approved {cid} -> verified",
                         paths=["10_Claims", "06_Metadata"])
        return {"id": cid, "status": "verified", "path": str(p)}

    @app.post("/claims/{cid}/reject")
    def reject(cid: str):
        p = claims.set_claim_status(vault, cid, status="rejected",
                                    date_str=schema.today_str())
        git.commit_vault(vault, f"wiki: human rejected {cid}", paths=["10_Claims", "06_Metadata"])
        return {"id": cid, "status": "rejected", "path": str(p)}

    @app.get("/reviews/due")
    def due():
        return learning.list_due_reviews(vault, schema.today_str())

    @app.post("/reviews/{lid}/record")
    def record(lid: str, passed: bool = True):
        p = learning.record_review(vault, lid, passed=passed, today_str=schema.today_str())
        git.commit_vault(vault, f"wiki: review {lid} passed={passed}",
                         paths=["30_Learning", "06_Metadata"])
        return {"id": lid, "path": str(p)}

    @app.get("/lint")
    def lint_check():
        return lint.run_checks(vault, schema.today_str())

    _index_cache = search.IndexCache(vault, embed_fn=embed_fn)

    @app.get("/search")
    def search_route(q: str = "", k: int = 8, reindex: bool = False):
        return _index_cache.get(force=reindex).query(q, k)

    @app.get("/")
    def home():
        return FileResponse(_WEB / "index.html")

    if _WEB.exists():
        app.mount("/static", StaticFiles(directory=_WEB), name="static")

    _attach_chat(app, vault)
    return app


def _attach_chat(app: FastAPI, vault: Path) -> None:
    import asyncio
    import json

    from . import agent as agent_mod

    # 앱 수명 동안 하나의 대화 세션을 유지한다 (요청마다 새로 만들면 매 턴 기억 상실).
    state: dict = {"session": None}
    turn_lock = asyncio.Lock()

    async def _close_session() -> None:
        session = state["session"]
        state["session"] = None
        if session is not None:
            try:
                await session.__aexit__(None, None, None)
            except Exception:  # noqa: S110 - 이미 죽은 세션 정리 실패는 무시해도 된다
                pass

    _SSE = "text/event-stream; charset=utf-8"

    def _event(payload) -> str:
        # SSE payload는 JSON 한 덩어리: 개행이 든 청크도 프레이밍이 깨지지 않는다
        return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"

    async def _stream(prompt: str):
        async with turn_lock:
            try:
                if state["session"] is None:
                    session = agent_mod.WikiSession(vault)
                    await session.__aenter__()
                    state["session"] = session
                async for chunk in state["session"].ask(prompt):
                    yield _event(chunk)
            except BaseException as e:  # noqa: BLE001
                # GeneratorExit(클라이언트 끊김)도 잡는다: 턴 중간에 끊긴 세션을
                # 재사용하면 다음 질문의 응답에 이전 턴 잔여 메시지가 섞인다.
                await _close_session()
                if isinstance(e, GeneratorExit | asyncio.CancelledError):
                    raise
                yield _event({"error": str(e)})
        yield "data: [DONE]\n\n"

    @app.post("/chat")
    async def chat(body: ChatBody):
        return StreamingResponse(_stream(body.prompt), media_type=_SSE)

    @app.post("/chat/reset")
    async def chat_reset():
        async with turn_lock:
            await _close_session()
        return {"ok": True}

    app.router.on_shutdown.append(_close_session)

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
        return StreamingResponse(_stream(prompt), media_type=_SSE)

    @app.post("/lint/contradictions")
    async def lint_contradictions():
        prompt = ("Use the lint subagent to audit the claim ledger for contradictions and report "
                  "the conflicting pairs. Report only - do not modify any claim.")
        return StreamingResponse(_stream(prompt), media_type=_SSE)
