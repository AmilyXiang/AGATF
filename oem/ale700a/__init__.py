"""ALE-700A OEM integration: Active URI control + Action URL feedback.

Public surface:
- ``Ale700aProvider`` / ``ActiveUriClient``: drive the phone via Active URI (doc section 3).
- ``ActionUrlListener`` / ``ActionEvent``: receive phone status callbacks (doc section 2).
"""
from oem.ale700a.action_url import ActionEvent, ActionUrlListener, resolve_event_name
from oem.ale700a.live import build_live_provider
from oem.ale700a.provider import (
    ACTION_KEYS,
    ACTIVE_URI_PATH,
    VERIFY_EVENTS,
    ActiveUriClient,
    Ale700aProvider,
)
from core import provider_registry

# Absorb this OEM by registering it (slide13/16): the CLI never imports it.
provider_registry.register(
    Ale700aProvider,
    operation_mode="active_uri",
    live_factory=build_live_provider,
)

__all__ = [
    "ActionEvent",
    "ActionUrlListener",
    "resolve_event_name",
    "ACTION_KEYS",
    "ACTIVE_URI_PATH",
    "VERIFY_EVENTS",
    "ActiveUriClient",
    "Ale700aProvider",
    "build_live_provider",
]
