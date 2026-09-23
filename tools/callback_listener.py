"""Vendor-neutral HTTP callback listener.

Many devices report status by issuing an HTTP GET to a console/callback URL.
This is the generic mechanism for that: a small HTTP server that records each
callback as a ``CallbackEvent`` and lets a caller block until an expected event
arrives. It is transport only and holds no OEM-specific vocabulary; an OEM
integration supplies its own event-name resolution and event names.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable
from urllib.parse import parse_qs, urlparse

logger = logging.getLogger(__name__)

# Resolve an event name from (path, query params); OEMs can override the rule.
EventResolver = Callable[[str, dict[str, str]], str]


@dataclass
class CallbackEvent:
    """One HTTP callback received from a device."""

    event: str
    params: dict[str, str] = field(default_factory=dict)
    path: str = ""
    received_at: float = 0.0
    consumed: bool = False


def default_event_resolver(path: str, params: dict[str, str]) -> str:
    """Neutral default: the ``event`` query param, else the last path segment."""
    if "event" in params:
        return params["event"]
    segment = path.rstrip("/").rsplit("/", 1)[-1]
    return segment.split(".")[0] if segment else ""


def _make_handler(record: Callable[[str, dict[str, str]], None]):
    class _CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802 - required by BaseHTTPRequestHandler
            parsed = urlparse(self.path)
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            record(parsed.path, params)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, *_args) -> None:
            # Silence the default stderr access log; callers log via on_event.
            pass

    return _CallbackHandler


class CallbackListener:
    """HTTP server that records device callbacks and waits on them."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        on_event: Callable[[CallbackEvent], None] | None = None,
        event_resolver: EventResolver = default_event_resolver,
    ) -> None:
        self._host = host
        self._port = port
        self._on_event = on_event
        self._resolve = event_resolver
        self._events: list[CallbackEvent] = []
        self._cond = threading.Condition()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _record(self, path: str, params: dict[str, str]) -> None:
        event = CallbackEvent(
            event=self._resolve(path, params),
            params=params,
            path=path,
            received_at=time.time(),
        )
        with self._cond:
            self._events.append(event)
            self._cond.notify_all()
        logger.info("[callback] received %s %s", event.event, params)
        if self._on_event is not None:
            self._on_event(event)

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else self._port

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self.port}"

    def start(self) -> "CallbackListener":
        self._server = ThreadingHTTPServer((self._host, self._port), _make_handler(self._record))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("[callback] listening on %s", self.url)
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def __enter__(self) -> "CallbackListener":
        return self.start()

    def __exit__(self, *_exc) -> None:
        self.stop()

    @property
    def events(self) -> list[CallbackEvent]:
        with self._cond:
            return list(self._events)

    def clear(self) -> None:
        with self._cond:
            self._events.clear()

    def wait_for_event(
        self,
        event: str,
        timeout: float = 10.0,
        match: dict[str, str] | None = None,
    ) -> CallbackEvent | None:
        """Block until an unconsumed matching event arrives; consume and return it."""
        deadline = time.time() + timeout
        with self._cond:
            while True:
                for candidate in self._events:
                    if candidate.consumed or candidate.event != event:
                        continue
                    if match and any(candidate.params.get(k) != v for k, v in match.items()):
                        continue
                    candidate.consumed = True
                    return candidate
                remaining = deadline - time.time()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
