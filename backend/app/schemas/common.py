"""Contract envelopes: {success, data, pagination} and error envelope."""
from typing import Any


def success_response(data: Any = None, pagination: dict | None = None) -> dict:
    payload: dict[str, Any] = {"success": True, "data": data}
    if pagination is not None:
        payload["pagination"] = pagination
    return payload


def error_response(message: str, error_code: str) -> dict:
    return {"success": False, "message": message, "error_code": error_code}
