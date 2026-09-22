"""Motor client singleton."""
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase

from app.core.config import get_settings

_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    global _client
    if _client is None:
        settings = get_settings()
        # tz_aware=True: datetimes come back as timezone-aware UTC, so
        # arithmetic against utcnow() never mixes naive and aware values.
        _client = AsyncIOMotorClient(settings.mongodb_uri, tz_aware=True)
    return _client


def get_db() -> AsyncIOMotorDatabase:
    settings = get_settings()
    return get_client()[settings.database_name]


async def close_mongo() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
