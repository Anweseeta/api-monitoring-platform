"""Activity log routes."""
from fastapi import APIRouter, Depends, Query
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.database.mongo import get_db
from app.models import serialize_activity
from app.schemas.common import success_response
from app.utils.pagination import paginate, pagination_params

router = APIRouter(prefix="/api/activity", tags=["activity"])


@router.get("")
async def list_activity(
    resource_type: str = Query(default=""),
    action: str = Query(default=""),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncIOMotorDatabase = Depends(get_db),
    user: dict = Depends(get_current_user),
):
    filt: dict = {"user_id": user["_id"]}
    if resource_type:
        filt["resource_type"] = resource_type
    if action:
        filt["action"] = action
    params = pagination_params(page, page_size)
    items, pagination = await paginate(
        db.activity_logs, filt, params["page"], params["page_size"],
        sort=[("timestamp", -1)], serialize=serialize_activity,
    )
    return success_response(items, pagination)
