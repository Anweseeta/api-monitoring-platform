"""Manual /test checks against the real demo endpoints + metrics/uptime reads."""
from bson import ObjectId

from tests.conftest import auth_headers


async def _create_monitor(client, headers, base, url_path, **overrides):
    payload = {
        "name": "Check API",
        "url": f"{base}{url_path}",
        "method": "GET",
        "interval": 60,
        "timeout": 10,
        "expected_status": 200,
    }
    payload.update(overrides)
    r = await client.post("/api/monitors", json=payload, headers=headers)
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def test_manual_test_against_demo_health(client, demo_server, clean_db):
    headers = await auth_headers(client, email="check@example.com")
    monitor = await _create_monitor(client, headers, demo_server, "/demo/health")

    r = await client.post(f"/api/monitors/{monitor['id']}/test", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    result = body["data"]
    assert result["success"] is True
    assert result["status_code"] == 200
    assert result["timed_out"] is False
    assert result["error"] is None
    assert result["response_time_ms"] >= 0

    # persisted as a check
    count = await clean_db.checks.count_documents({"api_id": ObjectId(monitor["id"])})
    assert count == 1

    # monitor counters updated
    r = await client.get(f"/api/monitors/{monitor['id']}", headers=headers)
    updated = r.json()["data"]
    assert updated["consecutive_successes"] == 1
    assert updated["last_checked_at"] is not None

    # checks listing + metrics + uptime
    r = await client.get(f"/api/monitors/{monitor['id']}/checks", headers=headers)
    assert r.json()["pagination"]["total"] == 1

    r = await client.get(f"/api/monitors/{monitor['id']}/metrics?period=24h", headers=headers)
    metrics = r.json()["data"]
    assert metrics["total_checks"] == 1
    assert metrics["successful_checks"] == 1
    assert metrics["uptime_percent"] == 100.0

    r = await client.get(f"/api/monitors/{monitor['id']}/uptime?period=24h", headers=headers)
    assert r.json()["data"]["uptime_percent"] == 100.0


async def test_manual_test_against_demo_error_records_failure(client, demo_server, clean_db):
    headers = await auth_headers(client, email="checkfail@example.com")
    monitor = await _create_monitor(client, headers, demo_server, "/demo/error")

    r = await client.post(f"/api/monitors/{monitor['id']}/test", headers=headers)
    assert r.status_code == 200
    result = r.json()["data"]
    assert result["success"] is False
    assert result["status_code"] == 500
    assert "Unexpected status 500" in (result["error"] or "")

    r = await client.get(f"/api/monitors/{monitor['id']}", headers=headers)
    assert r.json()["data"]["consecutive_failures"] == 1


async def test_manual_test_ssrf_blocked_for_metadata_ip(client, demo_server):
    headers = await auth_headers(client, email="checkssrf@example.com")
    # create via demo URL, then retarget at the metadata IP
    monitor = await _create_monitor(client, headers, demo_server, "/demo/health")
    r = await client.put(f"/api/monitors/{monitor['id']}",
                         json={"url": "http://169.254.169.254/latest/meta-data"},
                         headers=headers)
    assert r.status_code == 400
    assert r.json()["error_code"] == "SSRF_BLOCKED"


async def test_demo_slow_marks_degraded(client, demo_server):
    """Latency above degraded_latency_ms -> status degraded (still success)."""
    headers = await auth_headers(client, email="slow@example.com")
    monitor = await _create_monitor(client, headers, demo_server, "/demo/slow", timeout=15)
    r = await client.post(f"/api/monitors/{monitor['id']}/test", headers=headers)
    assert r.status_code == 200
    result = r.json()["data"]
    assert result["success"] is True
    assert result["response_time_ms"] >= 2500

    r = await client.get(f"/api/monitors/{monitor['id']}", headers=headers)
    assert r.json()["data"]["status"] == "degraded"
