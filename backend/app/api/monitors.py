"""Monitor routes: CRUD, test, pause/resume, checks, metrics, uptime."""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi import status as http_status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.database.mongo import get_db
from app.models import serialize_check, serialize_monitor
from app.monitoring import engine as monitoring_engine
from app.monitoring.ssrf import SSRFBlocked
from app.schemas.common import error_response, success_response
from app.schemas.monitor import MonitorCreate, MonitorUpdate
from app.services import metrics_service, monitor_service
from app.services.activity_service import log_activity
from app.utils.pagination import paginate, pagination_params

router = APIRouter(prefix="/api/monitors", tags=["monitors"])

VALID_STATUSES = ("healthy", "degraded", "down", "paused")
VALID_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD")


@router.get("")
async def list_monitors(
    search: str = Query(default=""),
    status: str = Query(default=""),
    method: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    filt: dict = {"user_id": user["_id"]}
    if search:
        filt["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"url": {"$regex": search, "$options": "i"}},
        ]
    if status:
        if status not in VALID_STATUSES:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=error_response(f"Invalid status filter: {status}", "VALIDATION_ERROR"),
            )
        filt["status"] = status
    if method:
        if method.upper() not in VALID_METHODS:
            raise HTTPException(
                status_code=http_status.HTTP_400_BAD_REQUEST,
                detail=error_response(f"Invalid method filter: {method}", "VALIDATION_ERROR"),
            )
        filt["method"] = method.upper()
    params = pagination_params(page, page_size)
    docs = await db.apis.find(filt).sort("created_at", -1).skip(
        (params["page"] - 1) * params["page_size"]
    ).limit(params["page_size"]).to_list(length=params["page_size"])
    total = await db.apis.count_documents(filt)
    pages = (total + params["page_size"] - 1) // params["page_size"] if total else 0
    uptimes = await monitor_service.uptime_for_monitors(db, [d["_id"] for d in docs], hours=24)
    items = [serialize_monitor(d, uptime_24h=uptimes.get(str(d["_id"]), 100.0)) for d in docs]
    return success_response(items, {"page": params["page"], "page_size": params["page_size"], "total": total, "pages": pages})


@router.post("", status_code=http_status.HTTP_201_CREATED)
async def create_monitor(
    payload: MonitorCreate,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    doc = await monitor_service.create_monitor(db, user, payload.model_dump(), request)
    await monitoring_engine.refresh_monitor_schedule(db, doc["_id"])
    return success_response(await monitor_service.serialize_monitor_with_uptime(db, doc))


@router.get("/{monitor_id}")
async def get_monitor(
    monitor_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    monitor = await monitor_service.get_owned_monitor(db, user["_id"], monitor_id)
    metrics = await metrics_service.compute_metrics(db, monitor["_id"], user["_id"], "24h")
    data = await monitor_service.serialize_monitor_with_uptime(db, monitor)
    data["metrics"] = metrics
    return success_response(data)


@router.put("/{monitor_id}")
async def update_monitor(
    monitor_id: str,
    payload: MonitorUpdate,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    monitor = await monitor_service.get_owned_monitor(db, user["_id"], monitor_id)
    updated = await monitor_service.update_monitor(db, monitor, user, payload.model_dump(), request)
    await monitoring_engine.refresh_monitor_schedule(db, updated["_id"])
    return success_response(await monitor_service.serialize_monitor_with_uptime(db, updated))


@router.delete("/{monitor_id}")
async def delete_monitor(
    monitor_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    monitor = await monitor_service.get_owned_monitor(db, user["_id"], monitor_id)
    await monitoring_engine.unschedule_monitor(monitor["_id"])
    await monitor_service.delete_monitor(db, monitor, user, request)
    return success_response(None)


@router.post("/{monitor_id}/test")
async def test_monitor(
    monitor_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    monitor = await monitor_service.get_owned_monitor(db, user["_id"], monitor_id)
    try:
        check_doc = await monitoring_engine.check_monitor(monitor["_id"], db)
    except SSRFBlocked as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=error_response(str(exc), "SSRF_BLOCKED"),
        ) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=http_status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=error_response("Monitor test failed unexpectedly", "TEST_FAILED"),
        ) from exc
    await log_activity(
        db, user["_id"], "api.tested", "api", monitor["_id"], monitor.get("name", ""), request
    )
    return success_response(serialize_check(check_doc))


@router.post("/{monitor_id}/pause")
async def pause_monitor(
    monitor_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    monitor = await monitor_service.get_owned_monitor(db, user["_id"], monitor_id)
    updated = await monitor_service.set_active(db, monitor, user, False, request)
    await monitoring_engine.refresh_monitor_schedule(db, updated["_id"])
    return success_response(await monitor_service.serialize_monitor_with_uptime(db, updated))


@router.post("/{monitor_id}/resume")
async def resume_monitor(
    monitor_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    monitor = await monitor_service.get_owned_monitor(db, user["_id"], monitor_id)
    updated = await monitor_service.set_active(db, monitor, user, True, request)
    await monitoring_engine.refresh_monitor_schedule(db, updated["_id"])
    return success_response(await monitor_service.serialize_monitor_with_uptime(db, updated))


@router.get("/{monitor_id}/checks")
async def list_checks(
    monitor_id: str,
    since: str = Query(default=""),
    until: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    monitor = await monitor_service.get_owned_monitor(db, user["_id"], monitor_id)
    filt: dict = {"api_id": monitor["_id"], "user_id": user["_id"]}
    ts: dict = {}
    if since:
        ts["$gte"] = _parse_ts(since)
    if until:
        ts["$lte"] = _parse_ts(until)
    if ts:
        filt["timestamp"] = ts
    params = pagination_params(page, page_size)
    items, pagination = await paginate(
        db.checks, filt, params["page"], params["page_size"],
        sort=[("timestamp", -1)], serialize=serialize_check,
    )
    return success_response(items, pagination)


@router.get("/{monitor_id}/metrics")
async def get_metrics(
    monitor_id: str,
    period: str = Query(default="24h"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _validate_period(period)
    monitor = await monitor_service.get_owned_monitor(db, user["_id"], monitor_id)
    data = await metrics_service.compute_metrics(db, monitor["_id"], user["_id"], period)
    return success_response(data)


@router.get("/{monitor_id}/uptime")
async def get_uptime(
    monitor_id: str,
    period: str = Query(default="24h"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    _validate_period(period)
    monitor = await monitor_service.get_owned_monitor(db, user["_id"], monitor_id)
    data = await metrics_service.compute_uptime(db, monitor["_id"], user["_id"], period)
    return success_response(data)


def _validate_period(period: str) -> None:
    if period not in ("24h", "7d", "30d"):
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=error_response("period must be one of 24h, 7d, 30d", "VALIDATION_ERROR"),
        )


def _parse_ts(value: str):
    from datetime import datetime, timezone

    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError as exc:
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail=error_response(f"Invalid timestamp: {value}", "VALIDATION_ERROR"),
        ) from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt
