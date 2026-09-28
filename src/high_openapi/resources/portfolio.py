# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from __future__ import annotations

import httpx

from .. import http_async, http_sync
from ..config import ResolvedConfig
from ..generated.models import (
    ConvertPositionRequest,
    ExitPositionRequest,
    Funds,
    Holdings,
    PositionConvertResult,
    PositionExitAllResult,
    PositionExitResult,
    Positions,
)
from ._shared import Body, dump_body, parse

__all__ = ["PortfolioResource", "AsyncPortfolioResource", "ConvertPositionRequest", "ExitPositionRequest"]


class PortfolioResource:
    def __init__(self, client: httpx.Client, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    def positions(self, *, cancel_event=None) -> Positions:
        """Open intraday and carry-forward positions with their P&L snapshot."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path="/portfolio/positions", auth="bearer",
            cancel_event=cancel_event,
        )
        return parse(Positions, data)

    def holdings(self, *, cancel_event=None) -> Holdings:
        """Demat holdings with their investment snapshot."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path="/portfolio/holdings", auth="bearer",
            cancel_event=cancel_event,
        )
        return parse(Holdings, data)

    def funds(self, *, cancel_event=None) -> Funds:
        """Cash, margin and charge balances."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path="/portfolio/funds", auth="bearer",
            cancel_event=cancel_event,
        )
        return parse(Funds, data)

    def convert_position(self, body: Body, *, cancel_event=None) -> PositionConvertResult:
        """Converts a position between product types. Never retried."""
        payload = dump_body(ConvertPositionRequest, body)
        data = http_sync.send_request(
            self._client, self._config, method="PATCH", path="/portfolio/positions/convert", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse(PositionConvertResult, data)

    def exit_all_positions(self, *, cancel_event=None) -> PositionExitAllResult:
        """Squares off every open position. Never retried."""
        data = http_sync.send_request(
            self._client, self._config, method="DELETE", path="/portfolio/positions/exit/all", auth="bearer",
            cancel_event=cancel_event,
        )
        return parse(PositionExitAllResult, data)

    def exit_position(self, body: Body, *, cancel_event=None) -> PositionExitResult:
        """Squares off one position. The API expects a body on this DELETE. Never retried."""
        payload = dump_body(ExitPositionRequest, body)
        data = http_sync.send_request(
            self._client, self._config, method="DELETE", path="/portfolio/positions/exit", auth="bearer",
            body=payload, cancel_event=cancel_event,
        )
        return parse(PositionExitResult, data)


class AsyncPortfolioResource:
    def __init__(self, client: httpx.AsyncClient, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    async def positions(self) -> Positions:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path="/portfolio/positions", auth="bearer",
        )
        return parse(Positions, data)

    async def holdings(self) -> Holdings:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path="/portfolio/holdings", auth="bearer",
        )
        return parse(Holdings, data)

    async def funds(self) -> Funds:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path="/portfolio/funds", auth="bearer",
        )
        return parse(Funds, data)

    async def convert_position(self, body: Body) -> PositionConvertResult:
        payload = dump_body(ConvertPositionRequest, body)
        data = await http_async.send_request(
            self._client, self._config, method="PATCH", path="/portfolio/positions/convert", auth="bearer",
            body=payload,
        )
        return parse(PositionConvertResult, data)

    async def exit_all_positions(self) -> PositionExitAllResult:
        data = await http_async.send_request(
            self._client, self._config, method="DELETE", path="/portfolio/positions/exit/all", auth="bearer",
        )
        return parse(PositionExitAllResult, data)

    async def exit_position(self, body: Body) -> PositionExitResult:
        payload = dump_body(ExitPositionRequest, body)
        data = await http_async.send_request(
            self._client, self._config, method="DELETE", path="/portfolio/positions/exit", auth="bearer",
            body=payload,
        )
        return parse(PositionExitResult, data)
