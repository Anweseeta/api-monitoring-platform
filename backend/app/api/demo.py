"""Unprotected demo + health endpoints.

/demo/* simulates target APIs for monitors to check. /demo/echo redacts
authorization-style headers before returning them.
/health and /health/db report app and database status.
"""
import asyncio
import random

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.database.mongo import get_db

router = APIRouter(tags=["demo"])

SENSITIVE_HEADERS = {"authorization", "proxy-authorization", "x-api-key", "cookie", "set-cookie"}


def _redact_headers(headers: dict) -> dict:
    return {
        name: ("[REDACTED]" if name.lower() in SENSITIVE_HEADERS else value)
        for name, value in headers.items()
    }


@router.get("/health")
async def health():
    return {"status": "healthy"}


@router.get("/health/db")
async def health_db(db: AsyncIOMotorDatabase = Depends(get_db)):
    try:
        await db.command("ping")
        return {"status": "healthy", "db": "connected"}
    except Exception:
        return {"status": "degraded", "db": "disconnected"}


@router.get("/demo/health")
async def demo_health():
    return {"status": "healthy"}


@router.get("/demo/slow")
async def demo_slow():
    await asyncio.sleep(3)
    return {"status": "ok", "delay_ms": 3000}


@router.get("/demo/error")
async def demo_error():
    return JSONResponse(status_code=500, content={"status": "error"})


@router.get("/demo/random")
async def demo_random():
    if random.random() < 0.5:
        return {"status": "ok"}
    return JSONResponse(status_code=500, content={"status": "error"})


@router.post("/demo/echo")
async def demo_echo(request: Request):
    try:
        body = await request.json()
    except Exception:
        body = None
    return {
        "received": body,
        "method": request.method,
        "headers_redacted": _redact_headers(dict(request.headers)),
    }
