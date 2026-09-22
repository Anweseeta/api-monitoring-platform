"""Monitor CRUD, check recording, status computation and metrics helpers.

User isolation: every read/write filters on user_id.
"""
import asyncio
from datetime import timedelta
from typing import Any

from bson import ObjectId
from fastapi import HTTPException, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.models import serialize_check, serialize_monitor
from app.monitoring.ssrf import SSRFBlocked, check_url_allowed
from app.schemas.common import error_response
from app.services import incident_service
from app.services.activity_service import log_activity
from app.services.settings_service import get_effective_settings
from app.utils.time import utcnow


# ---------------------------------------------------------------------------
# Ownership helpers
# ---------------------------------------------------------------------------

async def get_owned_monitor(
    db: AsyncIOMotorDatabase, user_id: ObjectId, monitor_id: str
) -> dict:
    """Fetch a monitor by id enforcing ownership.

    404 MONITOR_NOT_FOUND when missing, 403 FORBIDDEN when owned by someone else.
    """
    if not ObjectId.is_valid(monitor_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Monitor not found", "MONITOR_NOT_FOUND"),
        )
    doc = await db.apis.find_one({"_id": ObjectId(monitor_id)})
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Monitor not found", "MONITOR_NOT_FOUND"),
        )
    if doc.get("user_id") != user_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("Access denied", "FORBIDDEN"),
        )
    return doc


async def validate_monitor_url(url: str) -> None:
    try:
        # DNS resolution blocks; keep it off the event loop.
        await asyncio.to_thread(check_url_allowed, url)
    except SSRFBlocked as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(str(exc), "SSRF_BLOCKED"),
        ) from exc


# ---------------------------------------------------------------------------
# Status computation
# ---------------------------------------------------------------------------

def compute_status(
    *,
    active: bool,
    consecutive_failures: int,
    failure_threshold: int,
    last_latency_ms: float | None,
    last_success: bool | None,
    degraded_latency_ms: int,
) -> str:
    if not active:
        return "paused"
    if consecutive_failures >= failure_threshold:
        return "down"
    if last_success and last_latency_ms is not None and last_latency_ms > degraded_latency_ms:
        return "degraded"
    return "healthy"


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------

async def create_monitor(
    db: AsyncIOMotorDatabase, user_doc: dict, data: dict, request=None
) -> dict:
    await validate_monitor_url(data["url"])
    now = utcnow()
    doc: dict[str, Any] = {
        "user_id": user_doc["_id"],
        "name": data["name"],
        "url": data["url"],
        "method": data.get("method", "GET"),
        "description": data.get("description", ""),
        "interval": data.get("interval", 300),
        "timeout": data.get("timeout", 10),
        "expected_status": data.get("expected_status", 200),
        "headers": data.get("headers") or {},
        "body": data.get("body"),
        "active": data.get("active", True),
        "status": "paused" if not data.get("active", True) else "healthy",
        "consecutive_failures": 0,
        "consecutive_successes": 0,
        "last_checked_at": None,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.apis.insert_one(doc)
    doc["_id"] = result.inserted_id
    await log_activity(
        db, user_doc["_id"], "api.created", "api", doc["_id"], doc["name"], request
    )
    return doc


async def update_monitor(
    db: AsyncIOMotorDatabase, monitor: dict, user_doc: dict, data: dict, request=None
) -> dict:
    patch = {k: v for k, v in data.items() if v is not None}
    if "url" in patch:
        await validate_monitor_url(patch["url"])
    if not patch:
        return monitor
    patch["updated_at"] = utcnow()
    await db.apis.update_one({"_id": monitor["_id"]}, {"$set": patch})
    updated = await db.apis.find_one({"_id": monitor["_id"]})
    await log_activity(
        db, user_doc["_id"], "api.updated", "api", monitor["_id"], updated["name"], request
    )
    return updated


async def delete_monitor(db: AsyncIOMotorDatabase, monitor: dict, user_doc: dict, request=None) -> None:
    api_id = monitor["_id"]
    await db.apis.delete_one({"_id": api_id})
    await db.checks.delete_many({"api_id": api_id})
    incident_ids = [
        doc["_id"] async for doc in db.incidents.find({"api_id": api_id}, {"_id": 1})
    ]
    if incident_ids:
        await db.incidents.delete_many({"_id": {"$in": incident_ids}})
        await db.incident_events.delete_many({"incident_id": {"$in": incident_ids}})
    await log_activity(
        db, user_doc["_id"], "api.deleted", "api", api_id, monitor.get("name", ""), request
    )


async def set_active(
    db: AsyncIOMotorDatabase, monitor: dict, user_doc: dict, active: bool, request=None
) -> dict:
    new_status = "healthy" if active else "paused"
    await db.apis.update_one(
        {"_id": monitor["_id"]},
        {"$set": {"active": active, "status": new_status, "updated_at": utcnow()}},
    )
    updated = await db.apis.find_one({"_id": monitor["_id"]})
    await log_activity(
        db,
        user_doc["_id"],
        "api.resumed" if active else "api.paused",
        "api",
        monitor["_id"],
        updated["name"],
        request,
    )
    return updated


# ---------------------------------------------------------------------------
# Check recording + incident pipeline
# ---------------------------------------------------------------------------

async def record_check(
    db: AsyncIOMotorDatabase, monitor: dict, result: dict[str, Any]
) -> dict[str, Any]:
    """Persist a check result, update counters/status, run incident pipeline.

    Returns the inserted check document.
    """
    now = utcnow()
    check_doc: dict[str, Any] = {
        "api_id": monitor["_id"],
        "user_id": monitor["user_id"],
        "timestamp": result.get("timestamp") or now,
        "status_code": result.get("status_code"),
        "response_time_ms": result.get("response_time_ms"),
        "success": bool(result.get("success")),
        "error": result.get("error"),
        "timed_out": bool(result.get("timed_out")),
        "response_size_bytes": result.get("response_size_bytes", 0),
    }
    insert_result = await db.checks.insert_one(check_doc)
    check_doc["_id"] = insert_result.inserted_id

    settings = await get_effective_settings(db, monitor["user_id"])
    failure_threshold = settings["failure_threshold"]
    recovery_threshold = settings["recovery_threshold"]
    degraded_latency_ms = settings["degraded_latency_ms"]

    if check_doc["success"]:
        consecutive_failures = 0
        consecutive_successes = monitor.get("consecutive_successes", 0) + 1
    else:
        consecutive_failures = monitor.get("consecutive_failures", 0) + 1
        consecutive_successes = 0

    # Incident pipeline (dedup: one open incident per api).
    open_incident = await incident_service.get_open_incident(db, monitor["_id"])
    if not check_doc["success"] and consecutive_failures >= failure_threshold:
        if open_incident is None:
            open_incident, _ = await incident_service.ensure_open_incident(
                db, monitor, consecutive_failures
            )
            await log_activity(
                db,
                monitor["user_id"],
                "incident.auto_created",
                "incident",
                open_incident["_id"],
                open_incident["title"],
            )
        else:
            escalated = await incident_service.maybe_escalate(db, open_incident)
            if escalated:
                await log_activity(
                    db,
                    monitor["user_id"],
                    "incident.updated",
                    "incident",
                    open_incident["_id"],
                    open_incident["title"],
                )
    elif check_doc["success"] and open_incident is not None:
        if consecutive_successes >= recovery_threshold:
            resolved = await incident_service.auto_resolve_incident(
                db, open_incident, monitor, consecutive_successes
            )
            await log_activity(
                db,
                monitor["user_id"],
                "incident.auto_resolved",
                "incident",
                resolved["_id"],
                resolved["title"],
            )
            open_incident = None

    new_status = compute_status(
        active=monitor.get("active", True),
        consecutive_failures=consecutive_failures,
        failure_threshold=failure_threshold,
        last_latency_ms=check_doc["response_time_ms"],
        last_success=check_doc["success"],
        degraded_latency_ms=degraded_latency_ms,
    )
    await db.apis.update_one(
        {"_id": monitor["_id"]},
        {
            "$set": {
                "consecutive_failures": consecutive_failures,
                "consecutive_successes": consecutive_successes,
                "last_checked_at": check_doc["timestamp"],
                "status": new_status,
                "updated_at": now,
            }
        },
    )
    monitor.update(
        consecutive_failures=consecutive_failures,
        consecutive_successes=consecutive_successes,
        last_checked_at=check_doc["timestamp"],
        status=new_status,
        updated_at=now,
    )
    return check_doc


# ---------------------------------------------------------------------------
# Uptime helpers
# ---------------------------------------------------------------------------

async def uptime_for_monitors(
    db: AsyncIOMotorDatabase, api_ids: list[ObjectId], hours: int = 24
) -> dict[str, float]:
    """Map api_id hex -> uptime percent over the last `hours`."""
    if not api_ids:
        return {}
    since = utcnow() - timedelta(hours=hours)
    pipeline = [
        {"$match": {"api_id": {"$in": api_ids}, "timestamp": {"$gte": since}}},
        {"$group": {"_id": "$api_id", "total": {"$sum": 1}, "ok": {"$sum": {"$cond": ["$success", 1, 0]}}}},
    ]
    result: dict[str, float] = {}
    async for row in db.checks.aggregate(pipeline):
        total = row["total"] or 0
        result[str(row["_id"])] = round((row["ok"] / total * 100.0) if total else 100.0, 2)
    for api_id in api_ids:
        result.setdefault(str(api_id), 100.0)
    return result


async def serialize_monitor_with_uptime(db: AsyncIOMotorDatabase, monitor: dict) -> dict:
    uptimes = await uptime_for_monitors(db, [monitor["_id"]], hours=24)
    return serialize_monitor(monitor, uptime_24h=uptimes.get(str(monitor["_id"]), 100.0))


async def serialize_checks(check_doc: dict) -> dict:
    return serialize_check(check_doc)
