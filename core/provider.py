"""Provider layer (slide12 PROVIDER): OEM-specific HOW.

A provider turns abstract atomic steps (phone.hold / verify.call_on_hold)
into concrete actions. This is the ONLY layer allowed to contain OEM-specific
implementation (SSH / REST / OEM CLI / Robot / Camera / Protocol / Audio);
Case, Compiler and Executor stay vendor-neutral.

slide11: the SAME abstract step maps to different providers depending on the
backend. API mode drives the device over REST/API; Physical mode drives it via
Robot key presses and verifies with a Camera. The Case never changes.

Contains:
- BaseProvider: abstract interface every provider implements
  (supports_case, supports_backend, run_step, finalize).
- StubProvider: backend-agnostic stub (backend="any") for the base flow.
- ApiStubProvider / PhysicalStubProvider: same capabilities, different HOW,
  selected by operation_mode so one Case can bind to either.

Adding real hardware = add a new BaseProvider subclass; upper layers unchanged.
Used by: executor (calls run_step/finalize) and resolver (picks the provider).
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import Any

from core import provider_registry
from core.models import Capability, TestCase

logger = logging.getLogger(__name__)

# Capabilities shared by the call-oriented stub providers.
_CALL_CAPABILITIES = {
    Capability.BASIC_CALL,
    Capability.HOLD,
    Capability.RESUME,
    Capability.TRANSFER,
    Capability.AUDIO,
}


class BaseProvider(ABC):
    """Implements OEM-specific HOW for a set of actions and verifications."""

    name: str = "base"
    backend: str = "any"  # "api" | "physical" | "any"
    supported_capabilities: set[str] = set()

    def supports_case(self, case: TestCase, config_capabilities: set[str]) -> bool:
        # A provider can run a case only if both the config and the provider
        # cover every capability the case requires.
        required = set(case.required_capabilities)
        return required.issubset(config_capabilities) and required.issubset(self.supported_capabilities)

    def supports_backend(self, operation_mode: str) -> bool:
        # "any" providers work in every mode; others must match the device mode.
        return self.backend in ("any", operation_mode)

    @abstractmethod
    def run_step(self, case: TestCase, step: dict[str, Any], context: dict[str, Any] | None = None) -> tuple[bool, dict[str, Any]]:
        """Execute one atomic step and return (ok, detail).

        ``context`` carries per-case binding data (e.g. role_numbers) resolved
        from the plan; providers that need a target number read it from here.
        """

    @abstractmethod
    def finalize(self, case: TestCase) -> dict[str, Any]:
        """Return execution final data for the case."""


class _MessageProvider(BaseProvider):
    """Shared stub behaviour; subclasses only supply per-step messages."""

    messages: dict[str, str] = {}

    def run_step(self, case: TestCase, step: dict[str, Any], context: dict[str, Any] | None = None) -> tuple[bool, dict[str, Any]]:
        name = step.get("name", "")
        details = {
            "kind": step.get("kind", ""),
            "name": name,
            "provider": self.name,
            "backend": self.backend,
            "case": case.id,
            "message": self.messages.get(name, f"step '{name}' executed"),
        }
        logger.debug("[%s] %s %s -> %s", self.name, case.id, name, details["message"])
        return True, details

    def finalize(self, case: TestCase) -> dict[str, Any]:
        logger.debug("[%s] finalize %s", self.name, case.id)
        return {
            "case": case.id,
            "provider": self.name,
            "status": "pass",
            "summary": f"{case.name} executed through {self.name}",
        }


class StubProvider(_MessageProvider):
    """Backend-agnostic stub used to validate the flow without real hardware."""

    name = "stub_provider"
    backend = "any"
    supported_capabilities = _CALL_CAPABILITIES
    messages = {
        "phone.dial": "dial command accepted",
        "phone.hold": "call placed on hold",
        "phone.resume": "call resumed",
        "phone.transfer": "call transferred",
        "phone.answer": "call answered",
        "device.reboot": "device rebooted",
    }


class ApiStubProvider(_MessageProvider):
    """API-mode HOW: drives the device over REST and verifies via API state."""

    name = "api_provider"
    backend = "api"
    supported_capabilities = _CALL_CAPABILITIES
    messages = {
        "phone.dial": "REST POST /calls (dial)",
        "phone.answer": "REST POST /calls/{id}/answer",
        "phone.hold": "REST POST /calls/{id}/hold",
        "phone.resume": "REST POST /calls/{id}/resume",
        "phone.transfer": "REST POST /calls/{id}/transfer",
        "device.reboot": "REST POST /system/reboot",
        "verify.call_connected": "API state == CONNECTED",
        "verify.call_on_hold": "API state == HELD",
    }


class PhysicalStubProvider(_MessageProvider):
    """Physical-mode HOW: Robot presses keys, Camera verifies the screen."""

    name = "physical_provider"
    backend = "physical"
    supported_capabilities = _CALL_CAPABILITIES
    messages = {
        "phone.dial": "Robot dials number on keypad",
        "phone.answer": "Robot presses Answer key",
        "phone.hold": "Robot presses Hold key",
        "phone.resume": "Robot presses Resume key",
        "phone.transfer": "Robot presses Transfer key",
        "device.reboot": "Power cycle via controlled outlet",
        "verify.call_connected": "Camera reads 'Connected' on screen",
        "verify.call_on_hold": "Camera reads 'On Hold' on screen",
    }


# Register the neutral stubs so the Resolver/CLI source providers from the
# registry (slide11/12) instead of hardcoding a list.
provider_registry.register(StubProvider)
provider_registry.register(ApiStubProvider)
provider_registry.register(PhysicalStubProvider)
