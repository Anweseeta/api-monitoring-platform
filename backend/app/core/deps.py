"""FastAPI dependencies: current user auth and per-resource ownership checks."""
from bson import ObjectId
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.security import decode_access_token
from app.database.mongo import get_db
from app.schemas.common import error_response

_bearer = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncIOMotorDatabase = Depends(get_db),
) -> dict:
    """Return the authenticated user document or raise 401."""
    if credentials is None or not credentials.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("Authentication required", "UNAUTHORIZED"),
        )
    user_id = decode_access_token(credentials.credentials)
    if not user_id or not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("Invalid or expired token", "INVALID_TOKEN"),
        )
    user = await db.users.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("User not found", "UNAUTHORIZED"),
        )
    return user


def parse_object_id(value: str, error_code: str = "VALIDATION_ERROR", message: str = "Invalid id") -> ObjectId:
    if not ObjectId.is_valid(value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=error_response(message, error_code),
        )
    return ObjectId(value)
