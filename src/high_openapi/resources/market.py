# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from __future__ import annotations

import httpx

from .. import http_async, http_sync
from ..config import ResolvedConfig
from ..generated.models import MarketStatus
from ._shared import parse


class MarketResource:
    def __init__(self, client: httpx.Client, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    def status(self, *, cancel_event=None) -> MarketStatus:
        """Session state per exchange for today."""
        data = http_sync.send_request(
            self._client, self._config, method="GET", path="/market/status", auth="bearer",
            cancel_event=cancel_event,
        )
        return parse(MarketStatus, data)


class AsyncMarketResource:
    def __init__(self, client: httpx.AsyncClient, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config

    async def status(self) -> MarketStatus:
        data = await http_async.send_request(
            self._client, self._config, method="GET", path="/market/status", auth="bearer",
        )
        return parse(MarketStatus, data)
