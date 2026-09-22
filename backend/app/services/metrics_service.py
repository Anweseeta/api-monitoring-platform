"""Metrics aggregation over check results."""
from datetime import datetime, timedelta, timezone

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.utils.time import iso_z, period_start, utcnow

BUCKETS = {"24h": "hour", "7d": "day", "30d": "day"}


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    k = (len(ordered) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    frac = k - lo
    return round(ordered[lo] * (1 - frac) + ordered[hi] * frac, 2)


def _bucket_key(ts: datetime, granularity: str) -> datetime:
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    if granularity == "hour":
        return ts.replace(minute=0, second=0, microsecond=0)
    return ts.replace(hour=0, minute=0, second=0, microsecond=0)


def _bucket_range(start: datetime, end: datetime, granularity: str) -> list[datetime]:
    step = timedelta(hours=1) if granularity == "hour" else timedelta(days=1)
    current = _bucket_key(start, granularity)
    out = []
    while current <= end:
        out.append(current)
        current += step
    return out


async def _checks_in_period(
    db: AsyncIOMotorDatabase,
    api_ids: list[ObjectId] | None,
    user_id: ObjectId | None,
    period: str,
) -> tuple[list[dict], datetime, datetime]:
    end = utcnow()
    start = period_start(period, end)
    match: dict = {"timestamp": {"$gte": start, "$lte": end}}
    if api_ids is not None:
        match["api_id"] = {"$in": api_ids}
    if user_id is not None:
        match["user_id"] = user_id
    docs = await db.checks.find(match).sort("timestamp", 1).to_list(length=100000)
    return docs, start, end


def _classify(check: dict) -> str:
    if check.get("timed_out"):
        return "timeout"
    if check.get("status_code") is None:
        return "connection_error"
    code = int(check["status_code"])
    if 200 <= code < 300:
        return "2xx"
    if 300 <= code < 400:
        return "3xx"
    if 400 <= code < 500:
        return "4xx"
    return "5xx"


async def compute_metrics(
    db: AsyncIOMotorDatabase,
    api_id: ObjectId,
    user_id: ObjectId,
    period: str = "24h",
) -> dict:
    checks, start, end = await _checks_in_period(db, [api_id], user_id, period)
    granularity = BUCKETS.get(period, "hour")

    total = len(checks)
    successful = [c for c in checks if c.get("success")]
    failed = total - len(successful)
    latencies = [c["response_time_ms"] for c in successful if c.get("response_time_ms") is not None]

    distribution = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0, "timeout": 0, "connection_error": 0}
    for c in checks:
        distribution[_classify(c)] += 1

    buckets = _bucket_range(start, end, granularity)
    latency_sums: dict[datetime, list[float]] = {b: [] for b in buckets}
    uptime_totals: dict[datetime, list[int]] = {b: [] for b in buckets}
    for c in checks:
        key = _bucket_key(c["timestamp"], granularity)
        if key in latency_sums:
            if c.get("response_time_ms") is not None:
                latency_sums[key].append(c["response_time_ms"])
            uptime_totals[key].append(1 if c.get("success") else 0)

    response_time_series = [
        {"timestamp": iso_z(b), "avg_ms": round(sum(v) / len(v), 2) if v else None}
        for b, v in latency_sums.items()
    ]
    uptime_series = [
        {
            "timestamp": iso_z(b),
            "uptime": round(sum(v) / len(v) * 100.0, 2) if v else None,
        }
        for b, v in uptime_totals.items()
    ]

    return {
        "uptime_percent": round(len(successful) / total * 100.0, 2) if total else 100.0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
        "min_latency_ms": round(min(latencies), 2) if latencies else None,
        "max_latency_ms": round(max(latencies), 2) if latencies else None,
        "p50_latency_ms": _percentile(latencies, 50),
        "p95_latency_ms": _percentile(latencies, 95),
        "p99_latency_ms": _percentile(latencies, 99),
        "total_checks": total,
        "successful_checks": len(successful),
        "failed_checks": failed,
        "error_rate_percent": round(failed / total * 100.0, 2) if total else 0.0,
        "status_code_distribution": distribution,
        "response_time_series": response_time_series,
        "uptime_series": uptime_series,
    }


async def compute_uptime(
    db: AsyncIOMotorDatabase, api_id: ObjectId, user_id: ObjectId, period: str = "24h"
) -> dict:
    checks, _, _ = await _checks_in_period(db, [api_id], user_id, period)
    total = len(checks)
    successful = sum(1 for c in checks if c.get("success"))
    return {
        "uptime_percent": round(successful / total * 100.0, 2) if total else 100.0,
        "total_checks": total,
        "successful_checks": successful,
    }


async def _series_points(
    db: AsyncIOMotorDatabase, user_id: ObjectId, period: str, kind: str
) -> list[dict]:
    checks, start, end = await _checks_in_period(db, None, user_id, period)
    granularity = BUCKETS.get(period, "hour")
    buckets = _bucket_range(start, end, granularity)
    acc: dict[datetime, list[dict]] = {b: [] for b in buckets}
    for c in checks:
        key = _bucket_key(c["timestamp"], granularity)
        if key in acc:
            acc[key].append(c)
    points = []
    for b in buckets:
        group = acc[b]
        if kind == "uptime":
            value = round(sum(1 for c in group if c.get("success")) / len(group) * 100.0, 2) if group else None
            points.append({"timestamp": iso_z(b), "uptime": value})
        elif kind == "latency":
            lats = [c["response_time_ms"] for c in group if c.get("response_time_ms") is not None]
            points.append({"timestamp": iso_z(b), "avg_ms": round(sum(lats) / len(lats), 2) if lats else None})
        elif kind == "incidents":
            points.append({"timestamp": iso_z(b), "created": 0, "resolved": 0})
    return points


async def dashboard_uptime_points(db, user_id: ObjectId, period: str) -> list[dict]:
    return await _series_points(db, user_id, period, "uptime")


async def dashboard_latency_points(db, user_id: ObjectId, period: str) -> list[dict]:
    return await _series_points(db, user_id, period, "latency")


async def dashboard_incident_points(
    db: AsyncIOMotorDatabase, user_id: ObjectId, period: str
) -> list[dict]:
    end = utcnow()
    start = period_start(period, end)
    granularity = BUCKETS.get(period, "hour")
    buckets = _bucket_range(start, end, granularity)
    created = {b: 0 for b in buckets}
    resolved = {b: 0 for b in buckets}
    async for doc in db.incidents.find(
        {"user_id": user_id, "$or": [{"created_at": {"$gte": start}}, {"resolved_at": {"$gte": start}}]}
    ):
        c_at = doc.get("created_at")
        if c_at:
            key = _bucket_key(c_at, granularity)
            if key in created:
                created[key] += 1
        r_at = doc.get("resolved_at")
        if r_at:
            key = _bucket_key(r_at, granularity)
            if key in resolved:
                resolved[key] += 1
    return [
        {"timestamp": iso_z(b), "created": created[b], "resolved": resolved[b]}
        for b in buckets
    ]
