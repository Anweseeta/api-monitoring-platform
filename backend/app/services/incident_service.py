"""Incident lifecycle: dedup (one open incident per api), auto-create,
auto-resolve, and escalation from high -> critical after sustained downtime.
"""
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError

from app.core.config import get_settings
from app.models import serialize_incident
from app.services import notification_service
from app.utils.time import utcnow

OPEN_STATUSES = ("open", "investigating", "identified", "monitoring")


async def add_event(
    db: AsyncIOMotorDatabase,
    incident_id: ObjectId,
    event_type: str,
    message: str,
) -> dict:
    doc = {
        "incident_id": incident_id,
        "timestamp": utcnow(),
        "event_type": event_type,
        "message": message,
    }
    result = await db.incident_events.insert_one(doc)
    doc["_id"] = result.inserted_id
    return doc


async def get_open_incident(db: AsyncIOMotorDatabase, api_id: ObjectId) -> dict | None:
    """Dedup lookup: the single non-resolved incident for this api, if any."""
    return await db.incidents.find_one(
        {"api_id": api_id, "status": {"$in": list(OPEN_STATUSES)}}
    )


async def create_incident(
    db: AsyncIOMotorDatabase,
    *,
    api_doc: dict,
    title: str,
    description: str = "",
    severity: str = "high",
    created_by: str = "system",
    event_type: str = "created",
) -> dict:
    now = utcnow()
    doc: dict[str, Any] = {
        "api_id": api_doc["_id"],
        "user_id": api_doc["user_id"],
        "title": title,
        "description": description,
        "status": "open",
        "severity": severity,
        "started_at": now,
        "detected_at": now,
        "resolved_at": None,
        "duration_seconds": None,
        "root_cause": "",
        "resolution_notes": "",
        "created_by": created_by,
        "created_at": now,
        "updated_at": now,
    }
    result = await db.incidents.insert_one(doc)
    doc["_id"] = result.inserted_id
    await add_event(db, doc["_id"], event_type, f"Incident {event_type}: {title}")
    await notification_service.dispatch_webhooks(
        db,
        api_doc["user_id"],
        "incident.created",
        notification_service.webhook_payload(
            event="incident.created",
            api_name=api_doc.get("name", ""),
            api_id=api_doc["_id"],
            severity=severity,
            status="open",
            incident_id=doc["_id"],
        ),
    )
    return doc


async def ensure_open_incident(
    db: AsyncIOMotorDatabase, api_doc: dict, failure_count: int
) -> tuple[dict, bool]:
    """Return (incident, created). Creates one when none is open (dedup)."""
    incident = await get_open_incident(db, api_doc["_id"])
    if incident:
        return incident, False
    title = f"{api_doc.get('name', 'API')} is down"
    description = (
        f"Consecutive failures detected ({failure_count} in a row). "
        f"Last check failed at {utcnow().isoformat()}."
    )
    try:
        incident = await create_incident(
            db,
            api_doc=api_doc,
            title=title,
            description=description,
            severity="high",
            created_by="system",
            event_type="auto_created",
        )
    except DuplicateKeyError:
        # Lost a race with another check run (multi-worker / overlapping
        # schedules): the partial unique index on incidents guarantees a
        # single open incident per API, so just re-read the winner.
        incident = await get_open_incident(db, api_doc["_id"])
        return incident, False
    return incident, True


async def maybe_escalate(db: AsyncIOMotorDatabase, incident: dict) -> dict | None:
    """Escalate high -> critical once downtime exceeds the configured minutes."""
    if incident.get("severity") != "high":
        return None
    threshold = get_settings().incident_escalation_minutes
    started = incident.get("started_at")
    if started is None:
        return None
    if (utcnow() - started).total_seconds() < threshold * 60:
        return None
    await db.incidents.update_one(
        {"_id": incident["_id"]},
        {"$set": {"severity": "critical", "updated_at": utcnow()}},
    )
    await add_event(
        db,
        incident["_id"],
        "escalated",
        f"Escalated to critical after {threshold} minutes of downtime",
    )
    incident["severity"] = "critical"
    return incident


async def auto_resolve_incident(
    db: AsyncIOMotorDatabase, incident: dict, api_doc: dict, success_count: int
) -> dict:
    now = utcnow()
    started = incident.get("started_at") or now
    duration = int((now - started).total_seconds())
    await db.incidents.update_one(
        {"_id": incident["_id"]},
        {
            "$set": {
                "status": "resolved",
                "resolved_at": now,
                "duration_seconds": duration,
                "updated_at": now,
            }
        },
    )
    await add_event(
        db,
        incident["_id"],
        "auto_resolved",
        f"Auto-resolved after {success_count} consecutive successful checks",
    )
    await notification_service.dispatch_webhooks(
        db,
        api_doc["user_id"],
        "incident.resolved",
        notification_service.webhook_payload(
            event="incident.resolved",
            api_name=api_doc.get("name", ""),
            api_id=api_doc["_id"],
            severity=incident.get("severity", "medium"),
            status="resolved",
            incident_id=incident["_id"],
        ),
    )
    incident = await db.incidents.find_one({"_id": incident["_id"]})
    return incident


async def resolve_incident(
    db: AsyncIOMotorDatabase, incident: dict, resolution_notes: str = ""
) -> dict:
    now = utcnow()
    started = incident.get("started_at") or now
    duration = int((now - started).total_seconds())
    update: dict[str, Any] = {
        "status": "resolved",
        "resolved_at": now,
        "duration_seconds": duration,
        "updated_at": now,
    }
    if resolution_notes:
        update["resolution_notes"] = resolution_notes
    await db.incidents.update_one({"_id": incident["_id"]}, {"$set": update})
    await add_event(db, incident["_id"], "resolved", resolution_notes or "Incident resolved")
    return await db.incidents.find_one({"_id": incident["_id"]})


def serialize_with_api(incident: dict, api_doc: dict | None) -> dict:
    data = serialize_incident(incident)
    data["api_name"] = api_doc.get("name", "") if api_doc else ""
    return data
