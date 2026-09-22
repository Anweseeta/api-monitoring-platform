"""Monitor CRUD tests + user isolation."""

from tests.conftest import auth_headers

MONITOR_URL = None  # set per-test from demo_server


def _payload(**overrides):
    payload = {
        "name": "Payments API",
        "url": MONITOR_URL,
        "method": "GET",
        "interval": 300,
        "timeout": 10,
        "expected_status": 200,
    }
    payload.update(overrides)
    return payload


async def _create(client, headers, base, **overrides):
    global MONITOR_URL
    MONITOR_URL = f"{base}/demo/health"
    r = await client.post("/api/monitors", json=_payload(**overrides), headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_monitor_crud_lifecycle(client, demo_server):
    headers = await auth_headers(client, email="crud@example.com")
    base = demo_server

    # create (point at the real demo server so checks work)
    monitor = await _create(client, headers, base, interval=60)
    assert monitor["name"] == "Payments API"
    assert monitor["status"] == "healthy"
    assert monitor["active"] is True
    mid = monitor["id"]

    # list contains it
    r = await client.get("/api/monitors", headers=headers)
    body = r.json()
    assert body["success"] is True
    assert body["pagination"]["total"] == 1
    assert body["data"][0]["id"] == mid

    # get detail (includes metrics object)
    r = await client.get(f"/api/monitors/{mid}", headers=headers)
    assert r.status_code == 200
    assert "metrics" in r.json()["data"]

    # update
    r = await client.put(f"/api/monitors/{mid}", json={"name": "Payments v2", "interval": 600}, headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["name"] == "Payments v2"
    assert r.json()["data"]["interval"] == 600

    # pause / resume
    r = await client.post(f"/api/monitors/{mid}/pause", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["active"] is False
    assert r.json()["data"]["status"] == "paused"

    r = await client.post(f"/api/monitors/{mid}/resume", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["active"] is True

    # delete
    r = await client.delete(f"/api/monitors/{mid}", headers=headers)
    assert r.status_code == 200
    assert r.json()["data"] is None
    r = await client.get(f"/api/monitors/{mid}", headers=headers)
    assert r.status_code == 404
    assert r.json()["error_code"] == "MONITOR_NOT_FOUND"


async def test_monitor_validation_errors(client, demo_server):
    headers = await auth_headers(client, email="val@example.com")
    global MONITOR_URL
    MONITOR_URL = f"{demo_server}/demo/health"

    r = await client.post("/api/monitors", json=_payload(interval=999), headers=headers)
    assert r.status_code == 422
    assert r.json()["error_code"] == "VALIDATION_ERROR"

    r = await client.post("/api/monitors", json=_payload(timeout=500), headers=headers)
    assert r.status_code == 422

    r = await client.post("/api/monitors", json=_payload(method="FETCH"), headers=headers)
    assert r.status_code == 422

    # body on GET is rejected
    r = await client.post("/api/monitors", json=_payload(body={"a": 1}), headers=headers)
    assert r.status_code == 422


async def test_monitor_ssrf_blocked_non_http(client, demo_server):
    headers = await auth_headers(client, email="ssrf@example.com")
    global MONITOR_URL
    MONITOR_URL = f"{demo_server}/demo/health"
    r = await client.post("/api/monitors", json=_payload(url="ftp://example.com/x"), headers=headers)
    assert r.status_code == 400
    assert r.json()["error_code"] == "SSRF_BLOCKED"

    r = await client.post("/api/monitors", json=_payload(url="http://169.254.169.254/latest"), headers=headers)
    assert r.status_code == 400
    assert r.json()["error_code"] == "SSRF_BLOCKED"


async def test_monitor_not_found_and_bad_id(client):
    headers = await auth_headers(client, email="nf@example.com")
    r = await client.get("/api/monitors/000000000000000000000000", headers=headers)
    assert r.status_code == 404
    assert r.json()["error_code"] == "MONITOR_NOT_FOUND"

    r = await client.get("/api/monitors/not-an-id", headers=headers)
    assert r.status_code == 404


async def test_user_isolation_on_monitors(client, demo_server):
    headers_a = await auth_headers(client, email="a@example.com")
    headers_b = await auth_headers(client, email="b@example.com")

    monitor = await _create(client, headers_a, demo_server)
    mid = monitor["id"]

    # B cannot see A's monitor in list
    r = await client.get("/api/monitors", headers=headers_b)
    assert r.json()["pagination"]["total"] == 0

    # B gets 403 on direct access
    for method, url in [
        ("get", f"/api/monitors/{mid}"),
        ("put", f"/api/monitors/{mid}"),
        ("delete", f"/api/monitors/{mid}"),
        ("post", f"/api/monitors/{mid}/test"),
        ("post", f"/api/monitors/{mid}/pause"),
        ("get", f"/api/monitors/{mid}/checks"),
        ("get", f"/api/monitors/{mid}/metrics"),
    ]:
        kwargs = {"headers": headers_b}
        if method == "put":
            kwargs["json"] = {}
        r = await getattr(client, method)(url, **kwargs)
        assert r.status_code == 403, (method, url, r.text)
        assert r.json()["error_code"] == "FORBIDDEN"

    # A still has full access
    r = await client.get(f"/api/monitors/{mid}", headers=headers_a)
    assert r.status_code == 200


async def test_list_filters_and_pagination(client, demo_server):
    headers = await auth_headers(client, email="filter@example.com")
    base = demo_server
    await _create(client, headers, base, name="Alpha API", url=f"{base}/demo/health", method="GET")
    await _create(client, headers, base, name="Beta API", url=f"{base}/demo/echo", method="POST",
                  body={"x": 1})

    r = await client.get("/api/monitors?search=alpha", headers=headers)
    assert r.json()["pagination"]["total"] == 1

    r = await client.get("/api/monitors?method=POST", headers=headers)
    assert r.json()["pagination"]["total"] == 1
    assert r.json()["data"][0]["name"] == "Beta API"

    r = await client.get("/api/monitors?page=2&page_size=1", headers=headers)
    body = r.json()
    assert body["pagination"]["page"] == 2
    assert body["pagination"]["pages"] == 2
    assert len(body["data"]) == 1
