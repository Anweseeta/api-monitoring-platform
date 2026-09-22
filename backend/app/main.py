"""FastAPI application entrypoint.

- CORS origins come from FRONTEND_URL env.
- All errors are returned in the contract error envelope
  {"success": false, "message": ..., "error_code": ...}; no stack traces.
- Startup: connect Mongo, ensure indexes, start the monitoring engine.
- Shutdown: stop the engine, close Mongo.
"""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import activity, auth, dashboard, demo, incidents, monitors, settings, webhooks
from app.core.config import get_settings
from app.database.indexes import ensure_indexes
from app.database.mongo import close_mongo, get_db
from app.monitoring import engine as monitoring_engine
from app.schemas.common import error_response

logger = logging.getLogger(__name__)

# Refuse to boot in production with the shipped development secret.
DEV_JWT_SECRETS = {"dev-secret-change-me", "changeme-in-production", ""}


@asynccontextmanager
async def lifespan(app: FastAPI):
    app_settings = get_settings()
    if app_settings.is_production:
        if app_settings.jwt_secret in DEV_JWT_SECRETS or len(app_settings.jwt_secret) < 32:
            raise RuntimeError(
                "Refusing to start: set a strong JWT_SECRET (≥32 chars) when ENVIRONMENT=production."
            )
        if app_settings.monitor_allow_loopback:
            logger.warning(
                "MONITOR_ALLOW_LOOPBACK=true in production: monitors may target loopback/private IPs."
            )
    elif app_settings.jwt_secret in DEV_JWT_SECRETS:
        logger.warning("Using the default development JWT_SECRET — set JWT_SECRET for any shared deployment.")
    db = get_db()
    await ensure_indexes(db)
    await monitoring_engine.start_engine(db)
    logger.info("Startup complete")
    yield
    await monitoring_engine.stop_engine()
    await close_mongo()
    logger.info("Shutdown complete")


def create_app() -> FastAPI:
    app_settings = get_settings()
    app = FastAPI(
        title="API Monitoring & Incident Tracking Platform",
        lifespan=lifespan,
    )

    origins = [o.strip() for o in app_settings.frontend_url.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Exception handlers -> contract error envelope --------------------

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        detail = exc.detail
        if isinstance(detail, dict) and "success" in detail:
            body = detail
        else:
            body = error_response(str(detail), "HTTP_ERROR")
        return JSONResponse(status_code=exc.status_code, content=body)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        first = exc.errors()[0] if exc.errors() else {}
        loc = ".".join(str(p) for p in first.get("loc", []))
        message = f"{loc}: {first.get('msg', 'validation error')}" if loc else "Validation error"
        return JSONResponse(
            status_code=422,
            content=error_response(message, "VALIDATION_ERROR"),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        # Never leak stack traces or internals to the client.
        logger.exception("Unhandled error on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content=error_response("Internal server error", "INTERNAL_ERROR"),
        )

    # --- Routers ------------------------------------------------------------

    app.include_router(auth.router)
    app.include_router(monitors.router)
    app.include_router(incidents.router)
    app.include_router(dashboard.router)
    app.include_router(activity.router)
    app.include_router(settings.router)
    app.include_router(webhooks.router)
    app.include_router(demo.router)

    return app


app = create_app()
