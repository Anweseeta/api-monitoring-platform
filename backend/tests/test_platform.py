"""Demo/health endpoints, dashboard, activity, settings, webhooks, security."""
from tests.conftest import auth_headers


async def test_health_endpoints(client):
    r = await client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}

    r = await client.get("/health/db")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy", "db": "connected"}


async def test_demo_endpoints_unprotected(client):
    r = await client.get("/demo/health")
    assert r.status_code == 200
    assert r.json() == {"status": "healthy"}

    r = await client.get("/demo/error")
    assert r.status_code == 500
    assert r.json() == {"status": "error"}

    r = await client.get("/demo/random")
    assert r.status_code in (200, 500)

    r = await client.post("/demo/echo", json={"hello": "world"},
                          headers={"Authorization": "Bearer super-secret-token"})
    assert r.status_code == 200
    body = r.json()
    assert body["received"] == {"hello": "world"}
    assert body["method"] == "POST"
    redacted = body["headers_redacted"]
    assert redacted["authorization"] == "[REDACTED]"
    assert "super-secret-token" not in str(redacted)


async def test_dashboard_summary_populated(client, demo_server, clean_db):
    from app.monitoring.engine import check_monitor

    headers = await auth_headers(client, email="dash@example.com")
    # failure_threshold=1 so the single failing check marks the monitor down
    await client.put("/api/settings", json={"failure_threshold": 1}, headers=headers)
    base = demo_server
    for path, name in [("/demo/health", "H"), ("/demo/error", "E")]:
        r = await client.post("/api/monitors", json={
            "name": name, "url": f"{base}{path}", "interval": 60}, headers=headers)
        assert r.status_code == 201
        mid = r.json()["data"]["id"]
        await check_monitor(mid, clean_db)

    r = await client.get("/api/dashboard/summary", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["total_apis"] == 2
    assert data["healthy_apis"] == 1
    assert data["overall_uptime_24h"] == 50.0
    assert data["avg_response_time_ms"] is not None
    assert len(data["recent_activity"]) >= 2
    assert data["health_overview"]["healthy"] == 1

    for period in ("24h", "7d", "30d"):
        for route in ("uptime", "latency", "incidents"):
            r = await client.get(f"/api/dashboard/{route}?period={period}", headers=headers)
            assert r.status_code == 200, (route, period, r.text)
            assert "points" in r.json()["data"]

    r = await client.get("/api/dashboard/uptime?period=bogus", headers=headers)
    assert r.status_code == 400
    assert r.json()["error_code"] == "VALIDATION_ERROR"


async def test_activity_log_records_actions(client, demo_server):
    headers = await auth_headers(client, email="act@example.com")
    r = await client.post("/api/monitors", json={
        "name": "Act API", "url": f"{demo_server}/demo/health", "interval": 60}, headers=headers)
    mid = r.json()["data"]["id"]
    await client.post(f"/api/monitors/{mid}/pause", headers=headers)

    r = await client.get("/api/activity", headers=headers)
    body = r.json()
    assert body["success"] is True
    actions = [e["action"] for e in body["data"]]
    assert "user.registered" in actions
    assert "api.created" in actions
    assert "api.paused" in actions

    r = await client.get("/api/activity?action=api.created", headers=headers)
    assert all(e["action"] == "api.created" for e in r.json()["data"])

    # activity never contains auth headers
    assert "Bearer" not in str(body["data"])


async def test_settings_get_and_update(client):
    headers = await auth_headers(client, email="set@example.com")

    r = await client.get("/api/settings", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["failure_threshold"] == 3
    assert data["recovery_threshold"] == 2
    assert data["degraded_latency_ms"] == 1000
    assert data["results_retention_days"] == 30
    assert data["profile"]["email"] == "set@example.com"

    r = await client.put("/api/settings", json={
        "failure_threshold": 5,
        "notifications": {"email_enabled": True},
        "profile": {"name": "New Name", "email": "hacker@example.com"},
    }, headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["failure_threshold"] == 5
    assert data["notifications"]["email_enabled"] is True
    assert data["profile"]["name"] == "New Name"
    # profile.email is read-only
    assert data["profile"]["email"] == "set@example.com"

    r = await client.get("/api/auth/me", headers=headers)
    assert r.json()["data"]["user"]["name"] == "New Name"


async def test_webhooks_crud(client, monkeypatch):
    # The sandbox has no external DNS; bypass the SSRF DNS lookup (the
    # SSRF guard itself is covered by monitor validation tests).
    import app.api.webhooks as webhooks_route
    monkeypatch.setattr(webhooks_route, "check_url_allowed", lambda url: ("hooks.example.com", 443))
    headers = await auth_headers(client, email="wh@example.com")

    r = await client.post("/api/webhooks", json={
        "name": "Slack", "url": "https://hooks.example.com/x",
        "events": ["incident.created", "api.down"]}, headers=headers)
    assert r.status_code == 201
    wh = r.json()["data"]
    assert wh["active"] is True
    wid = wh["id"]

    r = await client.post("/api/webhooks", json={
        "name": "Bad", "url": "https://hooks.example.com/x", "events": ["nope"]}, headers=headers)
    assert r.status_code == 422

    r = await client.get("/api/webhooks", headers=headers)
    assert len(r.json()["data"]) == 1

    r = await client.delete(f"/api/webhooks/{wid}", headers=headers)
    assert r.status_code == 200
    r = await client.delete(f"/api/webhooks/{wid}", headers=headers)
    assert r.status_code == 404
    assert r.json()["error_code"] == "WEBHOOK_NOT_FOUND"


async def test_cross_user_webhook_isolation(client, monkeypatch):
    import app.api.webhooks as webhooks_route
    monkeypatch.setattr(webhooks_route, "check_url_allowed", lambda url: ("hooks.example.com", 443))
    headers_a = await auth_headers(client, email="wa@example.com")
    headers_b = await auth_headers(client, email="wb@example.com")
    r = await client.post("/api/webhooks", json={
        "name": "A hook", "url": "https://hooks.example.com/a", "events": ["incident.created"]},
        headers=headers_a)
    wid = r.json()["data"]["id"]

    r = await client.delete(f"/api/webhooks/{wid}", headers=headers_b)
    assert r.status_code == 403

    r = await client.get("/api/webhooks", headers=headers_b)
    assert r.json()["data"] == []
