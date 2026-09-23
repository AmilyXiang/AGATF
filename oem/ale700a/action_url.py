"""ALE-700A Action URL listener (doc section 2).

The phone reports every status change with an HTTP GET to a console URL, e.g.

    /action?event=call_established&mac=00a859ebf35b&cid=3&dt=20251131045

The listening mechanism is vendor-neutral, so it lives in
``tools.callback_listener``; this module only re-exports it under the ALE-700A
"Action URL" names the provider and tests use. The default event resolver
(``event`` query param, else last path segment) already matches how the
ALE-700A console reports events.
"""
from __future__ import annotations

from tools.callback_listener import (
    CallbackEvent as ActionEvent,
    CallbackListener as ActionUrlListener,
    default_event_resolver as resolve_event_name,
)

__all__ = ["ActionEvent", "ActionUrlListener", "resolve_event_name"]

