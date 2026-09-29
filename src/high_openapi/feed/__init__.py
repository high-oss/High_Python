# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""The HIGH live datafeed client — a separate client beside ``HighClient``,
built over a raw WebSocket. See :mod:`high_openapi.feed.client` for the
public ``AsyncHighFeed`` / ``HighFeed`` classes, and the package README's
"Live datafeed" section for usage.
"""

from __future__ import annotations

from .client import AsyncHighFeed, HighFeed
from .errors import (
    HighFeedAmbiguousIndexError,
    HighFeedAuthError,
    HighFeedError,
    HighFeedInvalidTokenError,
    HighFeedKeyError,
    HighFeedLimitError,
    HighFeedNoDataPlanError,
)
from .models import Depth, DepthLevel, IndexTick, Quote

__all__ = [
    "AsyncHighFeed",
    "HighFeed",
    "HighFeedError",
    "HighFeedAuthError",
    "HighFeedNoDataPlanError",
    "HighFeedInvalidTokenError",
    "HighFeedKeyError",
    "HighFeedAmbiguousIndexError",
    "HighFeedLimitError",
    "Quote",
    "Depth",
    "DepthLevel",
    "IndexTick",
]
