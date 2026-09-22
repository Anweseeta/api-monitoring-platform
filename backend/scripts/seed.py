"""Seed script: creates a DEMO ONLY user with sample monitors, synthetic
48h check history, and sample incidents so the dashboard is populated.

DEMO ONLY - the seeded credentials are public knowledge by design:
    email:    demo@example.com
    password: DemoPass123!

Usage (from backend/):
    .venv/bin/python scripts/seed.py

Monitors point at the app's own /demo/* endpoints (BACKEND_PUBLIC_URL env,
default http://localhost:8000), so seed BEFORE starting the server (or
restart it afterwards) so the scheduler picks the monitors up.
"""
import asyncio
import os
import random
import sys
from datetime import timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.database.indexes import ensure_indexes  # noqa: E402
from app.utils.time import utcnow  # noqa: E402

DEMO_EMAIL = "demo@example.com"
DEMO_PASSWORD = "DemoPass123!"
DEMO_NAME = "Demo User"


def _base_url() -> str:
    return os.environ.get("BACKEND_PUBLIC_URL", get_settings().backend_public_url).rstrip("/")


async def main() -> None:
    settings = get_settings()
    client = AsyncIOMotorClient(settings.mongodb_uri)
    db = client[settings.database_name]
    await ensure_indexes(db)

    base = _base_url()
    now = utcnow()

    # --- Demo user (idempotent upsert) -------------------------------------
    await db.users.delete_many({"email": DEMO_EMAIL})
    user_doc = {
        "name": DEMO_NAME,
        "email": DEMO_EMAIL,
        "password_hash": hash_password(DEMO_PASSWORD),
        "created_at": now,
    }
    user_id = (await db.users.insert_one(user_doc)).inserted_id
    # Wipe this user's previous demo data so re-seeds stay clean.
    old_incident_ids = [
        doc["_id"] async for doc in db.incidents.find({"user_id": user_id}, {"_id": 1})
    ]
    await db.apis.delete_many({"user_id": user_id})
    await db.checks.delete_many({"user_id": user_id})
    await db.incidents.delete_many({"user_id": user_id})
    if old_incident_ids:
        await db.incident_events.delete_many({"incident_id": {"$in": old_incident_ids}})
    await db.activity_logs.delete_many({"user_id": user_id})
    await db.webhooks.delete_many({"user_id": user_id})
    await db.settings.delete_many({"user_id": user_id})

    # --- Monitors ------------------------------------------------------------
    monitor_defs = [
        {
            "name": "Demo Health API",
            "url": f"{base}/demo/health",
            "method": "GET",
            "description": "Always-healthy demo endpoint",
            "interval": 60,
            "timeout": 10,
            "expected_status": 200,
            "base_latency_ms": 45,
            "fail_rate": 0.0,
        },
        {
            "name": "Demo Slow API",
            "url": f"{base}/demo/slow",
            "method": "GET",
            "description": "Responds in ~3s (shows degraded latency)",
            "interval": 300,
            "timeout": 10,
            "expected_status": 200,
            "base_latency_ms": 3050,
            "fail_rate": 0.0,
        },
        {
            "name": "Demo Flaky API",
            "url": f"{base}/demo/random",
            "method": "GET",
            "description": "Randomly returns 200 or 500",
            "interval": 60,
            "timeout": 10,
            "expected_status": 200,
            "base_latency_ms": 60,
            "fail_rate": 0.25,
        },
        {
            "name": "Demo Broken API",
            "url": f"{base}/demo/error",
            "method": "GET",
            "description": "Always returns 500 (drives the open incident)",
            "interval": 60,
            "timeout": 10,
            "expected_status": 200,
            "base_latency_ms": 35,
            "fail_rate": 1.0,
        },
    ]

    rng = random.Random(42)
    monitor_ids: dict[str, object] = {}
    for definition in monitor_defs:
        doc = {
            "user_id": user_id,
            "name": definition["name"],
            "url": definition["url"],
            "method": definition["method"],
            "description": definition["description"],
            "interval": definition["interval"],
            "timeout": definition["timeout"],
            "expected_status": definition["expected_status"],
            "headers": {},
            "body": None,
            "active": True,
            "status": "healthy",
            "consecutive_failures": 0,
            "consecutive_successes": 0,
            "last_checked_at": None,
            "created_at": now - timedelta(hours=48),
            "updated_at": now,
        }
        inserted = await db.apis.insert_one(doc)
        monitor_ids[definition["name"]] = inserted.inserted_id

        # --- ~48h of synthetic checks (10-minute spacing) -------------------
        checks = []
        ts = now - timedelta(hours=48)
        step = timedelta(minutes=10)
        consecutive_failures = 0
        while ts <= now:
            failed = rng.random() < definition["fail_rate"]
            latency = definition["base_latency_ms"] + rng.uniform(-12, 25)
            checks.append({
                "api_id": inserted.inserted_id,
                "user_id": user_id,
                "timestamp": ts,
                "status_code": 500 if failed else 200,
                "response_time_ms": round(latency, 2),
                "success": not failed,
                "error": "Unexpected status 500 (expected 200)" if failed else None,
                "timed_out": False,
                "response_size_bytes": rng.randint(20, 600),
            })
            consecutive_failures = consecutive_failures + 1 if failed else 0
            ts += step
        if checks:
            await db.checks.insert_many(checks)
        last = checks[-1]
        degraded = last["success"] and last["response_time_ms"] > 1000
        status_value = "down" if consecutive_failures >= 3 else ("degraded" if degraded else "healthy")
        await db.apis.update_one(
            {"_id": inserted.inserted_id},
            {"$set": {
                "consecutive_failures": consecutive_failures,
                "consecutive_successes": 0 if consecutive_failures else 3,
                "last_checked_at": last["timestamp"],
                "status": status_value,
            }},
        )

    # --- Sample incidents ----------------------------------------------------
    flaky_id = monitor_ids["Demo Flaky API"]
    broken_id = monitor_ids["Demo Broken API"]

    # 1) Resolved incident on the flaky API (30h ago -> 28h ago).
    started = now - timedelta(hours=30)
    resolved_at = now - timedelta(hours=28)
    resolved_doc = {
        "api_id": flaky_id,
        "user_id": user_id,
        "title": "Demo Flaky API is down",
        "description": "Consecutive failures detected (4 in a row).",
        "status": "resolved",
        "severity": "high",
        "started_at": started,
        "detected_at": started,
        "resolved_at": resolved_at,
        "duration_seconds": int((resolved_at - started).total_seconds()),
        "root_cause": "Upstream demo endpoint returned intermittent 500s.",
        "resolution_notes": "Endpoint recovered on its own; auto-resolved after 2 successful checks.",
        "created_by": "system",
        "created_at": started,
        "updated_at": resolved_at,
    }
    resolved_id = (await db.incidents.insert_one(resolved_doc)).inserted_id
    await db.incident_events.insert_many([
        {"incident_id": resolved_id, "timestamp": started, "event_type": "auto_created",
         "message": "Incident auto_created: Demo Flaky API is down"},
        {"incident_id": resolved_id, "timestamp": resolved_at, "event_type": "auto_resolved",
         "message": "Auto-resolved after 2 consecutive successful checks"},
    ])

    # 2) Open incident on the broken API (started 20 min ago -> the live
    #    engine will escalate it to critical after 15 min of downtime).
    open_started = now - timedelta(minutes=20)
    open_doc = {
        "api_id": broken_id,
        "user_id": user_id,
        "title": "Demo Broken API is down",
        "description": "Consecutive failures detected (5 in a row).",
        "status": "open",
        "severity": "high",
        "started_at": open_started,
        "detected_at": open_started,
        "resolved_at": None,
        "duration_seconds": None,
        "root_cause": "",
        "resolution_notes": "",
        "created_by": "system",
        "created_at": open_started,
        "updated_at": open_started,
    }
    open_id = (await db.incidents.insert_one(open_doc)).inserted_id
    await db.incident_events.insert_one({
        "incident_id": open_id, "timestamp": open_started, "event_type": "auto_created",
        "message": "Incident auto_created: Demo Broken API is down",
    })
    # Keep the monitor doc consistent with its open incident (dedup works).
    await db.apis.update_one(
        {"_id": broken_id},
        {"$set": {"status": "down", "consecutive_failures": 5, "consecutive_successes": 0,
                  "last_checked_at": open_started, "updated_at": now}},
    )

    # --- Default settings + a couple of activity entries ----------------------
    await db.settings.insert_one({
        "user_id": user_id,
        "default_timeout": 10,
        "default_interval": 300,
        "failure_threshold": 3,
        "recovery_threshold": 2,
        "degraded_latency_ms": 1000,
        "results_retention_days": 30,
        "notifications": {"email_enabled": False, "webhook_enabled": True},
        "updated_at": now,
    })
    await db.activity_logs.insert_many([
        {"user_id": user_id, "action": "user.registered", "resource_type": "user",
         "resource_id": user_id, "resource_name": DEMO_NAME,
         "timestamp": now - timedelta(hours=48), "ip": "127.0.0.1", "user_agent": "seed"},
        {"user_id": user_id, "action": "incident.auto_created", "resource_type": "incident",
         "resource_id": open_id, "resource_name": "Demo Broken API is down",
         "timestamp": open_started, "ip": "", "user_agent": "seed"},
    ])

    print(f"Seeded DEMO ONLY user {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print("  monitors: 4, incidents: 2 (1 open, 1 resolved), checks: ~48h synthetic")
    print(f"  demo endpoints base: {base}")
    client.close()


if __name__ == "__main__":
    asyncio.run(main())
