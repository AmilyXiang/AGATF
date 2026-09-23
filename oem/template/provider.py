"""Generic OEM provider template.

Copy this file and replace the vendor-specific mapping with your own device
protocol.
"""
from __future__ import annotations

import logging
from typing import Any

from core.models import Capability, TestCase
from core.provider import BaseProvider
from oem.template.action_url import ActionUrlListener

logger = logging.getLogger(__name__)


class ExampleProvider(BaseProvider):
    """Minimal provider skeleton for a new OEM implementation."""

    name = "template_provider"
    backend = "template"
    supported_capabilities = {
        Capability.BASIC_CALL,
        Capability.HOLD,
        Capability.RESUME,
    }

    def __init__(
        self,
        base_url: str | None = None,
        listener: ActionUrlListener | None = None,
        verify_timeout: float = 10.0,
    ) -> None:
        self.base_url = base_url.rstrip("/") if base_url else None
        self.listener = listener
        self.verify_timeout = verify_timeout

    def run_step(
        self,
        case: TestCase,
        step: dict[str, Any],
        context: dict[str, Any] | None = None,
    ) -> tuple[bool, dict[str, Any]]:
        name = step.get("name", "")
        kind = step.get("kind", "")

        if kind == "ACTION":
            # Replace this with your vendor-specific command map.
            detail = {
                "kind": kind,
                "name": name,
                "provider": self.name,
                "backend": self.backend,
                "case": case.id,
                "url": self.base_url,
                "message": "ACTION sent (replace with device-specific mapping)",
            }
            return True, detail

        if kind == "VERIFICATION":
            if self.listener is not None:
                # Replace with vendor-specific event names.
                expected = "device_event"
                received = self.listener.wait_for_event(expected, timeout=self.verify_timeout)
                if received is None:
                    return False, {
                        "kind": kind,
                        "name": name,
                        "provider": self.name,
                        "backend": self.backend,
                        "case": case.id,
                        "expected_event": expected,
                        "message": f"timed out waiting for event '{expected}'",
                    }
                return True, {
                    "kind": kind,
                    "name": name,
                    "provider": self.name,
                    "backend": self.backend,
                    "case": case.id,
                    "expected_event": expected,
                    "message": f"received event '{expected}'",
                    "event_params": received.params,
                }

            return True, {
                "kind": kind,
                "name": name,
                "provider": self.name,
                "backend": self.backend,
                "case": case.id,
                "message": "verification passed without OEM callback feedback",
            }

        return False, {
            "kind": kind,
            "name": name,
            "provider": self.name,
            "backend": self.backend,
            "case": case.id,
            "message": "unsupported step type",
        }

    def finalize(self, case: TestCase) -> dict[str, Any]:
        logger.debug("[template-provider] finalize %s", case.id)
        return {
            "case": case.id,
            "provider": self.name,
            "status": "pass",
            "summary": f"{case.name} executed via template provider",
        }
