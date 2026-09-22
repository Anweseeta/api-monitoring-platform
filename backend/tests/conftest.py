"""Shared pytest fixtures.

- Uses a dedicated test database (apimonitor_test) via env var, set BEFORE
  the app is imported (get_settings is lru-cached).
- `client` is an httpx AsyncClient over ASGI transport with get_db overridden
  to the cleaned test database. Lifespan (scheduler) does not run under ASGI
  transport, so no background jobs interfere with assertions.
- `demo_server` runs the real demo/health endpoints on 127.0.0.1:8123 in a
  thread (lifespan off, so no scheduler) for end-to-end monitor checks.
"""
import os

os.environ.setdefault("DATABASE_NAME", "apimonitor_test")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault("MONITOR_ALLOW_LOOPBACK", "true")
os.environ.setdefault("JWT_SECRET", "test-secret")

import threading
import time

import httpx
import pytest
import pytest_asyncio
import uvicorn
from httpx import ASGITransport, AsyncClient
from motor.motor_asyncio import AsyncIOMotorClient

from app.database.indexes import ensure_indexes
from app.database.mongo import get_db
from app.main import create_app

COLLECTIONS = [
    "users", "apis", "checks", "incidents", "incident_events",
    "activity_logs", "webhooks", "settings",
]

TEST_DB_NAME = os.environ["DATABASE_NAME"]


@pytest.fixture(scope="session")
def app():
    return create_app()


@pytest.fixture(scope="session")
def demo_server():
    """Real HTTP server exposing /demo/* and /health for monitor checks."""
    demo_app = create_app()
    config = uvicorn.Config(
        demo_app, host="127.0.0.1", port=8123, lifespan="off", log_level="error"
    )
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    # NOTE: trust_env=False — the sandbox no_proxy env var contains entries
    # that httpx cannot parse; the poll must not go through env proxies.
    for _ in range(200):
        try:
            r = httpx.get("http://127.0.0.1:8123/health", timeout=1, trust_env=False)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.05)
    else:
        raise RuntimeError("demo server did not start")
    yield "http://127.0.0.1:8123"
    server.should_exit = True
    thread.join(timeout=10)


@pytest_asyncio.fixture
async def db():
    client = AsyncIOMotorClient("mongodb://localhost:27017", tz_aware=True)
    database = client[TEST_DB_NAME]
    await ensure_indexes(database)
    yield database
    client.close()


@pytest_asyncio.fixture
async def clean_db(db):
    for name in COLLECTIONS:
        await db[name].delete_many({})
    return db


@pytest_asyncio.fixture
async def client(app, clean_db):
    app.dependency_overrides[get_db] = lambda: clean_db
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as c:
        yield c
    app.dependency_overrides.clear()


async def register_user(client: AsyncClient, name="Test User", email="test@example.com",
                        password="Password123!") -> dict:
    r = await client.post("/api/auth/register", json={"name": name, "email": email, "password": password})
    assert r.status_code == 201, r.text
    return r.json()["data"]


async def auth_headers(client: AsyncClient, email="test@example.com", password="Password123!") -> dict:
    data = await register_user(client, email=email, password=password)
    return {"Authorization": f"Bearer {data['access_token']}"}
