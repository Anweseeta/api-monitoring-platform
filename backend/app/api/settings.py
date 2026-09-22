"""Settings routes."""
from fastapi import APIRouter, Depends, Request
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.database.mongo import get_db
from app.schemas.common import success_response
from app.schemas.settings import SettingsUpdate
from app.services.activity_service import log_activity
from app.services.settings_service import serialize_user_settings, update_settings

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
async def get_settings(
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    return success_response(await serialize_user_settings(db, user))


@router.put("")
async def put_settings(
    payload: SettingsUpdate,
    request: Request,
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    data = await update_settings(db, user, payload.model_dump())
    await log_activity(db, user["_id"], "settings.updated", "settings", None, "", request)
    return success_response(data)
