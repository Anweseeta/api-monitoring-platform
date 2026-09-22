"""Incident routes: list (with summary), create, detail, update, delete, resolve."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.database.mongo import get_db
from app.models import serialize_incident, serialize_incident_event, serialize_monitor
from app.schemas.common import error_response, success_response
from app.schemas.incident import IncidentCreate, IncidentResolve, IncidentUpdate
from app.services import incident_service, monitor_service
from app.services.activity_service import log_activity
from app.services.notification_service import dispatch_webhooks, webhook_payload
from app.utils.pagination import pagination_params
from app.utils.time import utcnow

router = APIRouter(prefix="/api/incidents", tags=["incidents"])

VALID_STATUSES = ("open", "investigating", "identified", "monitoring", "resolved")
VALID_SEVERITIES = ("low", "medium", "high", "critical")


async def get_owned_incident(db: AsyncIOMotorDatabase, user_id, incident_id: str) -> dict:
    from bson import ObjectId

    if not ObjectId.is_valid(incident_id):
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=error_response("Incident not found", "INCIDENT_NOT_FOUND"),
        )
    doc = await db.incidents.find_one({"_id": ObjectId(incident_id)})
    if doc is None:
        raise HTTPException(
            status_code=http_status.HTTP_404_NOT_FOUND,
            detail=error_response("Incident not found", "INCIDENT_NOT_FOUND"),
        )
    if doc.get("user_id") != user_id:
        raise HTTPException(
            status_code=http_status.HTTP_403_FORBIDDEN,
            detail=error_response("Access denied", "FORBIDDEN"),
        )
    return doc


@router.get("")
async def list_incidents(
    status: str = Query(default=""),
    severity: str = Query(default=""),
    api_id: str = Query(default=""),
    from_: str = Query(default="", alias="from"),
    to: str = Query(default=""),
    search: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    from bson import ObjectId
    from datetime import datetime, timezone

    filt: dict = {"user_id": user["_id"]}
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                                detail=error_response("Invalid status", "VALIDATION_ERROR"))
        filt["status"] = status
    if severity:
        if severity not in VALID_SEVERITIES:
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                                detail=error_response("Invalid severity", "VALIDATION_ERROR"))
        filt["severity"] = severity
    if api_id:
        if not ObjectId.is_valid(api_id):
            raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                                detail=error_response("Invalid api_id", "VALIDATION_ERROR"))
        filt["api_id"] = ObjectId(api_id)
    if search:
        filt["title"] = {"$regex": search, "$options": "i"}
    for key, value in (("from", from_), ("to", to)):
        if value:
            try:
                text = value.strip()
                if text.endswith("Z"):
                    text = text[:-1] + "+00:00"
                dt = datetime.fromisoformat(text)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
            except ValueError:
                raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST,
                                    detail=error_response(f"Invalid {key} timestamp", "VALIDATION_ERROR"))
            filt.setdefault("created_at", {})["$gte" if key == "from" else "$lte"] = dt

    params = pagination_params(page, page_size)
    cursor = db.incidents.find(filt).sort("created_at", -1).skip(
        (params["page"] - 1) * params["page_size"]
    ).limit(params["page_size"])
    docs = await cursor.to_list(length=params["page_size"])
    total = await db.incidents.count_documents(filt)
    pages = (total + params["page_size"] - 1) // params["page_size"] if total else 0

    # Summary over the user's incidents (unfiltered by query, per contract).
    base = {"user_id": user["_id"]}
    all_docs = await db.incidents.find(base, {"status": 1, "severity": 1, "duration_seconds": 1}).to_list(length=100000)
    open_count = sum(1 for d in all_docs if d.get("status") != "resolved")
    resolved_docs = [d for d in all_docs if d.get("status") == "resolved"]
    durations = [d["duration_seconds"] for d in resolved_docs if d.get("duration_seconds") is not None]
    summary = {
        "total": len(all_docs),
        "open": open_count,
        "resolved": len(resolved_docs),
        "critical": sum(1 for d in all_docs if d.get("severity") == "critical" and d.get("status") != "resolved"),
        "avg_resolution_seconds": round(sum(durations) / len(durations), 2) if durations else None,
    }

    api_ids = list({d["api_id"] for d in docs})
    apis = {a["_id"]: a async for a in db.apis.find({"_id": {"$in": api_ids}})}
    items = [incident_service.serialize_with_api(d, apis.get(d["api_id"])) for d in docs]
    payload = success_response(
        items,
        {"page": params["page"], "page_size": params["page_size"], "total": total, "pages": pages},
    )
    payload["summary"] = summary
    return payload


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_incident(
    payload: IncidentCreate,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    try:
        monitor = await monitor_service.get_owned_monitor(db, user["_id"], payload.api_id)
    except HTTPException as exc:
        if exc.status_code == http_status.HTTP_404_NOT_FOUND:
            raise HTTPException(
                status_code=http_status.HTTP_404_NOT_FOUND,
                detail=error_response("API not found", "API_NOT_FOUND"),
            ) from exc
        raise
    incident = await incident_service.create_incident(
        db,
        api_doc=monitor,
        title=payload.title,
        description=payload.description,
        severity=payload.severity,
        created_by="user",
        event_type="created",
    )
    await log_activity(db, user["_id"], "incident.created", "incident",
                       incident["_id"], incident["title"], request)
    return success_response(serialize_incident(incident))


@router.get("/{incident_id}")
async def get_incident(
    incident_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    incident = await get_owned_incident(db, user["_id"], incident_id)
    api_doc = await db.apis.find_one({"_id": incident["api_id"]})
    events = await db.incident_events.find({"incident_id": incident["_id"]}).sort("timestamp", 1).to_list(length=1000)
    return success_response({
        "incident": serialize_incident(incident),
        "api": serialize_monitor(api_doc) if api_doc else None,
        "events": [serialize_incident_event(e) for e in events],
    })


@router.put("/{incident_id}")
async def update_incident(
    incident_id: str,
    payload: IncidentUpdate,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    incident = await get_owned_incident(db, user["_id"], incident_id)
    patch: dict = {}
    if payload.severity is not None:
        patch["severity"] = payload.severity
    if payload.root_cause is not None:
        patch["root_cause"] = payload.root_cause
    if payload.resolution_notes is not None:
        patch["resolution_notes"] = payload.resolution_notes
    resolving = payload.status == "resolved" and incident.get("status") != "resolved"
    if payload.status is not None:
        patch["status"] = payload.status
    if resolving:
        now = utcnow()
        started = incident.get("started_at") or now
        patch["resolved_at"] = now
        patch["duration_seconds"] = int((now - started).total_seconds())
    if patch:
        patch["updated_at"] = utcnow()
        await db.incidents.update_one({"_id": incident["_id"]}, {"$set": patch})
        if resolving:
            await incident_service.add_event(db, incident["_id"], "resolved",
                                             payload.resolution_notes or "Incident resolved")
            api_doc = await db.apis.find_one({"_id": incident["api_id"]})
            if api_doc is not None:
                await dispatch_webhooks(
                    db, user["_id"], "incident.resolved",
                    webhook_payload(event="incident.resolved", api_name=api_doc.get("name", ""),
                                    api_id=api_doc["_id"], severity=incident.get("severity", "medium"),
                                    status="resolved", incident_id=incident["_id"]),
                )
        else:
            await incident_service.add_event(db, incident["_id"], "updated", "Incident updated")
        await log_activity(db, user["_id"],
                           "incident.resolved" if resolving else "incident.updated",
                           "incident", incident["_id"], incident["title"], request)
    updated = await db.incidents.find_one({"_id": incident["_id"]})
    return success_response(serialize_incident(updated))


@router.delete("/{incident_id}")
async def delete_incident(
    incident_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    incident = await get_owned_incident(db, user["_id"], incident_id)
    await db.incidents.delete_one({"_id": incident["_id"]})
    await db.incident_events.delete_many({"incident_id": incident["_id"]})
    await log_activity(db, user["_id"], "incident.updated", "incident",
                       incident["_id"], incident.get("title", ""), request)
    return success_response(None)


@router.post("/{incident_id}/resolve")
async def resolve_incident(
    incident_id: str,
    payload: IncidentResolve,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    incident = await get_owned_incident(db, user["_id"], incident_id)
    resolved = await incident_service.resolve_incident(db, incident, payload.resolution_notes)
    await log_activity(db, user["_id"], "incident.resolved", "incident",
                       resolved["_id"], resolved["title"], request)
    return success_response(serialize_incident(resolved))
