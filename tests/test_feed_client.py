# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""End-to-end datafeed tests against a real local WebSocket server
(``tests/feed_server.py``) — never a mocked socket.

Covers the plan's required list: auth-before-subscribe ordering, a NotOk
auth never retrying, both maxScripPerConn/maxScripPerReq limits honoured,
delta merge across wire ticks, the quote/depth split, depth level-numbering
pairing, index vs equity translation, an unknown prefix rejected,
reconnect-and-resubscribe, sandbox refused at construction, and credentials
absent from logs.
"""

from __future__ import annotations

import asyncio
import threading
import time
from decimal import Decimal

import pytest

from high_openapi.feed import AsyncHighFeed, Depth, HighFeed, IndexTick, Quote
from high_openapi.feed.errors import HighFeedAuthError, HighFeedError, HighFeedKeyError, HighFeedLimitError

from .feed_server import not_ok_ack, ok_ack, start_feed_server


async def _next_event(feed, timeout: float = 5.0):
    return await asyncio.wait_for(feed.__anext__(), timeout=timeout)


async def _wait_until(predicate, timeout: float = 5.0, interval: float = 0.02) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        await asyncio.sleep(interval)
    assert predicate(), "condition never became true within the timeout"


def _cn_count(server) -> int:
    return sum(1 for m in server.received if isinstance(m, dict) and m.get("type") == "cn")


def _frames_of_type(server, type_: str):
    return [m for m in server.received if isinstance(m, dict) and m.get("type") == type_]


class TestAuthBeforeSubscribeOrdering:
    async def test_a_subscribe_call_before_connect_is_rejected_and_sends_nothing(self):
        feed = AsyncHighFeed(access_token="tok", ws_base_url="ws://127.0.0.1:1")
        with pytest.raises(HighFeedError):
            await feed.subscribe_quotes(["NSE@2885"])

    async def test_the_auth_frame_is_the_first_thing_the_server_ever_receives(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            await feed.subscribe_quotes(["NSE@2885"])
            await _wait_until(lambda: len(server.received) >= 2)
            assert server.received[0]["type"] == "cn"
            assert server.received[1]["type"] == "mws"
            await feed.close()
        finally:
            server.close()


class TestNotOkAuthNeverRetries:
    async def test_a_notok_ack_raises_and_is_never_retried(self):
        server = start_feed_server(auth_response=lambda frame: not_ok_ack(11001, "failed"))
        try:
            feed = AsyncHighFeed(access_token="bad-token", ws_base_url=server.url)
            with pytest.raises(HighFeedAuthError) as exc_info:
                await feed.connect()
            assert exc_info.value.st_code == 11001

            # Give a buggy retry loop every chance to fire before asserting
            # it did not.
            await asyncio.sleep(0.3)
            assert _cn_count(server) == 1
        finally:
            server.close()


class TestLimitsHonoured:
    async def test_max_scrip_per_conn_is_enforced_before_sending_anything(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack(max_scrip_per_conn=2, max_scrip_per_req=500))
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            with pytest.raises(HighFeedLimitError) as exc_info:
                await feed.subscribe_quotes(["NSE@1", "NSE@2", "NSE@3"])
            assert exc_info.value.limit == 2
            await asyncio.sleep(0.1)
            assert _frames_of_type(server, "mws") == []
            await feed.close()
        finally:
            server.close()

    async def test_max_scrip_per_req_splits_a_large_subscription_across_requests(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack(max_scrip_per_conn=1000, max_scrip_per_req=2))
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            await feed.subscribe_quotes([f"NSE@{i}" for i in range(1, 6)])  # 5 scrips, cap of 2 per request
            await _wait_until(lambda: len(_frames_of_type(server, "mws")) == 3)
            sizes = sorted(len(f["scrips"].split("&")) for f in _frames_of_type(server, "mws"))
            assert sizes == [1, 2, 2]
            await feed.close()
        finally:
            server.close()


class TestDeltaMergeAcrossWireTicks:
    async def test_a_field_not_repeated_keeps_its_last_value(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            await feed.subscribe_quotes(["NSE@2885"])

            server.send_to_all([{"t": "sf", "e": "nse_cm", "tk": "2885", "ltp": "100.00", "op": "99.00"}])
            first = await _next_event(feed)
            assert isinstance(first, Quote)
            assert first.open == Decimal("99.00")

            server.send_to_all([{"t": "sf", "e": "nse_cm", "tk": "2885", "ltp": "100.50"}])
            second = await _next_event(feed)
            assert isinstance(second, Quote)
            assert second.last_traded_price == Decimal("100.50")
            assert second.open == Decimal("99.00")  # carried over, not re-sent
            assert second.changed_fields == frozenset({"last_traded_price"})
            await feed.close()
        finally:
            server.close()


class TestQuoteDepthSplitOverTheWire:
    async def test_full_mode_tick_raises_two_separate_events(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            await feed.subscribe_quotes(["NSE@2885"])

            server.send_to_all([{
                "t": "sf", "e": "nse_cm", "tk": "2885",
                "ltp": "100.50", "op": "99.00", "bp": "100.40", "bq": "10", "sp": "100.60", "bs": "20",
            }])
            first = await _next_event(feed)
            second = await _next_event(feed)
            events = [first, second]
            quotes = [e for e in events if isinstance(e, Quote)]
            depths = [e for e in events if isinstance(e, Depth)]
            assert len(quotes) == 1 and len(depths) == 1
            assert depths[0].level_count == 1
            assert depths[0].source == "quote"
            assert depths[0].bids[0].price == Decimal("100.40")
            await feed.close()
        finally:
            server.close()

    async def test_a_tick_moving_only_ltp_never_raises_a_depth_event(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            await feed.subscribe_quotes(["NSE@2885"])

            server.send_to_all([{"t": "sf", "e": "nse_cm", "tk": "2885", "ltp": "100.50"}])
            only_event = await _next_event(feed)
            assert isinstance(only_event, Quote)

            # Confirm nothing else follows for this tick.
            server.send_to_all([{"t": "sf", "e": "nse_cm", "tk": "2885", "ltp": "100.55"}])
            next_event = await _next_event(feed)
            assert isinstance(next_event, Quote)
            assert next_event.last_traded_price == Decimal("100.55")
            await feed.close()
        finally:
            server.close()


class TestDepthLevelPairingOverTheWire:
    async def test_five_levels_pair_correctly_end_to_end(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            await feed.subscribe_depth(["NSE@2885"])

            tick = {"t": "dp", "e": "nse_cm", "tk": "2885"}
            for i, price in enumerate([10.1, 10.2, 10.3, 10.4, 10.5]):
                tick["bp" if i == 0 else f"bp{i}"] = str(price)
            for i in range(5):
                tick[f"bno{i + 1}"] = str(100 + i)
            server.send_to_all([tick])

            depth = await _next_event(feed)
            assert isinstance(depth, Depth)
            assert depth.level_count == 5
            assert depth.bids[0].price == Decimal("10.1") and depth.bids[0].orders == 100
            assert depth.bids[4].price == Decimal("10.5") and depth.bids[4].orders == 104
            await feed.close()
        finally:
            server.close()


class TestIndexVsEquityTranslationOverTheWire:
    async def test_index_key_resolves_to_the_feed_symbol_by_name(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            await feed.subscribe_indices(["NSE@26000"])
            await _wait_until(lambda: len(_frames_of_type(server, "ifs")) == 1)
            assert _frames_of_type(server, "ifs")[0]["scrips"] == "nse_cm|Nifty 50"

            index_tick = {"t": "if", "e": "nse_cm", "tk": "Nifty 50", "iv": "19500.25"}
            server.send_to_all([index_tick])
            event = await _next_event(feed)
            assert isinstance(event, IndexTick)
            assert event.scrip_key == "NSE@26000"
            assert event.index_value == Decimal("19500.25")
            await feed.close()
        finally:
            server.close()

    async def test_equity_key_resolves_to_its_token(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            await feed.subscribe_quotes(["NSE@2885"])
            await _wait_until(lambda: len(_frames_of_type(server, "mws")) == 1)
            assert _frames_of_type(server, "mws")[0]["scrips"] == "nse_cm|2885"
            await feed.close()
        finally:
            server.close()

    async def test_an_index_key_is_rejected_by_subscribe_quotes(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            with pytest.raises(HighFeedKeyError, match="NSE@26000"):
                await feed.subscribe_quotes(["NSE@26000"])
            await feed.close()
        finally:
            server.close()

    async def test_a_non_index_key_is_rejected_by_subscribe_indices(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            with pytest.raises(HighFeedKeyError, match="NSE@2885"):
                await feed.subscribe_indices(["NSE@2885"])
            await feed.close()
        finally:
            server.close()


class TestUnknownPrefixRejected:
    async def test_an_unsupported_prefix_is_rejected_and_nothing_is_sent(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            with pytest.raises(HighFeedKeyError, match="XSE@1"):
                await feed.subscribe_quotes(["XSE@1"])
            await asyncio.sleep(0.1)
            assert _frames_of_type(server, "mws") == []
            await feed.close()
        finally:
            server.close()


class TestReconnectAndResubscribe:
    async def test_transport_failure_triggers_reauth_and_full_resubscribe(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = AsyncHighFeed(access_token="tok", ws_base_url=server.url)
            await feed.connect()
            await feed.subscribe_quotes(["NSE@2885"])
            await _wait_until(lambda: len(_frames_of_type(server, "mws")) == 1)

            # drop_all_async, not drop_all: this test's client runs on the
            # same pytest-asyncio loop as this coroutine, and the close
            # handshake drop_all triggers needs that loop to keep running
            # while it completes — see feed_server.py's docstring.
            await server.drop_all_async()

            # Reconnect: a second "cn", then a fresh "mws" for the same key.
            await _wait_until(lambda: _cn_count(server) == 2, timeout=10)
            await _wait_until(lambda: len(_frames_of_type(server, "mws")) == 2, timeout=10)
            assert _frames_of_type(server, "mws")[1]["scrips"] == "nse_cm|2885"

            # And ticks resume flowing for the same subscription.
            server.send_to_all([{"t": "sf", "e": "nse_cm", "tk": "2885", "ltp": "111.00"}])
            event = await _next_event(feed, timeout=10)
            assert isinstance(event, Quote)
            assert event.scrip_key == "NSE@2885"
            assert event.last_traded_price == Decimal("111.00")
            await feed.close()
        finally:
            server.close()


class TestSandboxRefusedAtConstruction:
    def test_async_feed_refuses_sandbox(self):
        with pytest.raises(ValueError, match="sandbox"):
            AsyncHighFeed(environment="sandbox", access_token="tok")

    def test_sync_feed_refuses_sandbox(self):
        with pytest.raises(ValueError, match="sandbox"):
            HighFeed(environment="sandbox", access_token="tok")

    def test_production_default_is_fine_to_construct(self):
        # Never dial openapi-feed.high.live in a test — it is not deployed.
        # This proves the default resolves to the right host without ever
        # calling connect(): construction alone must not attempt a socket.
        feed = AsyncHighFeed(access_token="tok")
        assert feed.config.ws_base_url == "wss://openapi-feed.high.live"
        assert feed.config.environment == "production"


class _CapturingSink:
    def __init__(self):
        self.lines = []

    def _capture(self, message, detail=None):
        self.lines.append(str(message))
        if detail is not None:
            self.lines.append(str(detail))

    def error(self, message, detail=None):
        self._capture(message, detail)

    def warn(self, message, detail=None):
        self._capture(message, detail)

    def info(self, message, detail=None):
        self._capture(message, detail)

    def debug(self, message, detail=None):
        self._capture(message, detail)


class TestCredentialsAbsentFromLogs:
    async def test_the_access_token_never_appears_in_a_debug_log_line(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        sink = _CapturingSink()
        try:
            feed = AsyncHighFeed(
                access_token="SECRET-FEED-TOKEN", ws_base_url=server.url, log_level="debug", log_sink=sink,
            )
            await feed.connect()
            await feed.subscribe_quotes(["NSE@2885"])
            server.send_to_all([{"t": "sf", "e": "nse_cm", "tk": "2885", "ltp": "100.00"}])
            await _next_event(feed)
            await feed.close()

            assert sink.lines, "expected at least one log line"
            for line in sink.lines:
                assert "SECRET-FEED-TOKEN" not in line
        finally:
            server.close()


class TestHighFeedSyncCallback:
    def test_connect_subscribe_and_receive_via_a_plain_callback(self):
        server = start_feed_server(auth_response=lambda frame: ok_ack())
        try:
            feed = HighFeed(access_token="tok", ws_base_url=server.url)
            received = []
            lock = threading.Lock()

            def _on_event(event):
                with lock:
                    received.append(event)

            feed.add_listener(_on_event)
            feed.connect()
            feed.subscribe_quotes(["NSE@2885"])

            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                server.send_to_all([{"t": "sf", "e": "nse_cm", "tk": "2885", "ltp": "42.00"}])
                with lock:
                    if received:
                        break
                time.sleep(0.05)

            with lock:
                assert len(received) >= 1
                assert isinstance(received[0], Quote)
                assert received[0].last_traded_price == Decimal("42.00")
            feed.close()
        finally:
            server.close()
