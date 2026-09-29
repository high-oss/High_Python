# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""``AsyncHighFeed`` and ``HighFeed`` — the live datafeed clients, a separate
pair beside ``HighClient``/``AsyncHighClient``, built from the same options.

::

    from high_openapi import AsyncHighFeed

    async def main():
        feed = AsyncHighFeed(access_token=access_token)
        await feed.connect()
        await feed.subscribe_quotes(["NSE@2885"])
        async for event in feed:
            print(event)

::

    from high_openapi import HighFeed

    feed = HighFeed(access_token=access_token)
    feed.add_listener(print)
    feed.connect()
    feed.subscribe_quotes(["NSE@2885"])

**Production only.** ``openapi-feed.high.live`` — there is no sandbox feed,
so a client resolved to the sandbox environment refuses to construct at all
(see ``_reject_sandbox`` below), rather than opening a socket to a host
nothing serves.

**Auth is a gate.** ``connect()`` sends ``{"type":"cn","sessionid":<token>}``
and waits for its acknowledgement before anything else may be sent — no
subscription can race ahead of it (enforced by ``_require_connected``, which
every public method calls first). A ``"stat":"NotOk"`` acknowledgement never
retries and never reconnects, because the server will keep refusing; that
failure propagates straight out of ``connect()``. Reconnection applies only
to a transport failure *after* a successful connect, and always
re-authenticates and fully re-subscribes before the feed is usable again —
see ``_reconnect_with_backoff`` / ``_resubscribe_all``. If a *reconnect*
attempt itself gets a ``NotOk`` (a token that expired mid-session, say), the
same rule applies: no further retries, and the fatal error is delivered to
whoever is consuming events (the async iterator raises it; a sync
``HighFeed``'s pending or next call raises it too).

**Public surface is scrip keys, not feed identifiers.** Quotes and depth
take ordinary HIGH scrip keys and are translated via
``translate.translate_instrument`` (prefix rule; index keys are rejected —
use the index methods). Indices take only keys from the committed index
table, via ``translate.translate_index`` (a non-index key is rejected the
same way). This two-way rejection is deliberate: letting an index key fall
through the quote/depth prefix rule would silently subscribe to a token the
feed does not know (e.g. ``nse_cm|26000``) and just never tick — the
opposite of the loud failure a caller needs.
"""

from __future__ import annotations

import asyncio
import json
import threading
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterable, List, Optional, Tuple, Union

import websockets
from websockets.exceptions import ConnectionClosed

from .._engine import backoff_ms
from ..config import HighClientOptions, ResolvedConfig, resolve_config
from ..logger import redact_body
from . import _protocol, translate
from .errors import HighFeedAuthError, HighFeedError, HighFeedLimitError
from .models import Depth, IndexTick, Quote

__all__ = ["AsyncHighFeed", "HighFeed"]

ScripKeys = Union[str, Iterable[str]]

_STOP = object()

_INVERSE_ROUTE_TAG = {tag: kind for kind, tag in _protocol.ROUTE_TAG.items()}


class _TransportFailure(Exception):
    """Internal signal only: the socket closed (cleanly or not) and the run
    loop must decide, based on whether ``close()`` was ever called, whether
    that means "reconnect" or "stop"."""


def _reject_sandbox(config: ResolvedConfig) -> None:
    if config.environment == "sandbox":
        raise ValueError(
            'There is no sandbox datafeed: openapi-feed.high.live is production-only. '
            'Construct HighFeed/AsyncHighFeed with environment="production" (the default) '
            "or without an environment at all — never with environment=\"sandbox\"."
        )
    if config.ws_base_url is None:
        # Defensive: should be unreachable given _reject_sandbox already
        # covers the only environment ENVIRONMENTS leaves without a "ws"
        # host, but a config built by hand (or a future environment) could
        # still reach here without one.
        raise ValueError("No datafeed host is configured (ws_base_url is unset). Pass ws_base_url explicitly.")


@dataclass
class _Subscription:
    scrip_key: str
    state: _protocol.InstrumentState


def _to_key_list(scrip_keys: ScripKeys) -> List[str]:
    if isinstance(scrip_keys, str):
        return [scrip_keys]
    return list(scrip_keys)


class AsyncHighFeed:
    """The async datafeed client. Delivery is an async iterator
    (``async for event in feed``); :meth:`add_listener` is also available
    for callback-style consumption (it is how the sync :class:`HighFeed`
    bridges events out to its own callers)."""

    def __init__(
        self,
        options: Optional[HighClientOptions] = None,
        *,
        env: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> None:
        merged: dict = dict(options or {})
        merged.update(kwargs)
        self._init(resolve_config(merged, env))

    @classmethod
    def _from_resolved(cls, config: ResolvedConfig) -> "AsyncHighFeed":
        self = cls.__new__(cls)
        self._init(config)
        return self

    def _init(self, config: ResolvedConfig) -> None:
        _reject_sandbox(config)
        self.config = config

        # (route tag, feed segment, feed identifier) -> subscription state.
        # Shared across quote/depth/index — an index's feedSymbol ("Nifty
        # 50") and a token never collide, and quote/depth for the SAME
        # instrument get separate entries because "sf" and "dp" are
        # different route tags.
        self._registry: Dict[Tuple[str, str, str], _Subscription] = {}

        self._ws = None
        self._task: Optional["asyncio.Future"] = None
        self._queue: "asyncio.Queue" = asyncio.Queue()
        self._listeners: List[Callable[[Union[Quote, Depth, IndexTick]], None]] = []

        self._connected = False
        self._closed = False
        self._fatal_error: Optional[Exception] = None
        self._channel_counter = 0
        self._max_scrip_per_conn: Optional[int] = None
        self._max_scrip_per_req: Optional[int] = None

    # -- lifecycle ---------------------------------------------------------

    async def connect(self) -> None:
        """Opens the socket, sends the auth frame, and waits for its
        acknowledgement. Raises :class:`~high_openapi.feed.errors.HighFeedAuthError`
        (never retried) on a ``"stat":"NotOk"`` response. Only after this
        returns may :meth:`subscribe_quotes` and friends be called."""
        if self._closed:
            raise HighFeedError("This feed client has been closed. Construct a new one to reconnect.")
        if self._task is not None:
            return  # already connected (or connecting)
        if not self.config.access_token:
            raise HighFeedError("HighFeed needs an access_token. Pass it to the client, or set HIGH_ACCESS_TOKEN.")

        await self._open_and_authenticate()
        self._connected = True
        self._task = asyncio.ensure_future(self._run_forever())

    async def _open_and_authenticate(self) -> None:
        self.config.logger.info(f"HIGH feed connecting to {self.config.ws_base_url}")
        ws = await websockets.connect(self.config.ws_base_url, open_timeout=self.config.timeout_ms / 1000)

        frame = _protocol.auth_frame(self.config.access_token)
        self.config.logger.debug("HIGH feed -> cn", {"body": redact_body(frame)})
        try:
            await ws.send(json.dumps(frame, separators=(",", ":")))
            raw = await ws.recv()
        except ConnectionClosed as exc:
            raise HighFeedError(f"The datafeed connection closed before authenticating: {exc}") from exc

        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            await ws.close()
            raise HighFeedError(f"Expected a JSON auth acknowledgement, got: {raw!r}") from exc

        classified = _protocol.classify_message(parsed)
        if classified["kind"] != "auth_ack":
            await ws.close()
            raise HighFeedError(
                f"Expected the auth acknowledgement first; got a {classified['kind']!r} frame instead."
            )

        error = _protocol.auth_ack_error(classified)
        if error is not None:
            await ws.close()
            self.config.logger.error(f"HIGH feed auth failed: {error}")
            raise error

        self._ws = ws
        self._max_scrip_per_conn = classified["max_scrip_per_conn"]
        self._max_scrip_per_req = classified["max_scrip_per_req"]
        self.config.logger.info(
            f"HIGH feed authenticated (maxScripPerConn={self._max_scrip_per_conn}, "
            f"maxScripPerReq={self._max_scrip_per_req})"
        )

    async def close(self) -> None:
        """Closes the socket. Idempotent. The async iterator (and any
        pending listener delivery) stops cleanly; no reconnect is attempted."""
        if self._closed:
            return
        self._closed = True
        if self._ws is not None:
            try:
                await self._ws.close()
            except Exception:  # noqa: BLE001 — closing must never raise
                pass
        if self._task is not None:
            try:
                await asyncio.wait_for(asyncio.shield(self._task), timeout=5)
            except (asyncio.TimeoutError, asyncio.CancelledError):
                self._task.cancel()
        else:
            self._queue.put_nowait(_STOP)

    # -- subscription --------------------------------------------------

    async def subscribe_quotes(self, scrip_keys: ScripKeys) -> None:
        """Subscribes to touchline (market-watch) quotes. Rejects an index
        key — use :meth:`subscribe_indices`."""
        await self._subscribe_like("quote", scrip_keys, translate.translate_instrument, _protocol.subscribe_frame)

    async def unsubscribe_quotes(self, scrip_keys: ScripKeys) -> None:
        await self._unsubscribe_like("quote", scrip_keys, translate.translate_instrument)

    async def snapshot_quotes(self, scrip_keys: ScripKeys) -> None:
        """Requests a fresh snapshot for already- (or newly-)subscribed
        quote keys; the response arrives through the normal event stream."""
        await self._subscribe_like("quote", scrip_keys, translate.translate_instrument, _protocol.snapshot_frame)

    async def subscribe_depth(self, scrip_keys: ScripKeys) -> None:
        """Subscribes to five-level market depth. Rejects an index key —
        use :meth:`subscribe_indices`."""
        await self._subscribe_like("depth", scrip_keys, translate.translate_instrument, _protocol.subscribe_frame)

    async def unsubscribe_depth(self, scrip_keys: ScripKeys) -> None:
        await self._unsubscribe_like("depth", scrip_keys, translate.translate_instrument)

    async def snapshot_depth(self, scrip_keys: ScripKeys) -> None:
        await self._subscribe_like("depth", scrip_keys, translate.translate_instrument, _protocol.snapshot_frame)

    async def subscribe_indices(self, scrip_keys: ScripKeys) -> None:
        """Subscribes to index ticks. Only accepts keys from the committed
        index table — a non-index key is rejected; use
        :meth:`subscribe_quotes`/:meth:`subscribe_depth` for it."""
        await self._subscribe_like("index", scrip_keys, translate.translate_index, _protocol.subscribe_frame)

    async def unsubscribe_indices(self, scrip_keys: ScripKeys) -> None:
        await self._unsubscribe_like("index", scrip_keys, translate.translate_index)

    async def snapshot_indices(self, scrip_keys: ScripKeys) -> None:
        await self._subscribe_like("index", scrip_keys, translate.translate_index, _protocol.snapshot_frame)

    async def _subscribe_like(self, kind: str, scrip_keys: ScripKeys, translator, builder) -> None:
        self._require_connected()
        keys = _to_key_list(scrip_keys)
        if not keys:
            return

        translated = [(key, *translator(key)) for key in keys]
        route_tag = _protocol.ROUTE_TAG[kind]

        new_count = sum(
            1 for _, seg, ident in translated if (route_tag, seg, str(ident)) not in self._registry
        )
        total_after = len(self._registry) + new_count
        if self._max_scrip_per_conn is not None and total_after > self._max_scrip_per_conn:
            raise HighFeedLimitError(
                f"Subscribing to {new_count} more scrip(s) would bring this connection to {total_after}, "
                f"over the server's maxScripPerConn of {self._max_scrip_per_conn}.",
                requested=total_after, limit=self._max_scrip_per_conn,
            )

        for key, seg, ident in translated:
            reg_key = (route_tag, seg, str(ident))
            if reg_key not in self._registry:
                self._registry[reg_key] = _Subscription(key, _protocol.InstrumentState(key))

        feed_keys = [f"{seg}|{ident}" for _, seg, ident in translated]
        await self._send_frames(kind, feed_keys, builder)

    async def _unsubscribe_like(self, kind: str, scrip_keys: ScripKeys, translator) -> None:
        self._require_connected()
        keys = _to_key_list(scrip_keys)
        if not keys:
            return

        translated = [(key, *translator(key)) for key in keys]
        route_tag = _protocol.ROUTE_TAG[kind]
        for _, seg, ident in translated:
            self._registry.pop((route_tag, seg, str(ident)), None)

        feed_keys = [f"{seg}|{ident}" for _, seg, ident in translated]
        await self._send_frames(kind, feed_keys, _protocol.unsubscribe_frame)

    async def _send_frames(self, kind: str, feed_keys: List[str], builder) -> None:
        per_request = self._max_scrip_per_req or len(feed_keys) or 1
        for group in _protocol.chunk(feed_keys, per_request):
            self._channel_counter += 1
            frame = builder(kind, group, self._channel_counter)
            await self._send(frame)

    async def _send(self, frame: dict) -> None:
        self.config.logger.debug(f"HIGH feed -> {frame.get('type')}", {"body": frame})
        await self._ws.send(json.dumps(frame, separators=(",", ":")))

    async def _resubscribe_all(self) -> None:
        by_kind: Dict[str, List[str]] = {}
        for route_tag, seg, ident in self._registry:
            kind = _INVERSE_ROUTE_TAG[route_tag]
            by_kind.setdefault(kind, []).append(f"{seg}|{ident}")
        for kind, feed_keys in by_kind.items():
            await self._send_frames(kind, feed_keys, _protocol.subscribe_frame)

    def _require_connected(self) -> None:
        if self._closed:
            raise HighFeedError("This feed client has been closed.")
        if not self._connected or self._ws is None:
            raise HighFeedError("HighFeed is not connected. Call (and await) connect() before subscribing.")

    # -- receive loop / reconnect -------------------------------------

    async def _receive_loop(self) -> None:
        try:
            async for raw_text in self._ws:
                self._handle_raw_message(raw_text)
        except ConnectionClosed:
            pass
        raise _TransportFailure("The datafeed connection closed.")

    def _handle_raw_message(self, raw_text: str) -> None:
        try:
            parsed = json.loads(raw_text)
        except ValueError:
            self.config.logger.warn("HIGH feed: received a non-JSON frame, ignoring")
            return

        classified = _protocol.classify_message(parsed)
        kind = classified["kind"]
        if kind == "ticks":
            for item in classified["items"]:
                self._route_tick(item)
        elif kind == "sub_ack":
            self.config.logger.debug(f"HIGH feed sub/unsub ack: {classified['items']}")
        else:
            self.config.logger.debug(f"HIGH feed: unrouted frame ({kind}), ignoring")

    def _route_tick(self, item: Dict[str, Any]) -> None:
        route_tag = item.get("t")
        if route_tag not in ("sf", "dp", "if"):
            return
        reg_key = (route_tag, item.get("e"), str(item.get("tk")))
        subscription = self._registry.get(reg_key)
        if subscription is None:
            # Not something we asked for (a stale channel, a race with
            # unsubscribe) — dropped, never guessed at.
            return

        if route_tag == "sf":
            quote_event, depth_event = _protocol.apply_quote_tick(subscription.state, item)
            if quote_event is not None:
                self._emit(quote_event)
            if depth_event is not None:
                self._emit(depth_event)
        elif route_tag == "dp":
            depth_event = _protocol.apply_depth_tick(subscription.state, item)
            if depth_event is not None:
                self._emit(depth_event)
        else:
            index_event = _protocol.apply_index_tick(subscription.state, item)
            if index_event is not None:
                self._emit(index_event)

    def _emit(self, event: Union[Quote, Depth, IndexTick]) -> None:
        self._queue.put_nowait(event)
        for listener in list(self._listeners):
            try:
                listener(event)
            except Exception as exc:  # noqa: BLE001 — a listener's bug must not kill the feed
                self.config.logger.error("HIGH feed: a listener raised while handling an event", str(exc))

    async def _run_forever(self) -> None:
        try:
            while True:
                try:
                    await self._receive_loop()
                except _TransportFailure:
                    if self._closed:
                        return
                    self._connected = False
                    self.config.logger.error("HIGH feed: transport failure, reconnecting")
                    reconnected = await self._reconnect_with_backoff()
                    if not reconnected:
                        return
                    continue
        finally:
            self._queue.put_nowait(_STOP)

    async def _reconnect_with_backoff(self) -> bool:
        attempt = 0
        while not self._closed:
            delay_ms = backoff_ms(attempt)
            self.config.logger.warn(f"HIGH feed: reconnect attempt {attempt + 1} in {delay_ms:.0f}ms")
            await asyncio.sleep(delay_ms / 1000)
            attempt += 1
            try:
                await self._open_and_authenticate()
            except HighFeedAuthError as exc:
                # Never retried: the server will keep refusing. Surfaced to
                # whoever is consuming events (see __anext__).
                self._fatal_error = exc
                self.config.logger.error(f"HIGH feed: reconnect auth failed, giving up: {exc}")
                return False
            except Exception as exc:  # noqa: BLE001 — any other failure just tries again
                self.config.logger.warn(f"HIGH feed: reconnect attempt {attempt} failed: {exc}")
                continue
            else:
                await self._resubscribe_all()
                self._connected = True
                self.config.logger.info("HIGH feed: reconnected and resubscribed everything")
                return True
        return False

    # -- async iteration -------------------------------------------------

    def __aiter__(self) -> "AsyncHighFeed":
        return self

    async def __anext__(self) -> Union[Quote, Depth, IndexTick]:
        item = await self._queue.get()
        if item is _STOP:
            if self._fatal_error is not None:
                raise self._fatal_error
            raise StopAsyncIteration
        return item

    # -- callback listeners ------------------------------------------------

    def add_listener(self, callback: Callable[[Union[Quote, Depth, IndexTick]], None]):
        self._listeners.append(callback)
        return callback

    def remove_listener(self, callback: Callable[[Union[Quote, Depth, IndexTick]], None]) -> None:
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass


class HighFeed:
    """The synchronous datafeed client. Runs :class:`AsyncHighFeed` on a
    dedicated background thread and its own event loop; every method here
    blocks until the corresponding async operation completes. Delivery is by
    callback: register with :meth:`add_listener` (before or after
    :meth:`connect`) and it is invoked, from the background thread, with
    every event the feed delivers."""

    def __init__(
        self,
        options: Optional[HighClientOptions] = None,
        *,
        env: Optional[Dict[str, str]] = None,
        **kwargs: Any,
    ) -> None:
        merged: dict = dict(options or {})
        merged.update(kwargs)
        self.config: ResolvedConfig = resolve_config(merged, env)
        _reject_sandbox(self.config)  # fail fast, before ever starting a thread

        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._async: Optional[AsyncHighFeed] = None
        self._listeners: List[Callable[[Union[Quote, Depth, IndexTick]], None]] = []
        self._lock = threading.Lock()

    def _ensure_started(self) -> None:
        if self._loop is not None:
            return
        ready = threading.Event()

        def _run() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._async = AsyncHighFeed._from_resolved(self.config)
            for callback in self._listeners:
                self._async.add_listener(callback)
            self._loop = loop
            ready.set()
            loop.run_forever()

        self._thread = threading.Thread(target=_run, name="high-feed", daemon=True)
        self._thread.start()
        ready.wait()

    def _call(self, factory: Callable[[], "asyncio.Future"], timeout: Optional[float] = None):
        self._ensure_started()
        future = asyncio.run_coroutine_threadsafe(factory(), self._loop)
        return future.result(timeout=timeout)

    def connect(self) -> None:
        self._call(lambda: self._async.connect())

    def close(self) -> None:
        if self._loop is None:
            return
        try:
            self._call(lambda: self._async.close(), timeout=10)
        finally:
            loop = self._loop
            loop.call_soon_threadsafe(loop.stop)
            if self._thread is not None:
                self._thread.join(timeout=5)
            self._loop = None

    def subscribe_quotes(self, scrip_keys: ScripKeys) -> None:
        self._call(lambda: self._async.subscribe_quotes(scrip_keys))

    def unsubscribe_quotes(self, scrip_keys: ScripKeys) -> None:
        self._call(lambda: self._async.unsubscribe_quotes(scrip_keys))

    def snapshot_quotes(self, scrip_keys: ScripKeys) -> None:
        self._call(lambda: self._async.snapshot_quotes(scrip_keys))

    def subscribe_depth(self, scrip_keys: ScripKeys) -> None:
        self._call(lambda: self._async.subscribe_depth(scrip_keys))

    def unsubscribe_depth(self, scrip_keys: ScripKeys) -> None:
        self._call(lambda: self._async.unsubscribe_depth(scrip_keys))

    def snapshot_depth(self, scrip_keys: ScripKeys) -> None:
        self._call(lambda: self._async.snapshot_depth(scrip_keys))

    def subscribe_indices(self, scrip_keys: ScripKeys) -> None:
        self._call(lambda: self._async.subscribe_indices(scrip_keys))

    def unsubscribe_indices(self, scrip_keys: ScripKeys) -> None:
        self._call(lambda: self._async.unsubscribe_indices(scrip_keys))

    def snapshot_indices(self, scrip_keys: ScripKeys) -> None:
        self._call(lambda: self._async.snapshot_indices(scrip_keys))

    def add_listener(self, callback: Callable[[Union[Quote, Depth, IndexTick]], None]):
        with self._lock:
            self._listeners.append(callback)
            if self._async is not None:
                self._async.add_listener(callback)
        return callback

    def remove_listener(self, callback: Callable[[Union[Quote, Depth, IndexTick]], None]) -> None:
        with self._lock:
            if callback in self._listeners:
                self._listeners.remove(callback)
            if self._async is not None:
                self._async.remove_listener(callback)

    def __enter__(self) -> "HighFeed":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()
