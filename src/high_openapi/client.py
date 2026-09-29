# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""The HIGH Open API client — sync and async.

::

    from high_openapi import HighClient

    high = HighClient(environment="sandbox", api_key=api_key, access_token=access_token)
    funds = high.portfolio.funds()

::

    from high_openapi import AsyncHighClient

    async with AsyncHighClient(access_token=access_token) as high:
        funds = await high.portfolio.funds()

Credential containment: ``api_key``/``access_token`` are never attributes of
``ResolvedConfig``'s own ``__dict__`` (see config.py) — they live in a
module-private WeakKeyDictionary — so nothing on the client, a resource, or
the config object ever puts them in ``repr()``, ``str()``, ``vars()`` or
``pickle``'s default reducer. Nothing extra is needed here to get that
guarantee; it holds simply because neither this class nor the resource
classes ever copy the credential into an attribute of their own.
"""

from __future__ import annotations

from typing import Any, Mapping, Optional

import httpx

from . import http_async, http_sync
from .config import ResolvedConfig, resolve_config
from .resources.auth import AsyncAuthResource, AuthResource
from .resources.instruments import AsyncInstrumentsResource, InstrumentsResource
from .resources.market import AsyncMarketResource, MarketResource
from .resources.orders import AsyncOrdersResource, OrdersResource
from .resources.portfolio import AsyncPortfolioResource, PortfolioResource
from .resources.scrips import AsyncScripsResource, ScripsResource


class HighClient:
    """Synchronous client. Owns one pooled ``httpx.Client`` for its lifetime;
    call :meth:`close` (or use it as a context manager) when done."""

    def __init__(
        self,
        options: Optional[Mapping[str, Any]] = None,
        *,
        env: Optional[Mapping[str, str]] = None,
        **kwargs: Any,
    ) -> None:
        merged: dict = dict(options or {})
        merged.update(kwargs)
        self.config: ResolvedConfig = resolve_config(merged, env)
        self._client: httpx.Client = self.config.http_client or http_sync.new_client(self.config)

        self.auth = AuthResource(self._client, self.config)
        self.instruments = InstrumentsResource(self._client, self.config)
        self.market = MarketResource(self._client, self.config)
        self.orders = OrdersResource(self._client, self.config)
        self.portfolio = PortfolioResource(self._client, self.config)
        self.scrips = ScripsResource(self._client, self.config)

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "HighClient":
        return self

    def __exit__(self, *exc_info: Any) -> None:
        self.close()

    def __repr__(self) -> str:
        return (
            f"HighClient(base_url={self.config.base_url!r}, "
            f"version_path={self.config.version_path!r}, log_level={self.config.log_level!r})"
        )


class AsyncHighClient:
    """Asynchronous client. Owns one pooled ``httpx.AsyncClient`` for its
    lifetime; call :meth:`aclose` (or use it as an async context manager)
    when done."""

    def __init__(
        self,
        options: Optional[Mapping[str, Any]] = None,
        *,
        env: Optional[Mapping[str, str]] = None,
        **kwargs: Any,
    ) -> None:
        merged: dict = dict(options or {})
        merged.update(kwargs)
        self.config: ResolvedConfig = resolve_config(merged, env)
        self._client: httpx.AsyncClient = self.config.http_client or http_async.new_client(self.config)

        self.auth = AsyncAuthResource(self._client, self.config)
        self.instruments = AsyncInstrumentsResource(self._client, self.config)
        self.market = AsyncMarketResource(self._client, self.config)
        self.orders = AsyncOrdersResource(self._client, self.config)
        self.portfolio = AsyncPortfolioResource(self._client, self.config)
        self.scrips = AsyncScripsResource(self._client, self.config)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> "AsyncHighClient":
        return self

    async def __aexit__(self, *exc_info: Any) -> None:
        await self.aclose()

    def __repr__(self) -> str:
        return (
            f"AsyncHighClient(base_url={self.config.base_url!r}, "
            f"version_path={self.config.version_path!r}, log_level={self.config.log_level!r})"
        )
