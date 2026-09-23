"""Generic OEM callback listener template.

This is intentionally small and intentionally generic. Real OEM integrations
usually replace the callback parsing logic and event names with vendor-specific
values.
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


@dataclass
class ActionEvent:
    event: str
    params: dict[str, str] = field(default_factory=dict)
    path: str = ""
    received_at: float = 0.0
    consumed: bool = False


def resolve_event_name(path: str, params: dict[str, str]) -> str:
    if "event" in params:
        return params["event"]
    segment = path.rstrip("/").rsplit("/", 1)[-1]
    return segment.split(".")[0] if segment else ""


def _make_handler(record: Callable[[str, dict[str, str]], None]):
    class _ActionUrlHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            record(parsed.path, params)
            self.send_response(200)
            self.send_header("Content-Type", "text/plain")
            self.end_headers()
            self.wfile.write(b"OK")

        def log_message(self, *_args) -> None:
            pass

    return _ActionUrlHandler


class ActionUrlListener:
    """Minimal HTTP listener for OEM callback events."""

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        on_event: Callable[[ActionEvent], None] | None = None,
    ) -> None:
        self._host = host
        self._port = port
        self._on_event = on_event
        self._events: list[ActionEvent] = []
        self._cond = threading.Condition()
        self._server: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None

    def _record(self, path: str, params: dict[str, str]) -> None:
        event = ActionEvent(
            event=resolve_event_name(path, params),
            params=params,
            path=path,
            received_at=time.time(),
        )
        with self._cond:
            self._events.append(event)
            self._cond.notify_all()
        logger.info("[template-action-url] received %s %s", event.event, params)
        if self._on_event is not None:
            self._on_event(event)

    @property
    def port(self) -> int:
        return self._server.server_address[1] if self._server else self._port

    @property
    def url(self) -> str:
        return f"http://{self._host}:{self.port}"

    def start(self) -> "ActionUrlListener":
        self._server = ThreadingHTTPServer((self._host, self._port), _make_handler(self._record))
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()
        logger.info("[template-action-url] listening on %s", self.url)
        return self

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    @property
    def events(self) -> list[ActionEvent]:
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
    ) -> ActionEvent | None:
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
