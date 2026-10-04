"""API contract tests against the real app (auto-seeded temp database)."""
import io

DRAFT = {"platform": "Instagram", "format": "Carousel", "topic": "Education", "hook": "Numbered list", "tone": "Warm",
         "caption": "5 things about content calendars. Save this! #learning", "scheduled_at": "2026-10-06T19:00:00"}


def test_health(client):
    j = client.get("/api/health").json()
    assert j["status"] == "ok" and j["posts"] == 720


def test_overview_contract(client):
    j = client.get("/api/overview").json()
    for key in ("kpis", "trend", "platforms", "top_posts", "bottom_posts", "signals", "experiments", "learnings", "model_health"):
        assert key in j
    assert j["trend"]["monthly"] and all({"month", "posts", "engagement_rate"} <= set(m) for m in j["trend"]["monthly"])


def test_posts_pagination_and_filters(client):
    j = client.get("/api/posts", params={"platform": "LinkedIn", "page_size": 10, "sort": "engagement_rate"}).json()
    assert len(j["items"]) == 10 and all(i["platform"] == "LinkedIn" for i in j["items"])
    ers = [i["engagement_rate"] for i in j["items"]]
    assert ers == sorted(ers, reverse=True)
    assert client.get("/api/posts", params={"page_size": 1000}).status_code == 422
    assert client.get("/api/posts", params={"sort": "likes; drop"}).status_code == 422
    none = client.get("/api/posts", params={"search": "zzzzqqqq"}).json()
    assert none["total"] == 0 and none["items"] == []


def test_autopsy_and_404(client):
    pid = client.get("/api/posts", params={"page_size": 1}).json()["items"][0]["post_id"]
    j = client.get(f"/api/posts/{pid}/autopsy").json()
    assert j["post"]["id"] == pid and j["benchmark"]["platform_n"] > 0 and j["model_check"]["split"] in ("holdout", "training")
    r = client.get("/api/posts/99999999/autopsy")
    assert r.status_code == 404 and r.json()["error"]["code"] == "post_not_found"


def test_lab_predict_and_validation(client):
    r = client.post("/api/lab/predict", json=DRAFT)
    assert r.status_code == 200 and r.json()["prediction"]["engagement_rate"] > 0
    assert client.post("/api/lab/predict", json={**DRAFT, "hook": "Nonsense"}).status_code == 422
    assert client.post("/api/lab/predict", json={**DRAFT, "caption": ""}).status_code == 422
    assert client.post("/api/lab/predict", json={**DRAFT, "scheduled_at": "not-a-date"}).status_code == 422


def test_olap_endpoints(client):
    assert client.get("/api/olap/schema").json()["measures"]
    r = client.post("/api/olap/query", json={"rows": ["platform"], "measures": ["posts", "engagement_rate"]})
    assert r.status_code == 200 and r.json()["n_posts"] == 720
    assert client.post("/api/olap/query", json={"rows": ["bogus"]}).status_code == 422
    assert client.post("/api/olap/query", json={"columns": "platform"}).status_code == 422


def test_models_registry(client):
    j = client.get("/api/models").json()
    assert len(j["runs"]) == 8 and all(r["metrics"] for r in j["runs"])
    full = client.get("/api/models/multiple_linear_regression").json()
    assert full["results"]["terms"] and full["metrics"]["r2"] is not None
    assert client.get("/api/models/nope").status_code == 404


def test_experiments_api_flow(client):
    body = {"name": "API flow test", "hypothesis": "Short beats long", "variable": "caption_length", "platform": "X",
            "min_per_variant": 3,
            "variants": [{"label": "A", "description": "long", "is_control": True}, {"label": "B", "description": "short"}]}
    r = client.post("/api/experiments", json=body)
    assert r.status_code == 201
    exp = r.json()
    assert exp["status"] == "running" and exp["analysis"]["verdict"] == "insufficient_data"
    assert client.post(f"/api/experiments/{exp['id']}/complete").status_code == 422
    vid = exp["variants"][0]["id"]
    bad = client.post(f"/api/experiments/{exp['id']}/observations",
                      json={"variant_id": vid, "published_at": "2026-09-01T10:00:00", "impressions": 10, "engagements": 50})
    assert bad.status_code == 422
    foreign = client.post(f"/api/experiments/{exp['id']}/observations",
                          json={"variant_id": 999999, "published_at": "2026-09-01T10:00:00", "impressions": 100, "engagements": 5})
    assert foreign.status_code == 404
    assert client.get("/api/experiments/999999").status_code == 404


def test_ai_interpret(client):
    j = client.post("/api/ai/interpret", json={"scope": "overview"}).json()
    assert j["source"] in ("deterministic", "llm") and j["statements"] and j["evidence"]
    ids = {e["id"] for e in j["evidence"]}
    assert all(set(s["evidence_ids"]) <= ids for s in j["statements"])
    assert client.post("/api/ai/interpret", json={"scope": "autopsy"}).status_code == 422
    assert client.post("/api/ai/interpret", json={"scope": "bogus"}).status_code == 422
    pj = client.post("/api/ai/interpret", json={"scope": "prediction", "draft": DRAFT}).json()
    assert pj["statements"]


def test_csv_ingest_validation(client):
    header = "external_id,platform,format,topic,hook_type,tone,caption,published_at,impressions,reach,likes,comments,shares,saves\n"
    good = "NEW-1,Instagram,Reel,Education,Question,Warm,\"Hello there? #x\",2026-02-01T09:00:00,1000,800,40,5,3,2\n"
    bad = "NEW-2,Instagram,Reel,Education,Question,Warm,hi,2026-02-01T09:00:00,0,0,0,0,0,0\n"
    r = client.post("/api/ingest/csv", files={"file": ("p.csv", io.BytesIO((header + good + bad).encode()), "text/csv")})
    assert r.status_code == 200
    rep = r.json()["report"]
    assert rep["rows_loaded"] == 1 and rep["rows_rejected"] == 1
    missing = client.post("/api/ingest/csv", files={"file": ("p.csv", io.BytesIO(b"a,b\n1,2\n"), "text/csv")})
    assert missing.status_code == 422 and missing.json()["error"]["code"] == "missing_columns"
    empty = client.post("/api/ingest/csv", files={"file": ("p.csv", io.BytesIO(header.encode()), "text/csv")})
    assert empty.status_code == 422
    assert client.get("/api/etl/runs").json()["items"]
