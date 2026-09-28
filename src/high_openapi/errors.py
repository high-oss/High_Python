# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""The one error type every SDK failure surfaces as.

``code`` is an open string, not a closed enum: the gateway emits far more
codes than the documented catalogue, and a closed type would turn a
recoverable business error into a deserialisation crash. ``ERROR_CODES`` is
the documented catalogue for comparison only — a test (test_generated_types)
asserts it still matches the pinned spec's ``Error.code['x-error-codes']``.
"""

from __future__ import annotations

from typing import Any, List, Optional

# The documented error catalogue, from the spec's Error.code['x-error-codes'].
ERROR_CODES: tuple = (
    "INVALID_API_KEY",
    "INVALID_CONSENT",
    "INVALID_DATE",
    "INVALID_SCRIP",
    "INVALID_TOKEN",
    "INVALID_TOKEN_ID",
    "INVALID_TOTP",
    "ORDER_DETAILS_INVALID",
    "ORDER_NOT_CANCELLABLE",
    "ORDER_NOT_FOUND",
    "ORDER_REJECTED",
    "ORDER_STATUS_UNKNOWN",
    "OWNER_MISMATCH",
    "POSITION_CONVERT_FAILED",
    "POSITION_NOT_EXITABLE",
    "POSITION_SQUARE_OFF_FAILED",
    "QUANTITY_NOT_IN_LOTS",
    "REDIRECT_URL_NOT_CONFIGURED",
    "SANDBOX_TOKEN_NOT_ALLOWED",
    "SCRIP_NOT_FOUND",
    "SERVICE_UNAVAILABLE",
    "SESSION_EXPIRED",
    "SESSION_NOT_GENERATED",
    "STATIC_IP_MISMATCH",
    "STATIC_IP_MISSING",
    "TOTP_NOT_ENABLED",
    "UNHANDLED_ERROR",
    "VALIDATION_ERROR",
    "WRONG_TOKEN_AUDIENCE",
)


class HighApiError(Exception):
    """Every failure the SDK surfaces — transport, timeout, or an API error
    response. Transport failures and timeouts carry ``status=0``."""

    def __init__(
        self,
        message: str,
        *,
        status: int,
        code: Optional[str] = None,
        request_id: Optional[str] = None,
        messages: Optional[List[str]] = None,
        body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        # Quote this in support tickets.
        self.request_id = request_id
        # Every message the API returned; validation errors return several.
        self.messages = messages
        # The parsed body, when there was one.
        self.body = body


class OperationCancelled(Exception):
    """Raised by the sync client when a caller-supplied ``cancel_event`` was
    set before an attempt was sent, or during a retry delay. Deliberately not
    a ``HighApiError`` — a cancellation is the caller's own decision, not an
    API or transport failure, and must never be retried or mistaken for a
    timeout. The async client instead lets ``asyncio.CancelledError`` from a
    cancelled task propagate unchanged; this type is its sync equivalent."""


def _as_dict(value: Any) -> Optional[dict]:
    return value if isinstance(value, dict) else None


def _as_str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) else None


def _messages_of(value: Any) -> Optional[List[str]]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        strings = [item for item in value if isinstance(item, str)]
        return strings or None
    return None


def error_from_response(status: int, body: Any, fallback_text: Optional[str] = None) -> HighApiError:
    """Builds the error for a non-2xx response. ``body`` is the parsed JSON
    when the response had any; ``fallback_text`` is the raw text when it did
    not — a proxy or load balancer failure returns HTML, and losing that to a
    JSON parse error would hide the status the caller needs."""
    record = _as_dict(body)
    messages = _messages_of(record.get("message") if record else None)
    snippet = fallback_text.strip()[:200] if fallback_text else None

    if messages:
        message = "; ".join(messages)
    elif snippet:
        message = f"HTTP {status}: {snippet}"
    else:
        message = f"HTTP {status}"

    return HighApiError(
        message,
        status=status,
        code=_as_str(record.get("code")) if record else None,
        request_id=_as_str(record.get("requestId")) if record else None,
        messages=messages,
        body=body if body is not None else fallback_text,
    )
