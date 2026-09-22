"""Webhook routes."""
import asyncio
from urllib.parse import urlparse

from bson import ObjectId
from fastapi import APIRouter, Depends, HTTPException, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.database.mongo import get_db
from app.models import serialize_webhook
from app.monitoring.ssrf import SSRFBlocked, check_url_allowed
from app.schemas.common import error_response, success_response
from app.schemas.settings import WebhookCreate
from app.services.activity_service import log_activity
from app.utils.time import utcnow

router = APIRouter(prefix="/api/webhooks", tags=["webhooks"])


@router.get("")
async def list_webhooks(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    docs = await db.webhooks.find({"user_id": user["_id"]}).sort("created_at", -1).to_list(length=1000)
    return success_response([serialize_webhook(d) for d in docs])


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_webhook(
    payload: WebhookCreate,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    parsed = urlparse(payload.url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response("Webhook URL must be a valid http(s) URL", "VALIDATION_ERROR"),
        )
    # SSRF guard: the server will POST incident payloads to this URL.
    try:
        await asyncio.to_thread(check_url_allowed, payload.url)
    except SSRFBlocked as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(f"Webhook URL is not allowed: {exc}", "SSRF_BLOCKED"),
        ) from exc
    doc = {
        "user_id": user["_id"],
        "name": payload.name,
        "url": payload.url,
        "events": payload.events,
        "active": payload.active,
        "created_at": utcnow(),
    }
    result = await db.webhooks.insert_one(doc)
    doc["_id"] = result.inserted_id
    await log_activity(db, user["_id"], "webhook.created", "webhook", doc["_id"], doc["name"], request)
    return success_response(serialize_webhook(doc))


@router.delete("/{webhook_id}")
async def delete_webhook(
    webhook_id: str,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    if not ObjectId.is_valid(webhook_id):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Webhook not found", "WEBHOOK_NOT_FOUND"),
        )
    doc = await db.webhooks.find_one({"_id": ObjectId(webhook_id)})
    if doc is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=error_response("Webhook not found", "WEBHOOK_NOT_FOUND"),
        )
    if doc.get("user_id") != user["_id"]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=error_response("Access denied", "FORBIDDEN"),
        )
    await db.webhooks.delete_one({"_id": doc["_id"]})
    await log_activity(db, user["_id"], "webhook.deleted", "webhook", doc["_id"], doc.get("name", ""), request)
    return success_response(None)
