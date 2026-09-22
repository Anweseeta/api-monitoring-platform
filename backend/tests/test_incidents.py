"""Incident tests: dedup, auto-create/auto-resolve pipeline, escalation,
manual CRUD, list summary, and cross-user isolation."""
from datetime import timedelta

from bson import ObjectId

from app.monitoring.engine import check_monitor
from app.services import incident_service
from app.utils.time import utcnow
from tests.conftest import auth_headers


async def _create_monitor(client, headers, base, url_path, **overrides):
    payload = {
        "name": "Incident API",
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


async def test_incident_dedup_and_auto_resolve(client, demo_server, clean_db):
    headers = await auth_headers(client, email="inc@example.com")
    # fast thresholds so the pipeline triggers on manual checks
    r = await client.put("/api/settings", json={"failure_threshold": 2, "recovery_threshold": 2},
                         headers=headers)
    assert r.status_code == 200

    monitor = await _create_monitor(client, headers, demo_server, "/demo/error")
    mid = monitor["id"]

    # 1st failure: no incident yet (below threshold)
    await check_monitor(mid, clean_db)
    assert await clean_db.incidents.count_documents({}) == 0

    # 2nd failure: incident auto-created
    await check_monitor(mid, clean_db)
    incidents = await clean_db.incidents.find({}).to_list(length=10)
    assert len(incidents) == 1
    assert incidents[0]["status"] == "open"
    assert incidents[0]["severity"] == "high"
    assert incidents[0]["created_by"] == "system"

    # more failures: still exactly one open incident (dedup)
    await check_monitor(mid, clean_db)
    await check_monitor(mid, clean_db)
    assert await clean_db.incidents.count_documents({"status": {"$ne": "resolved"}}) == 1

    # events were recorded
    events = await clean_db.incident_events.find({"incident_id": incidents[0]["_id"]}).to_list(length=10)
    assert any(e["event_type"] == "auto_created" for e in events)

    # monitor is down
    doc = await clean_db.apis.find_one({"_id": ObjectId(mid)})
    assert doc["status"] == "down"

    # point the monitor at the healthy endpoint -> recovery
    r = await client.put(f"/api/monitors/{mid}", json={"url": f"{demo_server}/demo/health"},
                         headers=headers)
    assert r.status_code == 200

    await check_monitor(mid, clean_db)  # 1st success: not yet resolved
    assert await clean_db.incidents.count_documents({"status": {"$ne": "resolved"}}) == 1
    await check_monitor(mid, clean_db)  # 2nd success: auto-resolved
    resolved = await clean_db.incidents.find_one({"_id": incidents[0]["_id"]})
    assert resolved["status"] == "resolved"
    assert resolved["resolved_at"] is not None
    assert resolved["duration_seconds"] is not None

    events = await clean_db.incident_events.find({"incident_id": incidents[0]["_id"]}).to_list(length=10)
    assert any(e["event_type"] == "auto_resolved" for e in events)

    doc = await clean_db.apis.find_one({"_id": ObjectId(mid)})
    assert doc["status"] == "healthy"


async def test_escalation_high_to_critical(clean_db):
    from app.core.config import get_settings
    threshold = get_settings().incident_escalation_minutes
    old = utcnow() - timedelta(minutes=threshold + 1)
    incident = {
        "api_id": ObjectId(), "user_id": ObjectId(), "title": "t", "description": "",
        "status": "open", "severity": "high", "started_at": old, "detected_at": old,
        "resolved_at": None, "duration_seconds": None, "root_cause": "",
        "resolution_notes": "", "created_by": "system", "created_at": old, "updated_at": old,
    }
    incident["_id"] = (await clean_db.incidents.insert_one(incident)).inserted_id
    escalated = await incident_service.maybe_escalate(clean_db, incident)
    assert escalated is not None
    assert escalated["severity"] == "critical"
    events = await clean_db.incident_events.find({"incident_id": incident["_id"]}).to_list(length=5)
    assert any(e["event_type"] == "escalated" for e in events)

    # a fresh incident is NOT escalated (distinct API: only one open incident per API)
    fresh = dict(incident)
    del fresh["_id"]
    now = utcnow()
    fresh.update({"api_id": ObjectId(), "started_at": now, "detected_at": now, "created_at": now, "updated_at": now,
                  "severity": "high"})
    fresh["_id"] = (await clean_db.incidents.insert_one(fresh)).inserted_id
    assert await incident_service.maybe_escalate(clean_db, fresh) is None


async def test_manual_incident_crud(client, demo_server):
    headers = await auth_headers(client, email="manual@example.com")
    monitor = await _create_monitor(client, headers, demo_server, "/demo/health")
    mid = monitor["id"]

    # create
    r = await client.post("/api/incidents", json={
        "api_id": mid, "title": "Manual outage", "description": "Reported by user", "severity": "medium",
    }, headers=headers)
    assert r.status_code == 201
    incident = r.json()["data"]
    assert incident["status"] == "open"
    assert incident["created_by"] == "user"
    iid = incident["id"]

    # detail: incident + api + events
    r = await client.get(f"/api/incidents/{iid}", headers=headers)
    assert r.status_code == 200
    data = r.json()["data"]
    assert data["incident"]["id"] == iid
    assert data["api"]["id"] == mid
    assert isinstance(data["events"], list)

    # update severity + resolve via PUT (stamps resolved_at)
    r = await client.put(f"/api/incidents/{iid}", json={"severity": "critical", "status": "resolved",
                                                        "resolution_notes": "fixed"},
                         headers=headers)
    assert r.status_code == 200
    updated = r.json()["data"]
    assert updated["status"] == "resolved"
    assert updated["resolved_at"] is not None

    # resolve endpoint on an open incident
    r = await client.post("/api/incidents", json={"api_id": mid, "title": "Second"}, headers=headers)
    iid2 = r.json()["data"]["id"]
    r = await client.post(f"/api/incidents/{iid2}/resolve", json={"resolution_notes": "all good"},
                          headers=headers)
    assert r.status_code == 200
    assert r.json()["data"]["status"] == "resolved"
    assert r.json()["data"]["resolution_notes"] == "all good"

    # list carries the summary
    r = await client.get("/api/incidents", headers=headers)
    body = r.json()
    assert body["success"] is True
    assert body["summary"]["total"] == 2
    assert body["summary"]["resolved"] == 2
    assert body["pagination"]["total"] == 2

    # delete
    r = await client.delete(f"/api/incidents/{iid2}", headers=headers)
    assert r.status_code == 200
    r = await client.get(f"/api/incidents/{iid2}", headers=headers)
    assert r.status_code == 404
    assert r.json()["error_code"] == "INCIDENT_NOT_FOUND"


async def test_incident_create_with_unknown_api(client):
    headers = await auth_headers(client, email="unknownapi@example.com")
    r = await client.post("/api/incidents", json={
        "api_id": "000000000000000000000000", "title": "Nope",
    }, headers=headers)
    assert r.status_code == 404
    assert r.json()["error_code"] == "API_NOT_FOUND"


async def test_incident_user_isolation(client, demo_server):
    headers_a = await auth_headers(client, email="ia@example.com")
    headers_b = await auth_headers(client, email="ib@example.com")
    monitor = await _create_monitor(client, headers_a, demo_server, "/demo/health")
    r = await client.post("/api/incidents", json={"api_id": monitor["id"], "title": "A's incident"},
                          headers=headers_a)
    iid = r.json()["data"]["id"]

    r = await client.get(f"/api/incidents/{iid}", headers=headers_b)
    assert r.status_code == 403
    assert r.json()["error_code"] == "FORBIDDEN"

    r = await client.get("/api/incidents", headers=headers_b)
    assert r.json()["pagination"]["total"] == 0

    r = await client.post("/api/incidents", json={"api_id": monitor["id"], "title": "hijack"},
                          headers=headers_b)
    assert r.status_code == 403


async def test_ensure_open_incident_survives_lost_race(clean_db):
    """If two check runs race to create an incident, the loser must return
    the existing open incident instead of raising DuplicateKeyError
    (the partial unique index enforces one open incident per API)."""
    api_id, user_id = ObjectId(), ObjectId()
    api_doc = {"_id": api_id, "user_id": user_id, "name": "Race API"}

    first, created = await incident_service.ensure_open_incident(clean_db, api_doc, 3)
    assert created is True

    # Simulate the loser: its get_open_incident ran before the winner's
    # insert, so create_incident hits the unique index. Patch the read to
    # force the race path deterministically.
    orig_get_open = incident_service.get_open_incident

    async def _miss_then_hit(db, aid, _calls={"n": 0}):
        _calls["n"] += 1
        if _calls["n"] == 1:
            return None  # the loser's stale read
        return await orig_get_open(db, aid)

    incident_service.get_open_incident = _miss_then_hit
    try:
        second, created2 = await incident_service.ensure_open_incident(clean_db, api_doc, 4)
    finally:
        incident_service.get_open_incident = orig_get_open

    assert created2 is False
    assert str(second["_id"]) == str(first["_id"])
    count = await clean_db.incidents.count_documents({"api_id": api_id, "status": "open"})
    assert count == 1
