# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""A real HTTP server on a random port, stdlib only. Tests assert on actual
exchanges rather than a mocked transport, so a change in how the SDK builds
requests is caught rather than asserted around. Mirrors
high-sdk-node/tests/server.ts.
"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Callable, List, Optional


@dataclass
class ReceivedRequest:
    method: str
    url: str
    headers: dict
    body: str


class TestServer:
    def __init__(self, httpd: ThreadingHTTPServer, requests: List[ReceivedRequest], thread: threading.Thread):
        self._httpd = httpd
        self._thread = thread
        self.requests = requests
        port = httpd.server_address[1]
        self.base_url = f"http://127.0.0.1:{port}"
        self._closed = False

    def close(self) -> None:
        # Idempotent: a suite whose teardown closes a server shared across
        # several tests would otherwise fail for any test that never started
        # one, or double-closed one that was already torn down.
        if self._closed:
            return
        self._closed = True
        self._httpd.shutdown()
        self._httpd.server_close()
        self._thread.join(timeout=5)


Handler = Callable[[BaseHTTPRequestHandler, int], None]


def start_server(handler: Handler) -> TestServer:
    requests: List[ReceivedRequest] = []

    class _RequestHandler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _dispatch(self) -> None:
            length = int(self.headers.get("Content-Length") or 0)
            body = self.rfile.read(length).decode("utf-8") if length else ""
            index = len(requests)
            requests.append(
                ReceivedRequest(
                    method=self.command,
                    url=self.path,
                    headers={k.lower(): v for k, v in self.headers.items()},
                    body=body,
                )
            )
            handler(self, index)

        def do_GET(self) -> None: self._dispatch()  # noqa: N802

        def do_POST(self) -> None: self._dispatch()  # noqa: N802

        def do_PATCH(self) -> None: self._dispatch()  # noqa: N802

        def do_DELETE(self) -> None: self._dispatch()  # noqa: N802

        def do_PUT(self) -> None: self._dispatch()  # noqa: N802

        def log_message(self, format: str, *args) -> None:  # noqa: A002
            pass  # Silence stderr access logging during tests.

    httpd = ThreadingHTTPServer(("127.0.0.1", 0), _RequestHandler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return TestServer(httpd, requests, thread)


def send_json(handler: BaseHTTPRequestHandler, status: int, payload) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
