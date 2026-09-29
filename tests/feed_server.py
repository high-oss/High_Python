# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""A real local WebSocket server, on its own background thread with its own
asyncio event loop — the datafeed's equivalent of ``tests/server.py``. Tests
script its behaviour (the auth acknowledgement, scripted tick pushes, a
mid-session drop for the reconnect test) through thread-safe handles, so the
feed client under test is always talking to a real socket, never a mock —
and always on a thread of its own, so it never shares (and cannot deadlock
against) whichever loop/thread the client under test happens to run on,
sync (``HighFeed``, its own background thread) or async (``AsyncHighFeed``,
the pytest-asyncio loop).
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any, Callable, List, Optional

import websockets
from websockets.exceptions import ConnectionClosed


class FeedTestServer:
    port: int
    url: str
    received: List[Any]

    def send_to_all(self, payload: Any) -> None:
        """Pushes one JSON-encodable payload to every currently-connected
        socket. Callable from any thread."""
        asyncio.run_coroutine_threadsafe(self._send_to_all(payload), self._loop).result(timeout=5)

    def drop_all(self) -> None:
        """Forcibly closes every open connection — a transport failure, not
        a graceful close — without stopping the server itself, so a
        reconnect can be observed landing on the same server. Blocks the
        calling thread — safe from a thread other than the client under
        test's own event loop (a plain ``def`` test driving a threaded
        ``HighFeed``). See :meth:`drop_all_async` for a client that shares
        this thread's loop (``AsyncHighFeed`` under pytest-asyncio): the
        WebSocket closing handshake needs the client's loop to keep running
        while it completes, and blocking that loop's own thread here would
        deadlock against it."""
        asyncio.run_coroutine_threadsafe(self._drop_all(), self._loop).result(timeout=5)

    async def drop_all_async(self) -> None:
        """Same effect as :meth:`drop_all`, but awaitable from a coroutine
        running on another loop without blocking that loop while the close
        handshake with the client under test completes."""
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(self._drop_all(), self._loop))

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        try:
            asyncio.run_coroutine_threadsafe(self._shutdown(), self._loop).result(timeout=5)
        except Exception:  # noqa: BLE001 — best-effort teardown
            pass
        self._loop.call_soon_threadsafe(self._loop.stop)
        self._thread.join(timeout=5)

    async def _send_to_all(self, payload: Any) -> None:
        text = json.dumps(payload)
        for ws in list(self._connections):
            await ws.send(text)

    async def _drop_all(self) -> None:
        # 1006 (abnormal closure) is reserved and cannot be sent on the wire
        # — 1011 (internal error) is a valid code that still lands the
        # client in the same place: an unexpected closure it did not
        # initiate itself, which is exactly what a transport failure needs
        # to look like for the reconnect-and-resubscribe test.
        for ws in list(self._connections):
            await ws.close(code=1011, reason="test-induced drop")

    async def _shutdown(self) -> None:
        for ws in list(self._connections):
            await ws.close()
        self._server.close()
        await self._server.wait_closed()


# frame -> the auth acknowledgement to send back (a dict, per the plan's
# Phase 0 "Settled" auth ack shape).
AuthResponder = Callable[[dict], Any]
# (server, websocket, message) -> None, or an awaitable. Called for every
# non-"cn" frame received, e.g. to script per-test subscribe behaviour.
FrameHook = Callable[["FeedTestServer", Any, Any], Any]


def start_feed_server(*, auth_response: AuthResponder, on_frame: Optional[FrameHook] = None) -> FeedTestServer:
    server = FeedTestServer.__new__(FeedTestServer)
    server.received = []
    server._connections: List[Any] = []
    server._closed = False

    async def _handler(websocket, *_legacy_path) -> None:
        server._connections.append(websocket)
        try:
            async for raw in websocket:
                message = json.loads(raw)
                server.received.append(message)
                if isinstance(message, dict) and message.get("type") == "cn":
                    await websocket.send(json.dumps(auth_response(message)))
                elif on_frame is not None:
                    result = on_frame(server, websocket, message)
                    if asyncio.iscoroutine(result):
                        await result
        except ConnectionClosed:
            pass
        finally:
            if websocket in server._connections:
                server._connections.remove(websocket)

    ready = threading.Event()

    def _run() -> None:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        server._loop = loop

        async def _main() -> None:
            srv = await websockets.serve(_handler, "127.0.0.1", 0)
            server._server = srv
            server.port = srv.sockets[0].getsockname()[1]
            server.url = f"ws://127.0.0.1:{server.port}"

        loop.run_until_complete(_main())
        ready.set()
        loop.run_forever()

    thread = threading.Thread(target=_run, name="feed-test-server", daemon=True)
    thread.start()
    ready.wait()
    server._thread = thread
    return server


def ok_ack(max_scrip_per_conn: int = 1000, max_scrip_per_req: int = 500) -> dict:
    """The auth ack for a successful ``cn`` — datafeed plan, Phase 0
    "Settled"."""
    return {
        "stat": "Ok", "type": "cn", "msg": "successful", "stCode": 200,
        "maxScripPerConn": max_scrip_per_conn, "maxScripPerReq": max_scrip_per_req, "sType": "v2.0",
    }


def not_ok_ack(st_code: int, msg: str) -> dict:
    return {"stat": "NotOk", "type": "cn", "msg": msg, "stCode": st_code}
