"""Vendor-neutral HTTP transport tool.

A thin GET client (urllib) shared by OEM providers and device CGI interfaces.
Handles Basic-auth headers, optional TLS-verification bypass for self-signed
device certificates, and timeouts. Contains no OEM-specific behaviour.
"""
from __future__ import annotations

import base64
import logging
import ssl
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

logger = logging.getLogger(__name__)


def basic_auth_header(username: str, password: str) -> dict[str, str]:
    """Build an HTTP Basic Authorization header; empty when no password."""
    if not password:
        return {}
    token = base64.b64encode(f"{username}:{password}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


class HttpClient:
    """Minimal HTTP GET client returning (ok, status_code)."""

    def __init__(self, *, timeout: int = 10, verify_tls: bool = True) -> None:
        self.timeout = timeout
        # Devices ship self-signed certs; allow opt-in bypass over HTTPS.
        self.verify_tls = verify_tls

    def get(self, url: str, headers: dict[str, str] | None = None) -> tuple[bool, int]:
        req = urllib_request.Request(url, headers=headers or {}, method="GET")
        context = None if self.verify_tls else ssl._create_unverified_context()
        try:
            with urllib_request.urlopen(req, timeout=self.timeout, context=context) as resp:  # noqa: S310 - caller-provided device endpoint
                return 200 <= resp.status < 300, resp.status
        except HTTPError as exc:
            return False, exc.code
        except URLError as exc:
            logger.warning("http get failed: %s", exc)
            return False, 0
