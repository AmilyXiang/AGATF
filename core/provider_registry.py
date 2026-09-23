"""Provider registry (slide11 / slide12 RESOLVER).

The design doc says the Resolver decides WHICH provider implements an
Action/Verify based on the device backend (operation_mode), and that a new OEM
is absorbed by adding a Provider - never by editing the CLI/Executor
(slide13 / slide16 decision 4).

This registry is the neutral mechanism for that rule: OEM packages register a
default (dry-run capable) provider factory keyed by nothing, plus an optional
live-provider builder keyed by operation_mode. The CLI/Executor stay free of
any vendor-specific import.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from core.provider import BaseProvider


@dataclass
class LiveProvider:
    """A device-driving provider plus the runtime handles the CLI must manage."""

    provider: "BaseProvider"
    dut_numbers: dict[str, str] = field(default_factory=dict)
    teardown: Callable[[], None] | None = None


DefaultFactory = Callable[[], "BaseProvider"]
LiveFactory = Callable[[dict, dict, dict], LiveProvider]

_DEFAULT_FACTORIES: list[DefaultFactory] = []
_LIVE_FACTORIES: dict[str, LiveFactory] = {}


def register(
    default_factory: DefaultFactory,
    *,
    operation_mode: str | None = None,
    live_factory: LiveFactory | None = None,
) -> None:
    """Register a provider. OEM packages call this on import."""
    _DEFAULT_FACTORIES.append(default_factory)
    if operation_mode is not None and live_factory is not None:
        _LIVE_FACTORIES[operation_mode] = live_factory


def default_providers() -> list["BaseProvider"]:
    """All registered providers, with backend-agnostic ('any') ones last so a
    specific-backend provider always wins provider selection (slide11)."""
    providers = [factory() for factory in _DEFAULT_FACTORIES]
    return sorted(providers, key=lambda p: p.backend == "any")


def build_live_provider(
    operation_mode: str,
    device_data: dict,
    lab_data: dict,
    options: dict,
) -> LiveProvider:
    """Build the live provider for a device backend (operation_mode)."""
    factory = _LIVE_FACTORIES.get(operation_mode)
    if factory is None:
        raise ValueError(f"No live provider registered for operation_mode '{operation_mode}'")
    return factory(device_data, lab_data, options)
