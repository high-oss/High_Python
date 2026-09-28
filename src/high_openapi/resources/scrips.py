# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""``ExpiryType`` is hand-written rather than generated: the spec's
``/scrips/{symbol}/{type}/expiries`` ``type`` path parameter is an inline
parameter schema, and no ``datamodel-code-generator`` scope combination
turns an inline *parameter* (as opposed to a request body) into a named
type — see the build plan's tooling ruling. ``test_review_findings.py``
reads the pinned spec and asserts this literal still matches its enum, the
runtime analogue of the Node SDK's compile-time
``paths['/scrips/{symbol}/{type}/expiries']['get']['parameters']['path']['type']``
derivation.
"""

from __future__ import annotations

from typing import List, Literal

import httpx

from .. import http_async, http_sync
from ..config import ResolvedConfig
from ..generated.models import (
    Expiry,
    HistoricalCandles,
    HistoricalRequest,
    MarketDepth,
    OhlcRequest,
    OptionChain,
    OptionChainRequest,
    QuotesRequest,
    ScripInfo,
    Touchline,
)
from ..paths import path_of
from ._shared import Body, dump_body, parse, parse_list, parse_map

__all__ = [
    "ScripsResource", "AsyncScripsResource", "ExpiryType",
    "QuotesRequest", "OhlcRequest", "HistoricalRequest", "OptionChainRequest",
]

ExpiryType = Literal["futures", "options"]


class ScripsResource:
    def __init__(self, client: httpx.Client, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    def quotes(self, body: Body, *, cancel_event=None) -> "dict[str, Touchline]":
        """Last traded price and session change, keyed by trading symbol."""
        payload = dump_body(QuotesRequest, body)
        data = http_sync.send_request(
            self._client, self._config, method="POST", path="/scrips/quotes", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse_map(Touchline, data)

    def ohlc(self, body: Body, *, cancel_event=None) -> "dict[str, Touchline]":
        """Quotes plus the session OHLCV block, keyed by trading symbol."""
        payload = dump_body(OhlcRequest, body)
        data = http_sync.send_request(
            self._client, self._config, method="POST", path="/scrips/ohlc", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse_map(Touchline, data)

    def depth(self, symbol: str, *, cancel_event=None) -> MarketDepth:
        """Five levels of bids and asks."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path=path_of("/scrips/{symbol}/depth", {"symbol": symbol}),
            auth="bearer", cancel_event=cancel_event,
        )
        return parse(MarketDepth, data)

    def expiries(self, symbol: str, type: ExpiryType, *, cancel_event=None) -> List[Expiry]:  # noqa: A002
        """Available expiries for a derivative underlying."""
        data = http_sync.send_request(
            self._client, self._config, method="GET",
            path=path_of("/scrips/{symbol}/{type}/expiries", {"symbol": symbol, "type": type}),
            auth="bearer", cancel_event=cancel_event,
        )
        return parse_list(Expiry, data)

    def future_data(self, symbol: str, *, cancel_event=None) -> List[ScripInfo]:
        """The futures contracts on an underlying."""
        data = http_sync.send_request(
            self._client, self._config, method="GET",
            path=path_of("/scrips/{symbol}/future-data", {"symbol": symbol}), auth="bearer",
            cancel_event=cancel_event,
        )
        return parse_list(ScripInfo, data)

    def historical(self, body: Body, *, cancel_event=None) -> HistoricalCandles:
        """Historical candles, returned columnar: every array has the same
        length and index i across them describes one candle."""
        payload = dump_body(HistoricalRequest, body)
        data = http_sync.send_request(
            self._client, self._config, method="POST", path="/scrips/historical", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse(HistoricalCandles, data)

    def option_chain(self, body: Body, *, cancel_event=None) -> OptionChain:
        """The option chain for one underlying and expiry."""
        payload = dump_body(OptionChainRequest, body)
        data = http_sync.send_request(
            self._client, self._config, method="POST", path="/scrips/option-chain", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse(OptionChain, data)


class AsyncScripsResource:
    def __init__(self, client: httpx.AsyncClient, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    async def quotes(self, body: Body) -> "dict[str, Touchline]":
        payload = dump_body(QuotesRequest, body)
        data = await http_async.send_request(
            self._client, self._config, method="POST", path="/scrips/quotes", auth="bearer", body=payload,
        )
        return parse_map(Touchline, data)

    async def ohlc(self, body: Body) -> "dict[str, Touchline]":
        payload = dump_body(OhlcRequest, body)
        data = await http_async.send_request(
            self._client, self._config, method="POST", path="/scrips/ohlc", auth="bearer", body=payload,
        )
        return parse_map(Touchline, data)

    async def depth(self, symbol: str) -> MarketDepth:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path=path_of("/scrips/{symbol}/depth", {"symbol": symbol}),
            auth="bearer",
        )
        return parse(MarketDepth, data)

    async def expiries(self, symbol: str, type: ExpiryType) -> List[Expiry]:  # noqa: A002
        data = await http_async.send_request(
            self._client, self._config, method="GET",
            path=path_of("/scrips/{symbol}/{type}/expiries", {"symbol": symbol, "type": type}), auth="bearer",
        )
        return parse_list(Expiry, data)

    async def future_data(self, symbol: str) -> List[ScripInfo]:
        data = await http_async.send_request(
            self._client, self._config, method="GET",
            path=path_of("/scrips/{symbol}/future-data", {"symbol": symbol}), auth="bearer",
        )
        return parse_list(ScripInfo, data)

    async def historical(self, body: Body) -> HistoricalCandles:
        payload = dump_body(HistoricalRequest, body)
        data = await http_async.send_request(
            self._client, self._config, method="POST", path="/scrips/historical", auth="bearer", body=payload,
        )
        return parse(HistoricalCandles, data)

    async def option_chain(self, body: Body) -> OptionChain:
        payload = dump_body(OptionChainRequest, body)
        data = await http_async.send_request(
            self._client, self._config, method="POST", path="/scrips/option-chain", auth="bearer", body=payload,
        )
        return parse(OptionChain, data)
