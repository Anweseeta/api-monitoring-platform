"""Serializers: Mongo documents -> contract wire dicts.

IDs are ObjectId hex strings; datetimes are ISO-8601 UTC 'Z' strings.
Never include password hashes or raw auth headers in logs; headers stored on
the monitor doc are only ever sent to the monitored URL itself.
"""
from app.utils.time import iso_z

DEFAULT_SETTINGS = {
    "default_timeout": 10,
    "default_interval": 300,
    "failure_threshold": 3,
    "recovery_threshold": 2,
    "degraded_latency_ms": 1000,
    "results_retention_days": 30,
    "notifications": {"email_enabled": False, "webhook_enabled": True},
}


def oid(doc: dict) -> str:
    return str(doc["_id"])


def serialize_user(doc: dict) -> dict:
    return {
        "id": oid(doc),
        "name": doc.get("name", ""),
        "email": doc.get("email", ""),
        "created_at": iso_z(doc.get("created_at")),
    }


def serialize_monitor(doc: dict, uptime_24h: float | None = None) -> dict:
    return {
        "id": oid(doc),
        "user_id": str(doc.get("user_id")),
        "name": doc.get("name", ""),
        "url": doc.get("url", ""),
        "method": doc.get("method", "GET"),
        "description": doc.get("description", ""),
        "interval": doc.get("interval", 300),
        "timeout": doc.get("timeout", 10),
        "expected_status": doc.get("expected_status", 200),
        "headers": doc.get("headers", {}),
        "body": doc.get("body"),
        "active": doc.get("active", True),
        "status": doc.get("status", "healthy"),
        "consecutive_failures": doc.get("consecutive_failures", 0),
        "consecutive_successes": doc.get("consecutive_successes", 0),
        "last_checked_at": iso_z(doc.get("last_checked_at")),
        "uptime_24h": uptime_24h if uptime_24h is not None else doc.get("uptime_24h", 100.0),
        "created_at": iso_z(doc.get("created_at")),
        "updated_at": iso_z(doc.get("updated_at")),
    }


def serialize_check(doc: dict) -> dict:
    return {
        "id": oid(doc),
        "api_id": str(doc.get("api_id")),
        "timestamp": iso_z(doc.get("timestamp")),
        "status_code": doc.get("status_code"),
        "response_time_ms": doc.get("response_time_ms"),
        "success": doc.get("success", False),
        "error": doc.get("error"),
        "timed_out": doc.get("timed_out", False),
        "response_size_bytes": doc.get("response_size_bytes", 0),
    }


def serialize_incident(doc: dict) -> dict:
    return {
        "id": oid(doc),
        "api_id": str(doc.get("api_id")),
        "user_id": str(doc.get("user_id")),
        "title": doc.get("title", ""),
        "description": doc.get("description", ""),
        "status": doc.get("status", "open"),
        "severity": doc.get("severity", "medium"),
        "started_at": iso_z(doc.get("started_at")),
        "detected_at": iso_z(doc.get("detected_at")),
        "resolved_at": iso_z(doc.get("resolved_at")),
        "duration_seconds": doc.get("duration_seconds"),
        "root_cause": doc.get("root_cause", ""),
        "resolution_notes": doc.get("resolution_notes", ""),
        "created_by": doc.get("created_by", "system"),
        "updated_at": iso_z(doc.get("updated_at")),
    }


def serialize_incident_event(doc: dict) -> dict:
    return {
        "id": oid(doc),
        "incident_id": str(doc.get("incident_id")),
        "timestamp": iso_z(doc.get("timestamp")),
        "event_type": doc.get("event_type", ""),
        "message": doc.get("message", ""),
    }


def serialize_activity(doc: dict) -> dict:
    return {
        "id": oid(doc),
        "user_id": str(doc.get("user_id")),
        "action": doc.get("action", ""),
        "resource_type": doc.get("resource_type", ""),
        "resource_id": str(doc.get("resource_id")) if doc.get("resource_id") else None,
        "resource_name": doc.get("resource_name", ""),
        "timestamp": iso_z(doc.get("timestamp")),
        "ip": doc.get("ip", ""),
        "user_agent": doc.get("user_agent", ""),
    }


def serialize_webhook(doc: dict) -> dict:
    return {
        "id": oid(doc),
        "name": doc.get("name", ""),
        "url": doc.get("url", ""),
        "events": doc.get("events", []),
        "active": doc.get("active", True),
        "created_at": iso_z(doc.get("created_at")),
    }


def serialize_settings(user_doc: dict, settings_doc: dict | None) -> dict:
    merged = dict(DEFAULT_SETTINGS)
    if settings_doc:
        for key in DEFAULT_SETTINGS:
            if key in settings_doc and settings_doc[key] is not None:
                merged[key] = settings_doc[key]
    notifications = dict(DEFAULT_SETTINGS["notifications"])
    if isinstance(merged.get("notifications"), dict):
        notifications.update(merged["notifications"])
    return {
        "default_timeout": merged["default_timeout"],
        "default_interval": merged["default_interval"],
        "failure_threshold": merged["failure_threshold"],
        "recovery_threshold": merged["recovery_threshold"],
        "degraded_latency_ms": merged["degraded_latency_ms"],
        "results_retention_days": merged["results_retention_days"],
        "notifications": notifications,
        "profile": {"name": user_doc.get("name", ""), "email": user_doc.get("email", "")},
    }
