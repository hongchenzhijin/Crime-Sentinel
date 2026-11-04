def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["posts_loaded"] == 8
    assert r.json()["app"] == "Crime Sentinel"


def test_dataset_reports_synthetic(client):
    body = client.get("/api/dataset").json()
    assert body["is_synthetic"] is True
    assert body["total_posts"] == 8
    assert body["period_start"].startswith("2026-09-01")


def test_posts_pagination_and_priority_sort(client):
    body = client.get("/api/posts", params={"page_size": 3}).json()
    assert body["total"] == 8 and len(body["items"]) == 3
    assert body["items"][0]["classification"]["review_priority"] == "urgent"
    page3 = client.get("/api/posts", params={"page_size": 3, "page": 3}).json()
    assert len(page3["items"]) == 2


def test_post_filters(client):
    r = client.get("/api/posts", params={"category": "NEWS_REPORTING"}).json()
    assert [i["post"]["id"] for i in r["items"]] == ["post_0001"]
    r = client.get("/api/posts", params={"topic_id": "topic_b"}).json()
    assert r["total"] == 3
    r = client.get("/api/posts", params={"date_from": "2026-09-07T00:00:00Z"}).json()
    assert r["total"] == 2
    r = client.get("/api/posts", params={"search": "documentary"}).json()
    assert r["total"] == 1


def test_invalid_filters_rejected(client):
    assert client.get("/api/posts", params={"category": "NOT_A_CATEGORY"}).status_code == 422
    assert client.get("/api/posts", params={"page_size": 1000}).status_code == 422
    r = client.get("/api/posts", params={"date_from": "2026-09-10T00:00:00Z", "date_to": "2026-09-01T00:00:00Z"})
    assert r.status_code == 422


def test_post_not_found(client):
    assert client.get("/api/posts/post_9999").status_code == 404
    assert client.post("/api/posts/post_9999/review", json={"action": "confirm"}).status_code == 404


def test_review_validation(client):
    assert client.post("/api/posts/post_0007/review", json={"action": "change"}).status_code == 422
    r = client.post("/api/posts/post_0007/review", json={"action": "confirm", "reviewer_category": "NEWS_REPORTING"})
    assert r.status_code == 422


def test_review_correction_flow_and_audit(client):
    before = client.get("/api/posts/post_0007").json()["classification"]
    assert before["category"] == "UNCERTAIN_REQUIRES_REVIEW"
    r = client.post("/api/posts/post_0007/review", json={
        "action": "change", "reviewer_category": "NEUTRAL_DISCUSSION", "note": "historical reference", "reviewer": "r1",
    })
    assert r.status_code == 200
    c = r.json()["classification"]
    assert c["review_status"] == "corrected"
    assert c["reviewer_category"] == "NEUTRAL_DISCUSSION"
    assert c["category"] == "UNCERTAIN_REQUIRES_REVIEW"  # model output preserved
    audit = client.get("/api/posts/post_0007/audit").json()
    assert audit[0]["action"] == "review_change" and audit[0]["actor"] == "r1"
    assert audit[0]["details"]["model_category"] == "UNCERTAIN_REQUIRES_REVIEW"
    # Filtering uses the effective (reviewer) category.
    r = client.get("/api/posts", params={"category": "NEUTRAL_DISCUSSION"}).json()
    assert "post_0007" in [i["post"]["id"] for i in r["items"]]


def test_mark_uncertain(client):
    c = client.post("/api/posts/post_0004/review", json={"action": "mark_uncertain"}).json()["classification"]
    assert c["review_status"] == "marked_uncertain"
    assert c["reviewer_category"] == "UNCERTAIN_REQUIRES_REVIEW"


def test_dashboard_summary(client):
    s = client.get("/api/dashboard/summary").json()
    assert s["total_posts"] == 8
    assert s["pending_review_pct"] == 100.0
    assert s["urgent_threat_pending"] >= 1
    assert sum(b["count"] for b in s["confidence_histogram"]) == 8
    assert "not a probability" in s["confidence_note"]
    assert "evaluation_false_positive_rate" in s


def test_network_and_trends_endpoints(client):
    g = client.get("/api/network", params=[("edge_types", "USES_HASHTAG")]).json()
    assert {e["type"] for e in g["edges"]} == {"USES_HASHTAG"}
    assert "do not establish membership" in g["disclaimer"]
    t = client.get("/api/trends", params={"granularity": "day"}).json()
    assert t["granularity"] == "day" and t["series"]


def test_export_report_redacts_harmful_and_is_audited(client):
    client.post("/api/posts/post_0004/review", json={"action": "confirm"})
    client.post("/api/posts/post_0001/review", json={"action": "confirm"})
    rep = client.get("/api/export/report").json()
    by_id = {e["post_id"]: e for e in rep["reviewed_examples"]}
    assert "withheld" in by_id["post_0004"]["excerpt"]
    assert "Police said" in by_id["post_0001"]["excerpt"]
    assert any(a["action"] == "export_report" for a in client.get("/api/audit").json())


def test_no_direct_engagement_endpoints(client):
    """Outbound actions exist only inside the sandbox and only via a governed mission; the API itself
    exposes no endpoint to post, message, follow, or profile anyone."""
    spec = client.get("/openapi.json").json()["paths"]
    posts = {p for p, ops in spec.items() if "post" in ops}
    assert posts == {"/api/posts/{post_id}/review", "/api/sandbox/reset", "/api/sandbox/groups/{group_id}/join", "/api/missions",
                     "/api/missions/{mission_id}/stop", "/api/approvals/{approval_id}",
                     # internal analysis only (no outbound contact): rebuild communities, ask, reclassify
                     "/api/graphrag/build", "/api/graphrag/ask", "/api/learning/reclassify"}
    for forbidden in ("follow", "contact", "like", "profile", "send"):
        assert not any(forbidden in p for p in spec)
