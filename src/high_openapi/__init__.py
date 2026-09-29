# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Official Python SDK for the HIGH Open API."""

from .client import AsyncHighClient, HighClient
from .config import ENVIRONMENTS, Environment, HighClientOptions, ResolvedConfig, resolve_config
from .errors import ERROR_CODES, HighApiError, OperationCancelled
from .feed import (
    AsyncHighFeed,
    Depth,
    DepthLevel,
    HighFeed,
    HighFeedAuthError,
    HighFeedError,
    HighFeedInvalidTokenError,
    HighFeedKeyError,
    HighFeedLimitError,
    HighFeedNoDataPlanError,
    IndexTick,
    Quote,
)
from .logger import LOG_LEVELS, Logger, LogSink, create_logger, redact_body, redact_url
from .resources.auth import AsyncAuthResource, AuthResource
from .resources.instruments import AsyncInstrumentsResource, InstrumentCategory, InstrumentRow, InstrumentsResource
from .resources.market import AsyncMarketResource, MarketResource
from .resources.orders import AsyncOrdersResource, OrdersResource
from .resources.portfolio import AsyncPortfolioResource, PortfolioResource
from .resources.scrips import AsyncScripsResource, ExpiryType, ScripsResource

__version__ = "0.0.1"

__all__ = [
    "__version__",
    "HighClient",
    "AsyncHighClient",
    "ENVIRONMENTS",
    "Environment",
    "HighClientOptions",
    "ResolvedConfig",
    "resolve_config",
    "ERROR_CODES",
    "HighApiError",
    "OperationCancelled",
    "LOG_LEVELS",
    "Logger",
    "LogSink",
    "create_logger",
    "redact_body",
    "redact_url",
    "AuthResource",
    "AsyncAuthResource",
    "InstrumentsResource",
    "AsyncInstrumentsResource",
    "InstrumentCategory",
    "InstrumentRow",
    "MarketResource",
    "AsyncMarketResource",
    "OrdersResource",
    "AsyncOrdersResource",
    "PortfolioResource",
    "AsyncPortfolioResource",
    "ScripsResource",
    "AsyncScripsResource",
    "ExpiryType",
    "AsyncHighFeed",
    "HighFeed",
    "HighFeedError",
    "HighFeedAuthError",
    "HighFeedNoDataPlanError",
    "HighFeedInvalidTokenError",
    "HighFeedKeyError",
    "HighFeedLimitError",
    "Quote",
    "Depth",
    "DepthLevel",
    "IndexTick",
]
