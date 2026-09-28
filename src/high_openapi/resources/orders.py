# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from __future__ import annotations

from typing import Iterable

import httpx

from .. import http_async, http_sync
from ..config import ResolvedConfig
from ..generated.models import (
    ModifyOrderRequest,
    OrderBook,
    OrderCancelResult,
    OrderCharges,
    OrderChargesRequest,
    OrderMargin,
    OrderMarginRequestItem,
    OrderPlacementResult,
    PlaceOrderRequest,
    TradeBook,
)
from ..paths import path_of
from ._shared import Body, dump_body, dump_list_body, parse

__all__ = [
    "OrdersResource",
    "AsyncOrdersResource",
    "PlaceOrderRequest",
    "ModifyOrderRequest",
    "OrderChargesRequest",
    "OrderMarginRequestItem",
]


class OrdersResource:
    def __init__(self, client: httpx.Client, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    def place(self, body: Body, *, cancel_event=None) -> OrderPlacementResult:
        """Places a regular, bracket, cover or GTT order. Never retried."""
        payload = dump_body(PlaceOrderRequest, body)
        data = http_sync.send_request(
            self._client, self._config, method="POST", path="/orders", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse(OrderPlacementResult, data)

    def modify(self, body: Body, *, cancel_event=None) -> OrderPlacementResult:
        """Modifies a pending order. Never retried."""
        payload = dump_body(ModifyOrderRequest, body)
        data = http_sync.send_request(
            self._client, self._config, method="PATCH", path="/orders", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse(OrderPlacementResult, data)

    def get(self, order_id: str, *, cancel_event=None) -> OrderBook:
        """One order, in the same shape as the order book."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path=path_of("/orders/{orderId}", {"orderId": order_id}),
            auth="bearer", cancel_event=cancel_event,
        )
        return parse(OrderBook, data)

    def cancel(self, order_id: str, *, cancel_event=None) -> OrderCancelResult:
        """Cancels a pending order. Never retried."""
        data = http_sync.send_request(
            self._client, self._config, method="DELETE", path=path_of("/orders/{orderId}", {"orderId": order_id}),
            auth="bearer", cancel_event=cancel_event,
        )
        return parse(OrderCancelResult, data)

    def list(self, *, cancel_event=None) -> OrderBook:
        """Today's order book."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path="/orders/list", auth="bearer", cancel_event=cancel_event,
        )
        return parse(OrderBook, data)

    def trades(self, *, cancel_event=None) -> TradeBook:
        """Today's trade book."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path="/orders/trades", auth="bearer", cancel_event=cancel_event,
        )
        return parse(TradeBook, data)

    def trades_for(self, order_id: str, *, cancel_event=None) -> TradeBook:
        """The fills of one order."""
        data = http_sync.send_request(
            self._client, self._config, method="GET",
            path=path_of("/orders/{orderId}/trades", {"orderId": order_id}), auth="bearer",
            cancel_event=cancel_event,
        )
        return parse(TradeBook, data)

    def charges(self, body: Body, *, cancel_event=None) -> OrderCharges:
        """Estimated brokerage and statutory charges for one order."""
        payload = dump_body(OrderChargesRequest, body)
        data = http_sync.send_request(
            self._client, self._config, method="POST", path="/orders/charges", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse(OrderCharges, data)

    def margin(self, body: Iterable[Body], *, cancel_event=None) -> OrderMargin:
        """Margin required for a basket of orders."""
        payload = dump_list_body(OrderMarginRequestItem, body)
        data = http_sync.send_request(
            self._client, self._config, method="POST", path="/orders/margin", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse(OrderMargin, data)


class AsyncOrdersResource:
    def __init__(self, client: httpx.AsyncClient, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    async def place(self, body: Body) -> OrderPlacementResult:
        payload = dump_body(PlaceOrderRequest, body)
        data = await http_async.send_request(
            self._client, self._config, method="POST", path="/orders", auth="bearer", body=payload,
        )
        return parse(OrderPlacementResult, data)

    async def modify(self, body: Body) -> OrderPlacementResult:
        payload = dump_body(ModifyOrderRequest, body)
        data = await http_async.send_request(
            self._client, self._config, method="PATCH", path="/orders", auth="bearer", body=payload,
        )
        return parse(OrderPlacementResult, data)

    async def get(self, order_id: str) -> OrderBook:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path=path_of("/orders/{orderId}", {"orderId": order_id}),
            auth="bearer",
        )
        return parse(OrderBook, data)

    async def cancel(self, order_id: str) -> OrderCancelResult:
        data = await http_async.send_request(
            self._client, self._config, method="DELETE", path=path_of("/orders/{orderId}", {"orderId": order_id}),
            auth="bearer",
        )
        return parse(OrderCancelResult, data)

    async def list(self) -> OrderBook:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path="/orders/list", auth="bearer",
        )
        return parse(OrderBook, data)

    async def trades(self) -> TradeBook:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path="/orders/trades", auth="bearer",
        )
        return parse(TradeBook, data)

    async def trades_for(self, order_id: str) -> TradeBook:
        data = await http_async.send_request(
            self._client, self._config, method="GET",
            path=path_of("/orders/{orderId}/trades", {"orderId": order_id}), auth="bearer",
        )
        return parse(TradeBook, data)

    async def charges(self, body: Body) -> OrderCharges:
        payload = dump_body(OrderChargesRequest, body)
        data = await http_async.send_request(
            self._client, self._config, method="POST", path="/orders/charges", auth="bearer", body=payload,
        )
        return parse(OrderCharges, data)

    async def margin(self, body: Iterable[Body]) -> OrderMargin:
        payload = dump_list_body(OrderMarginRequestItem, body)
        data = await http_async.send_request(
            self._client, self._config, method="POST", path="/orders/margin", auth="bearer", body=payload,
        )
        return parse(OrderMargin, data)
