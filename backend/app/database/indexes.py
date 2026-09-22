"""MongoDB indexes for all collections used by the contract."""
from motor.motor_asyncio import AsyncIOMotorDatabase

INDEXES: dict[str, list[tuple]] = {
    "users": [
        ([("email", 1)], {"unique": True}),
    ],
    "apis": [
        ([("user_id", 1), ("created_at", -1)], {}),
        ([("user_id", 1), ("active", 1)], {}),
    ],
    "checks": [
        ([("api_id", 1), ("timestamp", -1)], {}),
        ([("user_id", 1), ("timestamp", -1)], {}),
    ],
    "incidents": [
        ([("user_id", 1), ("status", 1), ("created_at", -1)], {}),
        ([("api_id", 1), ("status", 1)], {}),
        # Atomic dedup guard: at most one non-resolved incident per API.
        # ensure_open_incident() catches DuplicateKeyError and re-reads.
        (
            [("api_id", 1)],
            {
                "unique": True,
                "partialFilterExpression": {
                    "status": {"$in": ["open", "investigating", "identified", "monitoring"]}
                },
            },
        ),
    ],
    "incident_events": [
        ([("incident_id", 1), ("timestamp", -1)], {}),
    ],
    "activity_logs": [
        ([("user_id", 1), ("timestamp", -1)], {}),
    ],
    "webhooks": [
        ([("user_id", 1)], {}),
    ],
    "settings": [
        ([("user_id", 1)], {"unique": True}),
    ],
}


async def ensure_indexes(db: AsyncIOMotorDatabase) -> None:
    for collection_name, specs in INDEXES.items():
        collection = db[collection_name]
        for keys, options in specs:
            await collection.create_index(keys, **options)
