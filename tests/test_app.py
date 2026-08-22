import json

from fastapi.testclient import TestClient

from wiki_agents.app import create_app


class _FakeSession:
    instances = 0

    def __init__(self, vault):
        _FakeSession.instances += 1

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def ask(self, prompt):
        yield "첫 줄\n둘째 줄"
        yield "이어지는 답"


def test_capture_and_pending(vault):
    app = create_app(vault)
    client = TestClient(app)

    r = client.post("/capture", json={"origin": "chatgpt", "content": "raw text"})
    assert r.status_code == 200
    sid = r.json()["id"]
    assert sid.startswith("source-")

    from wiki_agents import schema
    from wiki_agents.core import claims
    claims.create_claim(vault, claim="some claim", claim_type="technical_fact",
                        source_refs=[sid], date_str=schema.today_str(), seq=1)

    r = client.get("/claims/pending")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["claim"] == "some claim" for row in rows)


def test_approve_claim(vault):
    app = create_app(vault)
    client = TestClient(app)
    from wiki_agents import schema
    from wiki_agents.core import claims
    claims.create_claim(vault, claim="c", claim_type="technical_fact",
                        source_refs=[], date_str=schema.today_str(), seq=1)
    cid = "claim-" + schema.today_str().replace("-", "") + "-001"

    r = client.post(f"/claims/{cid}/approve")
    assert r.status_code == 200
    assert (vault / "10_Claims/verified" / f"{cid}.md").exists()


def test_due_reviews_route(vault):
    app = create_app(vault)
    client = TestClient(app)
    from wiki_agents import schema
    from wiki_agents.core import learning
    learning.create_learning_item(vault, topic="t", skill_area="frontend",
                                  date_str=schema.today_str(), seq=1)
    r = client.get("/reviews/due")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_chat_route_exists(vault):
    app = create_app(vault)
    routes = {r.path for r in app.routes}
    assert "/chat" in routes


def test_wrap_route_exists(vault):
    app = create_app(vault)
    routes = {r.path for r in app.routes}
    assert "/wrap" in routes


def test_lint_route(vault):
    app = create_app(vault)
    client = TestClient(app)
    r = client.get("/lint")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_contradictions_route_exists(vault):
    app = create_app(vault)
    routes = {r.path for r in app.routes}
    assert "/lint/contradictions" in routes


_SEARCH_VOCAB = ["python", "typed", "react", "hook", "git", "commit"]


def _fake_embed(texts):
    from wiki_agents.core import search
    return [[1.0 if w in set(search.tokenize(t)) else 0.0 for w in _SEARCH_VOCAB] for t in texts]


def test_search_route(vault):
    from wiki_agents import schema
    from wiki_agents.core import claims
    claims.create_claim(vault, claim="react hook timing", claim_type="technical_fact",
                        source_refs=["s"], date_str=schema.today_str(), seq=1)
    claims.create_claim(vault, claim="git commit conventions", claim_type="technical_fact",
                        source_refs=["s"], date_str=schema.today_str(), seq=2)
    app = create_app(vault, embed_fn=_fake_embed)
    client = TestClient(app)
    r = client.get("/search?q=react")
    assert r.status_code == 200
    rows = r.json()
    assert isinstance(rows, list) and rows
    assert "react" in rows[0]["title"].lower()


def test_approve_missing_claim_is_404_not_500(vault):
    client = TestClient(create_app(vault))
    r = client.post("/claims/claim-19990101-001/approve")
    assert r.status_code == 404


def test_capture_bad_url_is_502(vault, monkeypatch):
    import httpx

    from wiki_agents import app as app_mod

    def boom(*a, **k):
        raise httpx.ConnectError("nope")

    monkeypatch.setattr(app_mod.httpx, "get", boom)
    client = TestClient(create_app(vault))
    r = client.post("/capture", json={"origin": "web", "url": "http://x.invalid"})
    assert r.status_code == 502


def test_cross_origin_browser_requests_are_rejected(vault):
    client = TestClient(create_app(vault))
    r = client.post("/capture", json={"origin": "web", "content": "x"},
                    headers={"Origin": "https://evil.example"})
    assert r.status_code == 403
    r = client.post("/capture", json={"origin": "web", "content": "x"},
                    headers={"Origin": "http://127.0.0.1:8765"})
    assert r.status_code == 200
    r = client.post("/capture", json={"origin": "ext", "content": "y"},
                    headers={"Origin": "chrome-extension://abcdef"})
    assert r.status_code == 200


def _chat_events(text):
    events = []
    for block in text.split("\n\n"):
        block = block.strip()
        if not block:
            continue
        assert block.startswith("data: ")
        events.append(block[len("data: "):])
    return events


def test_chat_sse_preserves_multiline_chunks(vault, monkeypatch):
    from wiki_agents import agent as agent_mod
    _FakeSession.instances = 0
    monkeypatch.setattr(agent_mod, "WikiSession", _FakeSession)
    client = TestClient(create_app(vault))
    r = client.post("/chat", json={"prompt": "안녕"})
    assert r.status_code == 200
    events = _chat_events(r.text)
    assert events[-1] == "[DONE]"
    payloads = [json.loads(e) for e in events[:-1]]
    assert "첫 줄\n둘째 줄" in payloads  # 개행이 든 청크가 통째로 보존된다


def test_chat_session_persists_across_requests(vault, monkeypatch):
    from wiki_agents import agent as agent_mod
    _FakeSession.instances = 0
    monkeypatch.setattr(agent_mod, "WikiSession", _FakeSession)
    client = TestClient(create_app(vault))
    client.post("/chat", json={"prompt": "하나"})
    client.post("/chat", json={"prompt": "둘"})
    assert _FakeSession.instances == 1  # 요청마다 새 세션을 만들면 안 된다

    r = client.post("/chat/reset")
    assert r.status_code == 200
    client.post("/chat", json={"prompt": "셋"})
    assert _FakeSession.instances == 2  # reset 후에만 새 세션
