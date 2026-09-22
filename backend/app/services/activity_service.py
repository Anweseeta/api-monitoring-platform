"""Activity log service."""
from typing import Any

from bson import ObjectId
from fastapi import Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.utils.time import utcnow


async def log_activity(
    db: AsyncIOMotorDatabase,
    user_id: ObjectId | str,
    action: str,
    resource_type: str = "",
    resource_id: ObjectId | str | None = None,
    resource_name: str = "",
    request: Request | None = None,
) -> None:
    """Append an activity log entry. Never logs headers or tokens."""
    if isinstance(resource_id, str) and ObjectId.is_valid(resource_id):
        resource_id = ObjectId(resource_id)
    doc: dict[str, Any] = {
        "user_id": ObjectId(str(user_id)),
        "action": action,
        "resource_type": resource_type,
        "resource_id": resource_id,
        "resource_name": resource_name,
        "timestamp": utcnow(),
        "ip": "",
        "user_agent": "",
    }
    if request is not None:
        if request.client:
            doc["ip"] = request.client.host
        # Only the user-agent string is stored; never auth headers.
        doc["user_agent"] = request.headers.get("user-agent", "")[:500]
    await db.activity_logs.insert_one(doc)
