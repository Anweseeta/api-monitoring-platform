"""Auth routes: register, login, me."""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.deps import get_current_user
from app.core.rate_limit import rate_limit
from app.core.security import create_access_token, hash_password, verify_password
from app.database.mongo import get_db
from app.models import serialize_user
from app.schemas.auth import LoginRequest, RegisterRequest
from app.schemas.common import error_response, success_response
from app.services.activity_service import log_activity
from app.utils.time import utcnow

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", status_code=status.HTTP_201_CREATED, dependencies=[Depends(rate_limit("register"))])
async def register(payload: RegisterRequest, request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    email = payload.email.strip().lower()
    existing = await db.users.find_one({"email": email})
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=error_response("An account with this email already exists", "USER_EXISTS"),
        )
    user_doc = {
        "name": payload.name.strip(),
        "email": email,
        "password_hash": hash_password(payload.password),
        "created_at": utcnow(),
    }
    result = await db.users.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    token = create_access_token(str(user_doc["_id"]))
    await log_activity(db, user_doc["_id"], "user.registered", "user", user_doc["_id"], user_doc["name"], request)
    return success_response(
        {"user": serialize_user(user_doc), "access_token": token, "token_type": "bearer"}
    )


@router.post("/login", dependencies=[Depends(rate_limit("login"))])
async def login(payload: LoginRequest, request: Request, db: AsyncIOMotorDatabase = Depends(get_db)):
    email = payload.email.strip().lower()
    user_doc = await db.users.find_one({"email": email})
    if user_doc is None or not verify_password(payload.password, user_doc.get("password_hash", "")):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error_response("Invalid email or password", "INVALID_CREDENTIALS"),
        )
    token = create_access_token(str(user_doc["_id"]))
    await log_activity(db, user_doc["_id"], "user.logged_in", "user", user_doc["_id"], user_doc["name"], request)
    return success_response(
        {"user": serialize_user(user_doc), "access_token": token, "token_type": "bearer"}
    )


@router.get("/me")
async def me(user: dict = Depends(get_current_user)):
    return success_response({"user": serialize_user(user)})
