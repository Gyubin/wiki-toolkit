from fastapi.testclient import TestClient
from wiki_agent.app import create_app


def test_capture_and_pending(vault):
    app = create_app(vault)
    client = TestClient(app)

    r = client.post("/capture", json={"origin": "chatgpt", "content": "raw text"})
    assert r.status_code == 200
    sid = r.json()["id"]
    assert sid.startswith("source-")

    from wiki_agent.core import claims
    from wiki_agent import schema
    claims.create_claim(vault, claim="some claim", claim_type="technical_fact",
                        source_refs=[sid], date_str=schema.today_str(), seq=1)

    r = client.get("/claims/pending")
    assert r.status_code == 200
    rows = r.json()
    assert any(row["claim"] == "some claim" for row in rows)


def test_approve_claim(vault):
    app = create_app(vault)
    client = TestClient(app)
    from wiki_agent.core import claims
    from wiki_agent import schema
    claims.create_claim(vault, claim="c", claim_type="technical_fact",
                        source_refs=[], date_str=schema.today_str(), seq=1)
    cid = "claim-" + schema.today_str().replace("-", "") + "-001"

    r = client.post(f"/claims/{cid}/approve")
    assert r.status_code == 200
    assert (vault / "10_Claims/verified" / f"{cid}.md").exists()


def test_due_reviews_route(vault):
    app = create_app(vault)
    client = TestClient(app)
    from wiki_agent.core import learning
    from wiki_agent import schema
    learning.create_learning_item(vault, topic="t", skill_area="frontend",
                                  date_str=schema.today_str(), seq=1)
    r = client.get("/reviews/due")
    assert r.status_code == 200
    assert len(r.json()) >= 1


def test_chat_route_exists(vault):
    app = create_app(vault)
    routes = {r.path for r in app.routes}
    assert "/chat" in routes
