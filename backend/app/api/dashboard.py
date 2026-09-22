"""Dashboard routes: summary and time-series for uptime, latency, incidents."""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.database.mongo import get_db
from app.models import serialize_activity, serialize_incident
from app.schemas.common import error_response, success_response
from app.services import metrics_service
from app.services.incident_service import OPEN_STATUSES
from app.utils.time import period_start

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


def _validate_period(period: str) -> None:
    if period not in ("24h", "7d", "30d"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("period must be one of 24h, 7d, 30d", "VALIDATION_ERROR"),
        )


@router.get("/summary")
async def summary(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    user_id = user["_id"]
    monitors = await db.apis.find({"user_id": user_id}).to_list(length=10000)

    counts = {"healthy": 0, "degraded": 0, "down": 0, "paused": 0}
    for m in monitors:
        st = m.get("status", "healthy")
        if st in counts:
            counts[st] += 1

    since = period_start("24h")
    pipeline = [
        {"$match": {"user_id": user_id, "timestamp": {"$gte": since}}},
        {"$group": {"_id": None, "total": {"$sum": 1},
                    "ok": {"$sum": {"$cond": ["$success", 1, 0]}},
                    "lat_sum": {"$sum": {"$ifNull": ["$response_time_ms", 0]}},
                    "lat_n": {"$sum": {"$cond": [{"$ifNull": ["$response_time_ms", False]}, 1, 0]}}}},
    ]
    agg = await db.checks.aggregate(pipeline).to_list(length=1)
    row = agg[0] if agg else {"total": 0, "ok": 0, "lat_sum": 0, "lat_n": 0}
    total_checks = row.get("total", 0) or 0
    overall_uptime = round(row.get("ok", 0) / total_checks * 100.0, 2) if total_checks else 100.0
    lat_n = row.get("lat_n", 0) or 0
    avg_latency = round(row.get("lat_sum", 0) / lat_n, 2) if lat_n else None

    open_incidents = await db.incidents.count_documents(
        {"user_id": user_id, "status": {"$in": list(OPEN_STATUSES)}}
    )
    recent_incidents = await db.incidents.find({"user_id": user_id}).sort(
        "created_at", -1
    ).limit(5).to_list(length=5)
    recent_activity = await db.activity_logs.find({"user_id": user_id}).sort(
        "timestamp", -1
    ).limit(8).to_list(length=8)

    return success_response({
        "total_apis": len(monitors),
        "healthy_apis": counts["healthy"],
        "degraded_apis": counts["degraded"],
        "down_apis": counts["down"],
        "paused_apis": counts["paused"],
        "avg_response_time_ms": avg_latency,
        "overall_uptime_24h": overall_uptime,
        "open_incidents": open_incidents,
        "recent_incidents": [serialize_incident(i) for i in recent_incidents],
        "recent_activity": [serialize_activity(a) for a in recent_activity],
        "health_overview": counts,
    })


@router.get("/uptime")
async def uptime(
    period: str = Query(default="24h"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _validate_period(period)
    points = await metrics_service.dashboard_uptime_points(db, user["_id"], period)
    return success_response({"points": points})


@router.get("/latency")
async def latency(
    period: str = Query(default="24h"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _validate_period(period)
    points = await metrics_service.dashboard_latency_points(db, user["_id"], period)
    return success_response({"points": points})


@router.get("/incidents")
async def incidents(
    period: str = Query(default="24h"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _validate_period(period)
    points = await metrics_service.dashboard_incident_points(db, user["_id"], period)
    return success_response({"points": points})
