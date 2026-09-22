"""Fast end-to-end acceptance: fail -> incident -> recover -> resolve.

Drives the real HTTP API + the real monitoring engine check function,
so this exercises the full acceptance workflow without waiting for the
wall-clock scheduler.
"""
import asyncio
import sys
import time
import uuid

sys.path.insert(0, "/home/hatch/workspace/api-monitoring-platform/backend")

import httpx

BASE = "http://127.0.0.1:8000"
email = f"e2e_{uuid.uuid4().hex[:8]}@example.com"
password = "E2eTest123!"


def log(msg):
    print(f"[E2E] {msg}", flush=True)


async def main():
    async with httpx.AsyncClient(base_url=BASE, timeout=30, trust_env=False) as client:
        # 1. register
        r = await client.post("/api/auth/register", json={
            "name": "E2E Tester", "email": email,
            "password": password, "confirm_password": password,
        })
        assert r.status_code in (200, 201), f"register: {r.status_code} {r.text}"
        token = r.json()["data"]["access_token"]
        log("register OK")
        headers = {"Authorization": f"Bearer {token}"}

        # 2. create a monitor pointing at the failing demo endpoint
        r = await client.post("/api/monitors", headers=headers, json={
            "name": "E2E Failing API",
            "url": "http://127.0.0.1:8000/demo/error",
            "method": "GET",
            "interval": 60,
            "timeout": 10,
            "expected_status": 200,
        })
        assert r.status_code in (200, 201), f"create monitor: {r.status_code} {r.text}"
        monitor_id = r.json()["data"]["id"]
        log(f"monitor created: {monitor_id}")

        # 3. run the real engine check 3x (failure threshold = 3)
        from app.monitoring.engine import check_monitor
        results = [await check_monitor(monitor_id) for _ in range(3)]
        assert all(not c["success"] for c in results), "checks should fail"
        log("3 failing checks recorded")

        # 4. incident auto-created?
        r = await client.get("/api/incidents", headers=headers)
        incidents = r.json()["data"]
        assert len(incidents) == 1, f"expected 1 incident, got {len(incidents)}"
        incident_id = incidents[0]["id"]
        assert incidents[0]["status"] == "open", incidents[0]["status"]
        log(f"incident auto-created: {incident_id} (OPEN)")

        # 5. dedup: more failures must NOT create another incident
        await check_monitor(monitor_id)
        r = await client.get("/api/incidents", headers=headers)
        assert len(r.json()["data"]) == 1, "deduplication failed"
        log("dedup OK: still exactly 1 incident")

        # 6. manual update: set INVESTIGATING + severity
        r = await client.put(f"/api/incidents/{incident_id}", headers=headers, json={
            "status": "investigating", "severity": "high",
            "root_cause": "demo /error endpoint returns 500",
        })
        assert r.status_code == 200, f"update incident: {r.status_code} {r.text}"
        log("incident updated to INVESTIGATING / HIGH")

        # 7. switch monitor to healthy endpoint, 2 successful checks (recovery threshold = 2)
        r = await client.put(f"/api/monitors/{monitor_id}", headers=headers, json={
            "url": "http://127.0.0.1:8000/demo/health",
        })
        assert r.status_code == 200, f"update monitor: {r.status_code} {r.text}"
        results = [await check_monitor(monitor_id) for _ in range(2)]
        assert all(c["success"] for c in results), "checks should succeed"
        log("2 successful checks recorded")

        # 8. incident auto-resolved?
        r = await client.get(f"/api/incidents/{incident_id}", headers=headers)
        payload = r.json()["data"]
        inc = payload["incident"]
        assert inc["status"] == "resolved", f"incident status: {inc['status']}"
        assert inc["resolved_at"], "resolved_at missing"
        assert inc["duration_seconds"] is not None or inc.get("duration"), "duration missing"
        log(f"incident auto-resolved, duration recorded")

        # 9. timeline events present
        events = payload.get("events", [])
        assert len(events) >= 3, f"expected >=3 timeline events, got {len(events)}"
        log(f"timeline OK ({len(events)} events)")

        # 10. metrics: uptime + latency stats
        r = await client.get(f"/api/monitors/{monitor_id}/metrics", headers=headers)
        m = r.json()["data"]
        assert m["total_checks"] >= 6, m
        assert 0 < m["uptime_percent"] < 100, m
        assert m["avg_latency_ms"] is not None and m["p95_latency_ms"] is not None, m
        log(f"metrics OK: uptime={m['uptime_percent']}%, avg={m['avg_latency_ms']}ms, p95={m['p95_latency_ms']}ms")

        # 11. dashboard reflects reality
        r = await client.get("/api/dashboard/summary", headers=headers)
        d = r.json()["data"]
        assert d["total_apis"] >= 1, d
        recent = d.get("recent_incidents", [])
        assert any(i["status"] == "resolved" for i in recent), d
        log(f"dashboard OK: total_apis={d['total_apis']}, open_incidents={d['open_incidents']}")

        # 12. activity log recorded the flow
        r = await client.get("/api/activity", headers=headers, params={"limit": 50})
        actions = [a["action"] for a in r.json()["data"]]
        for expected in ("api.created", "incident.auto_created", "incident.auto_resolved"):
            assert any(expected in a for a in actions), f"missing activity: {expected} in {actions[:10]}"
        log("activity log OK")

        # 13. manual test-now endpoint
        r = await client.post(f"/api/monitors/{monitor_id}/test", headers=headers)
        t = r.json()["data"]
        assert t["success"] is True and t["status_code"] == 200, t
        log("test-now OK")

        # 14. user isolation: another user cannot see this monitor
        email2 = f"e2e2_{uuid.uuid4().hex[:8]}@example.com"
        r = await client.post("/api/auth/register", json={
            "name": "Other", "email": email2,
            "password": password, "confirm_password": password,
        })
        token2 = r.json()["data"]["access_token"]
        r = await client.get(f"/api/monitors/{monitor_id}",
                            headers={"Authorization": f"Bearer {token2}"})
        assert r.status_code in (403, 404), f"isolation broken: {r.status_code}"
        log("user isolation OK")

    log("ALL E2E CHECKS PASSED")


asyncio.run(main())
