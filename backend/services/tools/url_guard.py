"""
Unconditional SSRF & Sidecar Port Guard (SPEC-05).

Protects agent HTTP/web tools from accessing:
- Loopback addresses (127.0.0.0/8, ::1, localhost)
- Link-local / Cloud Instance Metadata (169.254.0.0/16, fe80::/10, metadata.google.internal)
- Unspecified addresses (0.0.0.0, ::)
- The ContextuAI Solo sidecar port (default 18741) on any interface

Allows standard LAN addresses (192.168.x.x, 10.x.x.x, 172.16.x.x) unless they
target the sidecar port, so users can connect to home-lab APIs on their LAN.
"""

from __future__ import annotations

import ipaddress
import logging
import os
import socket
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

SIDECAR_PORT = int(os.getenv("PORT", "18741"))

_BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "ip6-localhost",
    "ip6-loopback",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}


class SSRFBlockedError(ValueError):
    """Raised when a URL targets a forbidden loopback, metadata, or sidecar endpoint."""


def _check_ip(ip_str: str) -> None:
    """Validate a single IP address string against SSRF blocklist rules."""
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError as exc:
        raise SSRFBlockedError(f"Invalid IP address: {ip_str}") from exc

    if isinstance(addr, ipaddress.IPv6Address) and addr.ipv4_mapped is not None:
        addr = addr.ipv4_mapped

    if addr.is_loopback:
        raise SSRFBlockedError(f"Blocked loopback address: {ip_str}")
    if addr.is_link_local:
        raise SSRFBlockedError(f"Blocked link-local / cloud metadata address: {ip_str}")
    if addr.is_unspecified:
        raise SSRFBlockedError(f"Blocked unspecified address: {ip_str}")
    if addr.is_multicast:
        raise SSRFBlockedError(f"Blocked multicast address: {ip_str}")


def assert_url_allowed(url: str) -> None:
    """Raise ``SSRFBlockedError`` if ``url`` is unsafe to fetch."""
    if not url or not isinstance(url, str):
        raise SSRFBlockedError("Empty or invalid URL")

    parsed = urlparse(url.strip())
    if parsed.scheme.lower() not in ("http", "https"):
        raise SSRFBlockedError(f"Unsupported URL scheme: {parsed.scheme!r}")

    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if not hostname:
        raise SSRFBlockedError("Missing hostname in URL")

    try:
        port = parsed.port
    except ValueError as exc:
        raise SSRFBlockedError(f"Invalid port in URL: {url}") from exc

    sidecar_port = int(os.getenv("PORT", str(SIDECAR_PORT)))
    if port == sidecar_port:
        raise SSRFBlockedError(
            f"Access to ContextuAI sidecar port ({sidecar_port}) is forbidden"
        )

    if hostname in _BLOCKED_HOSTNAMES or hostname.endswith(".localhost"):
        raise SSRFBlockedError(f"Blocked hostname: {hostname}")

    # Direct IP literal check before DNS resolution
    try:
        ipaddress.ip_address(hostname)
        _check_ip(hostname)
        return
    except ValueError:
        pass

    # Resolve hostname via DNS and inspect every returned address
    try:
        addr_infos = socket.getaddrinfo(
            hostname,
            port or (443 if parsed.scheme.lower() == "https" else 80),
            proto=socket.IPPROTO_TCP,
        )
    except socket.gaierror as exc:
        raise SSRFBlockedError(f"Could not resolve hostname {hostname!r}: {exc}") from exc

    if not addr_infos:
        raise SSRFBlockedError(f"No DNS records resolved for {hostname!r}")

    for info in addr_infos:
        sockaddr = info[4]
        if sockaddr and len(sockaddr) >= 1:
            _check_ip(str(sockaddr[0]))


def is_url_allowed(url: str) -> bool:
    """Return True if ``url`` passes SSRF validation, False otherwise."""
    try:
        assert_url_allowed(url)
        return True
    except Exception as exc:
        logger.warning("URL blocked by url_guard (%s): %s", url, exc)
        return False
