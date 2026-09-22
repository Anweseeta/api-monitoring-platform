"""Centralized monitoring engine: one AsyncIOScheduler, one interval job per
active monitor (id=f"monitor:{id}"), rescheduled on create/update/pause/resume/delete.

check() performs the async httpx request honoring method/url/headers/body/timeout,
measures latency, records the result, updates consecutive counters, applies the
failure/recovery thresholds (incident dedup + auto-resolve + escalation), and the
scheduler prunes results older than the retention window.
"""
import asyncio
import logging
import time
from datetime import timedelta

import httpx
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.mongo import get_db
from app.monitoring.ssrf import SSRFBlocked, check_url_allowed
from app.services import monitor_service
from app.services.settings_service import get_effective_settings
from app.utils.time import utcnow

logger = logging.getLogger(__name__)

_scheduler: AsyncIOScheduler | None = None
_job_lock = asyncio.Lock()


def get_scheduler() -> AsyncIOScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AsyncIOScheduler()
    return _scheduler


def _job_id(monitor_id: ObjectId | str) -> str:
    return f"monitor:{monitor_id}"


# ---------------------------------------------------------------------------
# Check execution
# ---------------------------------------------------------------------------

async def perform_http_check(monitor: dict) -> dict:
    """Execute the HTTP request for a monitor. Never raises for target errors;
    returns a result dict. Raises SSRFBlocked when the URL is unsafe."""
    await asyncio.to_thread(check_url_allowed, monitor["url"])  # raises SSRFBlocked

    method = monitor.get("method", "GET").upper()
    url = monitor["url"]
    headers = dict(monitor.get("headers") or {})
    body = monitor.get("body")
    timeout = float(monitor.get("timeout", 10))
    expected_status = monitor.get("expected_status", 200)

    request_kwargs: dict = {"method": method, "url": url, "headers": headers, "timeout": timeout}
    if body is not None and method in ("POST", "PUT", "PATCH"):
        if isinstance(body, (dict, list)):
            request_kwargs["json"] = body
            headers.setdefault("Content-Type", "application/json")
        elif isinstance(body, str):
            request_kwargs["content"] = body.encode("utf-8")
        else:
            request_kwargs["json"] = body

    started = time.perf_counter()
    try:
        # trust_env=False: ignore (possibly broken) proxy env vars; monitor
        # checks always go direct.
        async with httpx.AsyncClient(follow_redirects=True, trust_env=False) as client:
            response = await client.request(**request_kwargs)
    except httpx.TimeoutException:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return {
            "status_code": None,
            "response_time_ms": round(elapsed_ms, 2),
            "success": False,
            "error": f"Request timed out after {timeout:g}s",
            "timed_out": True,
            "response_size_bytes": 0,
            "timestamp": utcnow(),
        }
    except httpx.HTTPError as exc:
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        return {
            "status_code": None,
            "response_time_ms": round(elapsed_ms, 2),
            "success": False,
            "error": f"{type(exc).__name__}: {exc}",
            "timed_out": False,
            "response_size_bytes": 0,
            "timestamp": utcnow(),
        }

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    status_code = response.status_code
    return {
        "status_code": status_code,
        "response_time_ms": round(elapsed_ms, 2),
        "success": status_code == expected_status,
        "error": None if status_code == expected_status else f"Unexpected status {status_code} (expected {expected_status})",
        "timed_out": False,
        "response_size_bytes": len(response.content or b""),
        "timestamp": utcnow(),
    }


async def check_monitor(monitor_id: ObjectId | str, db: AsyncIOMotorDatabase | None = None) -> dict:
    """Run one check for a monitor and record it (manual or scheduled)."""
    if db is None:
        db = get_db()
    if isinstance(monitor_id, str):
        monitor_id = ObjectId(monitor_id)
    monitor = await db.apis.find_one({"_id": monitor_id})
    if monitor is None:
        raise ValueError(f"Monitor {monitor_id} not found")
    try:
        result = await perform_http_check(monitor)
    except SSRFBlocked as exc:
        # SSRF-blocked targets are recorded as failed checks so the monitor
        # visibly reflects the problem, but never hit the network.
        result = {
            "status_code": None,
            "response_time_ms": 0.0,
            "success": False,
            "error": f"SSRF blocked: {exc}",
            "timed_out": False,
            "response_size_bytes": 0,
            "timestamp": utcnow(),
        }
    check_doc = await monitor_service.record_check(db, monitor, result)
    return check_doc


async def _scheduled_check(monitor_id: str) -> None:
    try:
        await check_monitor(monitor_id)
    except Exception:
        logger.exception("Scheduled check failed for monitor %s", monitor_id)


# ---------------------------------------------------------------------------
# Scheduling
# ---------------------------------------------------------------------------

async def schedule_monitor(db: AsyncIOMotorDatabase, monitor: dict) -> None:
    """(Re)schedule the interval job for a monitor. Paused/inactive -> removed."""
    scheduler = get_scheduler()
    job_id = _job_id(monitor["_id"])
    async with _job_lock:
        existing = scheduler.get_job(job_id)
        if existing:
            scheduler.remove_job(job_id)
        if monitor.get("active"):
            interval = int(monitor.get("interval", 300))
            scheduler.add_job(
                _scheduled_check,
                "interval",
                seconds=interval,
                id=job_id,
                args=[str(monitor["_id"])],
                max_instances=1,
                coalesce=True,
                misfire_grace_time=60,
            )
            logger.info("Scheduled monitor %s every %ss", monitor["_id"], interval)


async def unschedule_monitor(monitor_id: ObjectId | str) -> None:
    scheduler = get_scheduler()
    job_id = _job_id(monitor_id)
    async with _job_lock:
        if scheduler.get_job(job_id):
            scheduler.remove_job(job_id)


async def refresh_monitor_schedule(db: AsyncIOMotorDatabase, monitor_id: ObjectId | str) -> None:
    """Call after create/update/pause/resume to keep the job in sync."""
    if isinstance(monitor_id, str):
        monitor_id = ObjectId(monitor_id)
    monitor = await db.apis.find_one({"_id": monitor_id})
    if monitor is None:
        await unschedule_monitor(monitor_id)
    else:
        await schedule_monitor(db, monitor)


# ---------------------------------------------------------------------------
# Pruning + escalation sweeps
# ---------------------------------------------------------------------------

async def prune_old_results(db: AsyncIOMotorDatabase | None = None) -> int:
    """Delete check results older than each user's retention window."""
    if db is None:
        db = get_db()
    total_deleted = 0
    user_ids = await db.apis.distinct("user_id")
    for user_id in user_ids:
        settings = await get_effective_settings(db, user_id)
        cutoff = utcnow() - timedelta(days=settings["results_retention_days"])
        res = await db.checks.delete_many({"user_id": user_id, "timestamp": {"$lt": cutoff}})
        total_deleted += res.deleted_count
    if total_deleted:
        logger.info("Pruned %d old check results", total_deleted)
    return total_deleted


async def escalation_sweep(db: AsyncIOMotorDatabase | None = None) -> int:
    """Escalate open high-severity incidents past the downtime threshold."""
    from app.services import incident_service  # local import to avoid cycles

    if db is None:
        db = get_db()
    escalated = 0
    cursor = db.incidents.find(
        {"status": {"$in": list(incident_service.OPEN_STATUSES)}, "severity": "high"}
    )
    async for incident in cursor:
        if await incident_service.maybe_escalate(db, incident):
            escalated += 1
    return escalated


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

async def start_engine(db: AsyncIOMotorDatabase) -> None:
    scheduler = get_scheduler()
    if not scheduler.running:
        scheduler.start()
    # Schedule every active monitor.
    async for monitor in db.apis.find({"active": True}):
        await schedule_monitor(db, monitor)
    # Housekeeping jobs.
    if not scheduler.get_job("prune-results"):
        scheduler.add_job(prune_old_results, "interval", hours=6, id="prune-results",
                          max_instances=1, coalesce=True)
    if not scheduler.get_job("escalation-sweep"):
        scheduler.add_job(escalation_sweep, "interval", minutes=5, id="escalation-sweep",
                          max_instances=1, coalesce=True)
    count = len([j for j in scheduler.get_jobs() if j.id.startswith("monitor:")])
    logger.info("Monitoring engine started with %d monitor jobs", count)


async def stop_engine() -> None:
    scheduler = get_scheduler()
    if scheduler.running:
        scheduler.shutdown(wait=False)
        logger.info("Monitoring engine stopped")
