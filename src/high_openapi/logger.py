# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Logging, off by default, with redaction that every request path goes through.

A library that prints uninvited is a bad citizen in someone else's
application, so the default level is ``silent``. Each level prints itself and
everything more severe. Credentials never reach a log line: headers are never
logged at all, sensitive query parameters are redacted from URLs, and request
or response bodies are deep-redacted by key name.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from typing import Any, Callable, Optional, Protocol, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

LOG_LEVELS: Tuple[str, ...] = ("silent", "error", "warn", "info", "debug")

_RANK = {level: index for index, level in enumerate(LOG_LEVELS)}

_LEVELS_WITHOUT_SILENT = ("error", "warn", "info", "debug")


class LogSink(Protocol):
    """Anything that can receive the SDK's log lines. A plain object with
    ``error``/``warn``/``info``/``debug`` methods satisfies it."""

    def error(self, message: str, detail: Optional[Any] = None) -> None: ...

    def warn(self, message: str, detail: Optional[Any] = None) -> None: ...

    def info(self, message: str, detail: Optional[Any] = None) -> None: ...

    def debug(self, message: str, detail: Optional[Any] = None) -> None: ...


class Logger:
    """A logger already bound to a level and a sink."""

    def __init__(self, level: str, sink: LogSink):
        self._threshold = _RANK[level]
        self._sink = sink

    def enabled(self, level: str) -> bool:
        return _RANK[level] <= self._threshold

    def error(self, message: str, detail: Optional[Any] = None) -> None:
        self._emit("error", message, detail)

    def warn(self, message: str, detail: Optional[Any] = None) -> None:
        self._emit("warn", message, detail)

    def info(self, message: str, detail: Optional[Any] = None) -> None:
        self._emit("info", message, detail)

    def debug(self, message: str, detail: Optional[Any] = None) -> None:
        self._emit("debug", message, detail)

    def _emit(self, level: str, message: str, detail: Optional[Any]) -> None:
        if not self.enabled(level):
            return
        formatted = _format(level, message)
        sink_method: Callable[..., None] = getattr(self._sink, level)
        if detail is None:
            sink_method(formatted)
        else:
            sink_method(formatted, detail)


class _ConsoleSink:
    """Default sink: stderr for error/warn (matching console.error/warn),
    stdout for info/debug (matching console.info/debug)."""

    def error(self, message: str, detail: Optional[Any] = None) -> None:
        self._write(sys.stderr, message, detail)

    def warn(self, message: str, detail: Optional[Any] = None) -> None:
        self._write(sys.stderr, message, detail)

    def info(self, message: str, detail: Optional[Any] = None) -> None:
        self._write(sys.stdout, message, detail)

    def debug(self, message: str, detail: Optional[Any] = None) -> None:
        self._write(sys.stdout, message, detail)

    @staticmethod
    def _write(stream, message: str, detail: Optional[Any]) -> None:
        if detail is None:
            print(message, file=stream)
        else:
            print(message, detail, file=stream)


def _format(level: str, message: str) -> str:
    """``2026-09-28T17:05:12.345Z WARN  message`` — sortable, and the level
    column padded so lines stay aligned in a terminal."""
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.") + (
        f"{datetime.now(timezone.utc).microsecond // 1000:03d}Z"
    )
    return f"{timestamp} {level.upper():<5} {message}"


def create_logger(level: str, sink: Optional[LogSink] = None) -> Logger:
    """Builds a logger that drops anything below ``level``. Defaults to a
    console sink when none is supplied."""
    return Logger(level, sink if sink is not None else _ConsoleSink())


# Query parameters that must never reach a log sink. tOtp is a live second
# factor and the token parameters are bearer credentials.
_SENSITIVE_PARAMS = {"tOtp", "apiKey", "accessToken", "tokenId", "stepToken"}


def redact_url(url: str) -> str:
    """Replaces sensitive query parameter values with ``REDACTED``. Returns a
    malformed URL unchanged rather than raising — a logging helper must never
    turn an observability feature into an outage."""
    try:
        parsed = urlparse(url)
        if not parsed.scheme or not parsed.netloc:
            return url
        pairs = parse_qsl(parsed.query, keep_blank_values=True)
    except Exception:
        return url

    touched = False
    redacted_pairs = []
    for key, value in pairs:
        if key in _SENSITIVE_PARAMS:
            redacted_pairs.append((key, "REDACTED"))
            touched = True
        else:
            redacted_pairs.append((key, value))

    if not touched:
        return url

    new_query = urlencode(redacted_pairs)
    return urlunparse(parsed._replace(query=new_query))


# Object keys whose values must never be logged, at any nesting depth. Query
# parameters are handled by redact_url; this covers request and response
# bodies, which is where a future endpoint could start carrying a secret.
_SENSITIVE_KEYS = {
    "tOtp", "totp", "otp", "apiKey", "accessToken", "refreshToken",
    "tokenId", "stepToken", "password", "pin", "authorization",
    # The datafeed socket's auth frame credential (feed/client.py):
    # {"type": "cn", "sessionid": "<access token>"}.
    "sessionid",
}

# Above this many characters of serialised JSON, a logged payload is replaced
# by a note rather than printed.
_MAX_LOGGED_JSON = 1500


def redact_body(value: Any) -> Any:
    """Deep-copies a payload for logging, masking credential-shaped keys and
    replacing anything oversized with a note. Primitives and ``None`` pass
    through untouched."""
    if value is None or not isinstance(value, (dict, list)):
        return value

    def mask(item: Any) -> Any:
        if isinstance(item, list):
            return [mask(entry) for entry in item]
        if isinstance(item, dict):
            return {
                key: ("REDACTED" if key in _SENSITIVE_KEYS else mask(nested))
                for key, nested in item.items()
            }
        return item

    masked = mask(value)

    try:
        serialised = json.dumps(masked)
    except (TypeError, ValueError):
        return "[unserialisable]"

    if len(serialised) > _MAX_LOGGED_JSON:
        return f"[truncated: {len(serialised)} bytes of JSON]"
    return masked
