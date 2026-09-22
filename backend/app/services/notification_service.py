"""Notification dispatch: email via SMTP env config + webhook POSTs via httpx.

Both are best-effort: failures are swallowed (and logged) so a broken
webhook/SMTP config can never break the monitoring pipeline.
"""
import asyncio
import logging
import smtplib
from email.message import EmailMessage
from typing import Any

import httpx
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.config import get_settings
from app.utils.time import iso_z, utcnow

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT = 10.0


def _smtp_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and s.smtp_user and s.smtp_password)


def _send_email_sync(to_email: str, subject: str, body: str) -> None:
    s = get_settings()
    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.set_content(body)
    with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15) as server:
        server.starttls()
        server.login(s.smtp_user, s.smtp_password)
        server.send_message(msg)


async def send_email(to_email: str, subject: str, body: str) -> bool:
    """Send an email if SMTP is configured. Returns True when sent."""
    if not _smtp_configured():
        logger.debug("SMTP not configured; skipping email to %s", to_email)
        return False
    try:
        await asyncio.to_thread(_send_email_sync, to_email, subject, body)
        return True
    except Exception:
        logger.exception("Failed to send email to %s", to_email)
        return False


async def _post_webhook(url: str, payload: dict[str, Any]) -> None:
    # Re-validate at dispatch time: DNS can change between webhook creation
    # and firing, so a creation-time check alone is not sufficient.
    from app.monitoring.ssrf import SSRFBlocked, check_url_allowed

    try:
        await asyncio.to_thread(check_url_allowed, url)
    except SSRFBlocked as exc:
        logger.warning("Skipping webhook POST to %s: %s", url, exc)
        return
    # trust_env=False: ignore (possibly broken) proxy env vars; dispatch direct.
    async with httpx.AsyncClient(timeout=WEBHOOK_TIMEOUT, trust_env=False) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()


async def dispatch_webhooks(
    db: AsyncIOMotorDatabase,
    user_id: ObjectId,
    event: str,
    payload: dict[str, Any],
) -> int:
    """POST the payload to every active webhook of the user subscribed to event.

    Returns the number of webhooks successfully notified.
    """
    cursor = db.webhooks.find({"user_id": user_id, "active": True, "events": event})
    webhooks = await cursor.to_list(length=100)
    if not webhooks:
        return 0
    results = await asyncio.gather(
        *(_post_webhook(wh["url"], payload) for wh in webhooks),
        return_exceptions=True,
    )
    delivered = 0
    for wh, result in zip(webhooks, results):
        if isinstance(result, Exception):
            logger.warning("Webhook %s (%s) failed: %s", wh.get("name"), wh.get("url"), result)
        else:
            delivered += 1
    return delivered


def webhook_payload(
    *,
    event: str,
    api_name: str,
    api_id: ObjectId | str,
    severity: str,
    status: str,
    incident_id: ObjectId | str | None = None,
) -> dict[str, Any]:
    return {
        "event": event,
        "api": api_name,
        "api_id": str(api_id),
        "severity": severity,
        "status": status,
        "timestamp": iso_z(utcnow()),
        "incident_id": str(incident_id) if incident_id else None,
    }
