"""ALE-700A OEM provider: Active URI HOW.

Implements the Provider-layer HOW for the ALE-700A DeskPhone using its
Active URI remote-control interface. An abstract atomic step such as
``phone.hold`` is translated into an HTTP GET of

    /cgi-bin/ConfigManApp.com?key=F_HOLD

per "ALE-700A Action URL and Active URI Specifications" (sections 3.4-3.6).
This module is the ONLY place ALE-700A specifics live; Case / Compiler /
Executor stay vendor-neutral.

The HTTP sender is injectable so the step-to-key mapping can be exercised
without a live phone. With no base URL and no injected sender the client runs
in dry-run mode and records the exact Active URI it would send, mirroring the
stub providers. A real deployment passes a base URL (and a secret reference for
Basic auth) to drive a physical phone.
"""
from __future__ import annotations

import base64
import logging
import os
from typing import Any, Callable
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from core.models import Capability, TestCase
from core.provider import BaseProvider
from oem.ale700a.action_url import ActionUrlListener

logger = logging.getLogger(__name__)

# Fixed CGI path the phone parses as an Active URI instruction (doc 3.5).
ACTIVE_URI_PATH = "/cgi-bin/ConfigManApp.com"

# Abstract atomic action -> Active URI key sequence template (doc 3.4).
# {number} is substituted with the target number for dial / transfer.
ACTION_KEYS: dict[str, str] = {
    "phone.dial": "SPEAKER;{number};ENTER",
    "phone.answer": "OK",
    "phone.hold": "F_HOLD",
    "phone.resume": "F_HOLD",  # F_HOLD toggles hold / release (doc 3.4)
    "phone.transfer": "F_TRANSFER;{number};OK",
    "device.reboot": "Reboot",
}

# Abstract verification -> Action URL event the phone reports (doc 2.4).
# The listener confirms real device state instead of mere command acceptance.
VERIFY_EVENTS: dict[str, str] = {
    "verify.call_connected": "call_established",
    "verify.call_on_hold": "call_hold",
    "verify.registered": "registration_succeeded",
    "verify.initialized": "setup_completed",
}

# Sender contract: (url, headers) -> (ok, http_status).
Sender = Callable[[str, dict[str, str]], tuple[bool, int]]


class ActiveUriClient:
    """Builds and sends ALE-700A Active URI HTTP GET commands."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        username: str = "admin",
        secret_ref: str | None = None,
        sender: Sender | None = None,
        timeout: int = 10,
    ) -> None:
        # No base_url and no sender => dry-run: record the URL, send nothing.
        self.base_url = base_url.rstrip("/") if base_url else None
        self.username = username
        self.secret_ref = secret_ref
        self._sender = sender
        self.timeout = timeout

    def build_url(self, key_sequence: str) -> str:
        base = self.base_url or "http://<phone-ip>"
        return f"{base}{ACTIVE_URI_PATH}?key={key_sequence}"

    def _auth_header(self) -> dict[str, str]:
        # Password is read from the environment via the secret reference; it is
        # never stored in config or embedded in the URL (avoids leaking creds).
        password = os.environ.get(self.secret_ref, "") if self.secret_ref else ""
        if not password:
            return {}
        token = base64.b64encode(f"{self.username}:{password}".encode()).decode()
        return {"Authorization": f"Basic {token}"}

    def send(self, key_sequence: str) -> tuple[bool, dict[str, Any]]:
        url = self.build_url(key_sequence)
        detail: dict[str, Any] = {"url": url, "key": key_sequence}
        if self.base_url is None and self._sender is None:
            detail["mode"] = "dry-run"
            logger.debug("[ale700a] dry-run %s", url)
            return True, detail

        sender = self._sender or self._http_get
        ok, status = sender(url, self._auth_header())
        detail["mode"] = "live"
        detail["http_status"] = status
        logger.debug("[ale700a] sent %s -> %s (%s)", url, status, ok)
        return ok, detail

    def _http_get(self, url: str, headers: dict[str, str]) -> tuple[bool, int]:
        req = urllib_request.Request(url, headers=headers, method="GET")
        try:
            with urllib_request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - fixed OEM CGI endpoint
                return 200 <= resp.status < 300, resp.status
        except HTTPError as exc:
            return False, exc.code
        except URLError as exc:
            logger.warning("[ale700a] request failed: %s", exc)
            return False, 0


class Ale700aProvider(BaseProvider):
    """Drives the ALE-700A over Active URI (doc section 3)."""

    name = "ale700a_active_uri"
    backend = "active_uri"
    supported_capabilities = {
        Capability.BASIC_CALL,
        Capability.HOLD,
        Capability.RESUME,
        Capability.TRANSFER,
        Capability.AUDIO,
    }

    def __init__(
        self,
        client: ActiveUriClient | None = None,
        default_number: str = "",
        listener: ActionUrlListener | None = None,
        verify_timeout: float = 10.0,
    ) -> None:
        self.client = client or ActiveUriClient()
        # Number used when an action template needs a dial / transfer target.
        self.default_number = default_number
        # Optional Action URL listener; when set, verifications wait for the
        # phone's real status callback instead of only confirming acceptance.
        self.listener = listener
        self.verify_timeout = verify_timeout

    def run_step(self, case: TestCase, step: dict[str, Any]) -> tuple[bool, dict[str, Any]]:
        name = step.get("name", "")
        kind = step.get("kind", "")

        if kind == "ACTION":
            template = ACTION_KEYS.get(name)
            if template is None:
                logger.error("[ale700a] unsupported action '%s'", name)
                return False, {
                    "kind": kind,
                    "name": name,
                    "provider": self.name,
                    "case": case.id,
                    "error": f"unsupported Active URI action '{name}'",
                }
            key_sequence = template.format(number=self.default_number)
            ok, detail = self.client.send(key_sequence)
            detail.update(
                {
                    "kind": kind,
                    "name": name,
                    "provider": self.name,
                    "backend": self.backend,
                    "case": case.id,
                }
            )
            return ok, detail

        # VERIFICATION: with a listener, wait for the real Action URL callback
        # (closed loop). Without one, fall back to confirming command acceptance.
        expected_event = VERIFY_EVENTS.get(name)
        if self.listener is not None and expected_event is not None:
            timeout = step.get("timeout") or self.verify_timeout
            received = self.listener.wait_for_event(expected_event, timeout=timeout)
            base = {
                "kind": kind,
                "name": name,
                "provider": self.name,
                "backend": self.backend,
                "case": case.id,
                "expected_event": expected_event,
            }
            if received is None:
                logger.warning("[ale700a] timed out waiting for Action URL '%s'", expected_event)
                return False, {**base, "message": f"timed out waiting for Action URL '{expected_event}'"}
            return True, {
                **base,
                "message": f"Action URL '{expected_event}' received",
                "event_params": received.params,
            }

        return True, {
            "kind": kind,
            "name": name,
            "provider": self.name,
            "backend": self.backend,
            "case": case.id,
            "message": "accepted via Active URI (state verification pending Action URL feedback)",
        }

    def finalize(self, case: TestCase) -> dict[str, Any]:
        logger.debug("[ale700a] finalize %s", case.id)
        return {
            "case": case.id,
            "provider": self.name,
            "status": "pass",
            "summary": f"{case.name} executed via ALE-700A Active URI",
        }
