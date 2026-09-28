# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Pure, I/O-free decision helpers shared by the sync and async HTTP engines.

Kept separate from http_sync.py / http_async.py so the retry/backoff/query
logic is defined exactly once and tested without a network at all.
"""

from __future__ import annotations

import random
from email.utils import parsedate_to_datetime
from typing import Any, Dict, Mapping, Optional
from urllib.parse import urlencode

# Statuses worth trying again on an idempotent operation.
RETRYABLE_STATUSES = {429, 500, 502, 503, 504}

# Only reads are retried. A retried POST /orders would be a duplicate order.
# The method check is case-insensitive — callers may pass lowercase.
IDEMPOTENT_METHODS = {"GET", "HEAD"}


def is_retryable_method(method: str) -> bool:
    return method.upper() in IDEMPOTENT_METHODS


def backoff_ms(attempt_index: int) -> float:
    """Exponential backoff with jitter, used when the server gave no
    Retry-After."""
    return 250 * (2**attempt_index) + random.randint(0, 99)


def retry_after_ms(header: Optional[str], now_ms: Optional[float] = None) -> Optional[float]:
    """Parses a Retry-After header, in either of its two legal forms: a delay
    in seconds, or an HTTP-date. Never returns a negative delay. Returns
    ``None`` for a missing or unparseable header, so backoff takes over."""
    if not header:
        return None

    try:
        seconds = float(header)
        if seconds >= 0:
            return seconds * 1000
    except ValueError:
        pass

    try:
        at = parsedate_to_datetime(header)
    except (TypeError, ValueError):
        return None
    if at is None:
        return None

    if now_ms is None:
        from datetime import datetime, timezone

        now_ms = datetime.now(timezone.utc).timestamp() * 1000
    at_ms = at.timestamp() * 1000
    return max(0.0, at_ms - now_ms)


def query_string_value(value: Any) -> str:
    """Mirrors JS's ``String(value)`` for the value types this SDK sends as
    query parameters: lowercase booleans, plain numbers and strings."""
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)


def encode_query(query: Optional[Mapping[str, Any]]) -> str:
    """Builds a query string, skipping ``None`` values entirely — an unset
    optional parameter must not reach the wire as the literal text
    ``"None"``."""
    if not query:
        return ""
    pairs = [(key, query_string_value(value)) for key, value in query.items() if value is not None]
    return urlencode(pairs)
