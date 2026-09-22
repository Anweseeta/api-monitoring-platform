"""SSRF protection for monitor checks.

Resolves the URL hostname and blocks private/reserved/loopback/link-local
ranges, cloud metadata IPs, non-http(s) schemes and out-of-range ports.
Loopback is allowed only when MONITOR_ALLOW_LOOPBACK=true (default true so
the bundled /demo/* endpoints work out of the box; set false in production).
"""
import ipaddress
import socket
from urllib.parse import urlparse

from app.core.config import get_settings

# Cloud metadata endpoints that must never be reachable from a monitor check.
METADATA_IPS = {
    ipaddress.ip_address("169.254.169.254"),  # AWS/GCP/Azure metadata
    ipaddress.ip_address("100.100.100.200"),  # Alibaba Cloud metadata
}


class SSRFBlocked(Exception):
    """Raised when a monitor URL fails the SSRF safety check."""


def _ip_blocked(ip: ipaddress.IPv4Address | ipaddress.IPv6Address, allow_loopback: bool) -> bool:
    if ip in METADATA_IPS:
        return True
    if ip.is_loopback:
        # Loopback is allowed only when the flag is on; note that on some
        # Python versions loopback also reports is_private, so check it first.
        return not allow_loopback
    # Always blocked regardless of the loopback flag:
    return (
        ip.is_private
        or ip.is_reserved
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_unspecified
    )


def check_url_allowed(url: str, allow_loopback: bool | None = None) -> tuple[str, int]:
    """Validate a monitor URL. Returns (hostname, port).

    Raises SSRFBlocked with a human-readable reason when the URL is unsafe.
    """
    if allow_loopback is None:
        allow_loopback = get_settings().monitor_allow_loopback

    try:
        parsed = urlparse(url)
    except ValueError as exc:
        raise SSRFBlocked(f"Malformed URL: {exc}") from exc

    if parsed.scheme not in ("http", "https"):
        raise SSRFBlocked("Only http(s) URLs are allowed")

    hostname = parsed.hostname
    if not hostname:
        raise SSRFBlocked("URL has no hostname")

    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    if not 1 <= port <= 65535:
        raise SSRFBlocked("Port out of range")

    try:
        addrinfo = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise SSRFBlocked(f"DNS resolution failed for {hostname}") from exc

    checked: set[str] = set()
    for _family, _type, _proto, _canon, sockaddr in addrinfo:
        ip_str = sockaddr[0]
        if ip_str in checked:
            continue
        checked.add(ip_str)
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            raise SSRFBlocked(f"Unparseable resolved address {ip_str}") from None
        if _ip_blocked(ip, allow_loopback):
            raise SSRFBlocked(
                f"URL resolves to a blocked address ({ip_str}); "
                "private/reserved/loopback targets are not allowed"
            )
    return hostname, port
