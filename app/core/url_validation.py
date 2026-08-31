"""
app/core/url_validation.py
──────────────────────────
SSRF-safe webhook URL validator.

Blocks non-HTTP/S schemes, loopback, RFC1918 private ranges,
link-local addresses, cloud metadata endpoints, and embedded credentials.

DNS is resolved at validation time so that hostnames that map to private
IPs are also caught (basic DNS-rebinding mitigation at the application layer).
"""

from __future__ import annotations

import ipaddress
import logging
import socket
from urllib.parse import urlparse

logger = logging.getLogger("kariyer.url_validation")


_ALLOWED_SCHEMES = frozenset({"http", "https"})


_BLOCKED_HOSTNAMES: frozenset[str] = frozenset(
    {
        "localhost",
        "metadata.google.internal",
        "169.254.169.254",
        "fd00::ec2",
        "instance-data",
        "computeMetadata",
    }
)

_BLOCKED_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("100.64.0.0/10"),
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("240.0.0.0/4"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
    ipaddress.ip_network("::ffff:0:0/96"),
]


class SSRFError(ValueError):
    """Raised when a URL fails webhook-safety validation."""


def _is_ip_blocked(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
    except ValueError:
        return True

    return any(addr in net for net in _BLOCKED_NETWORKS)


def validate_target_url(url: str, *, resolve_dns: bool = True) -> str:
    """
    Validate that *url* is safe to use as a webhook / callback target.

    Checks performed (in order):

    1. Input must be a non-empty string.
    2. URL must parse without error.
    3. Scheme must be ``http`` or ``https``.
    4. URL must not contain embedded credentials (``user:pass@host``).
    5. Hostname must not appear in the blocked-hostname set.
    6. If the hostname is a bare IP, it must not be in a blocked range.
    7. If *resolve_dns* is True, the hostname is resolved via DNS and every
       returned IP is checked against the blocked-network list.

    Args:
        url:         The caller-supplied URL string.
        resolve_dns: Resolve the hostname and validate the resulting IPs.
                     Set to ``False`` only in unit tests where DNS is mocked.

    Returns:
        The validated URL string (whitespace-stripped, otherwise unchanged).

    Raises:
        SSRFError:  With a safe, user-facing message describing the rejection
                    reason. Never includes internal IP addresses in the message.
    """
    if not url or not isinstance(url, str):
        raise SSRFError("target_url must be a non-empty string.")

    url = url.strip()

    try:
        parsed = urlparse(url)
    except Exception as exc:
        raise SSRFError("target_url is not a valid URL.") from exc

    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise SSRFError(
            f"URL scheme '{parsed.scheme}' is not permitted. Only 'http' and 'https' are allowed."
        )

    hostname = parsed.hostname
    if not hostname:
        raise SSRFError("target_url must include a valid hostname.")

    if parsed.username or parsed.password:
        raise SSRFError("target_url must not contain embedded credentials.")

    if hostname in _BLOCKED_HOSTNAMES:
        raise SSRFError(
            "The supplied target URL hostname is not permitted as a webhook destination."
        )

    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        pass
    else:
        if _is_ip_blocked(hostname):
            raise SSRFError(
                "target_url points to a private or reserved IP address, which is not permitted."
            )
        return url

    if resolve_dns:
        try:
            results = socket.getaddrinfo(hostname, None)
        except OSError as exc:
            raise SSRFError(f"Could not resolve hostname '{hostname}': {exc}") from exc

        for result in results:
            ip = result[4][0]
            if _is_ip_blocked(ip):
                logger.warning(
                    "SSRF blocked: hostname '%s' resolved to a private IP (IP redacted from log)",
                    hostname,
                )
                raise SSRFError(
                    "target_url resolves to a private or reserved IP address, "
                    "which is not permitted as a webhook destination."
                )

    return url
