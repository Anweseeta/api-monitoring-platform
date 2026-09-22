"""Time helpers: always ISO-8601 UTC strings on the wire."""
from datetime import datetime, timedelta, timezone

PERIOD_TO_HOURS = {"24h": 24, "7d": 24 * 7, "30d": 24 * 30}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def iso_z(dt: datetime | None) -> str | None:
    """Serialize a datetime as '2026-09-22T13:00:00Z'. Returns None for None input."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def period_start(period: str, now: datetime | None = None) -> datetime:
    hours = PERIOD_TO_HOURS.get(period, 24)
    base = now or utcnow()
    return base - timedelta(hours=hours)
