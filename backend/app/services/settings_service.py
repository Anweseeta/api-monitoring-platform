"""Per-user settings service (merged over defaults)."""
from typing import Any

from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.models import DEFAULT_SETTINGS, serialize_settings
from app.utils.time import utcnow


def default_settings() -> dict[str, Any]:
    env = get_settings()
    merged = dict(DEFAULT_SETTINGS)
    merged["default_interval"] = env.default_interval
    merged["default_timeout"] = env.default_timeout
    merged["failure_threshold"] = env.failure_threshold
    merged["recovery_threshold"] = env.recovery_threshold
    merged["degraded_latency_ms"] = env.degraded_latency_ms
    merged["results_retention_days"] = env.results_retention_days
    return merged


async def get_settings_doc(db: AsyncIOMotorDatabase, user_id: ObjectId) -> dict | None:
    return await db.settings.find_one({"user_id": user_id})


async def get_effective_settings(db: AsyncIOMotorDatabase, user_id: ObjectId) -> dict[str, Any]:
    """Return the merged settings dict used by the monitoring engine."""
    doc = await get_settings_doc(db, user_id)
    merged = default_settings()
    if doc:
        for key in DEFAULT_SETTINGS:
            if key in doc and doc[key] is not None:
                merged[key] = doc[key]
    notifications = dict(DEFAULT_SETTINGS["notifications"])
    if isinstance(merged.get("notifications"), dict):
        notifications.update(merged["notifications"])
    merged["notifications"] = notifications
    return merged


async def serialize_user_settings(db: AsyncIOMotorDatabase, user_doc: dict) -> dict:
    doc = await get_settings_doc(db, user_doc["_id"])
    return serialize_settings(user_doc, doc)


async def update_settings(
    db: AsyncIOMotorDatabase, user_doc: dict, update: dict[str, Any]
) -> dict:
    """Apply a partial settings update; returns the serialized settings object."""
    user_id = user_doc["_id"]
    patch: dict[str, Any] = {}
    for key in (
        "default_timeout",
        "default_interval",
        "failure_threshold",
        "recovery_threshold",
        "degraded_latency_ms",
        "results_retention_days",
    ):
        if key in update and update[key] is not None:
            patch[key] = update[key]
    notifications = update.get("notifications") or {}
    notif_patch = {
        k: v for k, v in notifications.items() if k in ("email_enabled", "webhook_enabled") and v is not None
    }
    if notif_patch:
        existing = await get_settings_doc(db, user_id) or {}
        merged_notif = dict(DEFAULT_SETTINGS["notifications"])
        merged_notif.update(existing.get("notifications", {}))
        merged_notif.update(notif_patch)
        patch["notifications"] = merged_notif
    profile = update.get("profile") or {}
    if profile.get("name"):
        await db.users.update_one({"_id": user_id}, {"$set": {"name": profile["name"]}})
        user_doc = await db.users.find_one({"_id": user_id})
    # profile.email is read-only and intentionally ignored.
    if patch:
        patch["updated_at"] = utcnow()
        await db.settings.update_one({"user_id": user_id}, {"$set": patch}, upsert=True)
    return await serialize_user_settings(db, user_doc)
