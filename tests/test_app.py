from fastapi.testclient import TestClient

from wiki_agents.app import create_app


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
