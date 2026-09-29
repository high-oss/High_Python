# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""A real HTTP server on a random port, stdlib only. Tests assert on actual
exchanges rather than a mocked transport, so a change in how the SDK builds
requests is caught rather than asserted around. Mirrors
high-sdk-node/tests/server.ts.
"""

from __future__ import annotations

import json
import ssl
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, List, Optional

# A throwaway, loopback-only self-signed certificate (CN=localhost, SAN
# 127.0.0.1/localhost), checked in for the instrument list's https-only
# safety-gate tests — the one thing this suite cannot exercise against a
# plain http.server. Never used for anything but 127.0.0.1 in a test
# process; regenerate with:
#   openssl req -x509 -newkey rsa:2048 -keyout tls-key.pem -out tls-cert.pem \
#     -days 3650 -nodes -subj /CN=localhost \
#     -addext "subjectAltName=DNS:localhost,IP:127.0.0.1"
_FIXTURES = Path(__file__).resolve().parent / "fixtures"
TLS_CERT = _FIXTURES / "tls-cert.pem"
TLS_KEY = _FIXTURES / "tls-key.pem"


@dataclass
class ReceivedRequest:
    method: str
    url: str
    headers: dict
    body: str


class TestServer:
    def __init__(
        self,
        httpd: ThreadingHTTPServer,
        requests: List[ReceivedRequest],
        thread: threading.Thread,
        scheme: str = "http",
    ):
        self._httpd = httpd
        self._thread = thread
        self.requests = requests
        port = httpd.server_address[1]
        self.base_url = f"{scheme}://127.0.0.1:{port}"
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


def start_server(handler: Handler, *, tls: bool = False) -> TestServer:
    """``tls=True`` wraps the same real server in loopback TLS using the
    checked-in self-signed fixture, for the instrument list's https-only
    safety gate — the client must be built with a transport that skips
    certificate verification (``httpx.Client(verify=False)``) to talk to
    it, exactly like any client deliberately trusting a pinned test cert."""
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
    if tls:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(certfile=str(TLS_CERT), keyfile=str(TLS_KEY))
        httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    return TestServer(httpd, requests, thread, scheme="https" if tls else "http")


def send_json(handler: BaseHTTPRequestHandler, status: int, payload) -> None:
    body = json.dumps(payload).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def send_text(handler: BaseHTTPRequestHandler, status: int, content_type: str, text: str) -> None:
    """Raw-body response — used for the instrument list's CSV downloads,
    which are not JSON envelopes."""
    body = text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)
