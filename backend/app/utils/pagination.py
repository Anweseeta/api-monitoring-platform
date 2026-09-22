"""Pagination helper matching the contract's pagination envelope."""
from typing import Any, TypeVar

from motor.motor_asyncio import AsyncIOMotorCollection

T = TypeVar("T")

DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


def pagination_params(page: int = 1, page_size: int = DEFAULT_PAGE_SIZE) -> dict[str, int]:
    page = max(page, 1)
    page_size = min(max(page_size, 1), MAX_PAGE_SIZE)
    return {"page": page, "page_size": page_size}


async def paginate(
    collection: AsyncIOMotorCollection,
    filter_: dict[str, Any],
    page: int,
    page_size: int,
    sort: list[tuple[str, int]] | None = None,
    serialize=None,
) -> tuple[list[dict], dict]:
    """Return (items, pagination) for a filtered query. Items are serialized if a serializer is given."""
    skip = (page - 1) * page_size
    cursor = collection.find(filter_)
    if sort:
        cursor = cursor.sort(sort)
    cursor = cursor.skip(skip).limit(page_size)
    docs = await cursor.to_list(length=page_size)
    total = await collection.count_documents(filter_)
    pages = (total + page_size - 1) // page_size if total else 0
    if serialize:
        items = [serialize(doc) for doc in docs]
    else:
        items = docs
    return items, {"page": page, "page_size": page_size, "total": total, "pages": pages}
