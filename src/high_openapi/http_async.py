# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Sends one HIGH operation and returns its unwrapped ``data``, asynchronously.

Same retry/backoff/error-mapping behaviour as ``http_sync.py`` — see that
module's docstring — implemented over ``httpx.AsyncClient``.

Cancellation is native Python: no explicit cancellation parameter is
accepted. Cancelling the enclosing ``asyncio.Task`` (``task.cancel()``) is
the idiomatic mechanism, and it is honoured both mid-request (``httpx``
awaits the underlying anyio/asyncio socket operations, which raise
``asyncio.CancelledError`` when cancelled) and mid-retry-delay (``asyncio.
sleep`` is itself cancellable). Nothing here catches ``CancelledError`` — it
is a ``BaseException``, not caught by the ``Exception``-rooted ``except``
clauses below, so it always propagates unchanged, exactly as the contract
requires.
"""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any, Mapping, Optional

import httpx

from ._engine import RETRYABLE_STATUSES, backoff_ms, is_retryable_method, retry_after_ms
from .config import ResolvedConfig
from .errors import HighApiError, error_from_response
from .http_sync import headers_for, url_for  # pure helpers, shared as-is
from .logger import redact_body, redact_url


def new_client(config: ResolvedConfig) -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(config.timeout_ms / 1000))


async def _attempt(
    client: httpx.AsyncClient,
    config: ResolvedConfig,
    method: str,
    url: str,
    headers: dict,
    content: Optional[bytes],
    timeout_ms: Optional[float] = None,
):
    config.logger.debug(
        f"HIGH -> {method.upper()} {redact_url(url)}",
        None if content is None else {"body": redact_body(json.loads(content))},
    )
    config.logger.info(f"HIGH {method.upper()} {redact_url(url)}")

    effective_timeout_ms = timeout_ms if timeout_ms is not None else config.timeout_ms
    started = time.monotonic()
    try:
        request_obj = client.build_request(
            method, url, headers=headers, content=content, timeout=httpx.Timeout(effective_timeout_ms / 1000),
        )
        response = await client.send(request_obj)
    except httpx.TimeoutException as exc:
        config.logger.error(f"HIGH <- timeout after {effective_timeout_ms}ms {redact_url(url)}")
        raise HighApiError(f"Request timed out after {effective_timeout_ms}ms", status=0, body=exc) from exc
    except httpx.HTTPError as exc:
        config.logger.error(f"HIGH <- transport failure {redact_url(url)}", str(exc))
        raise HighApiError(f"Request failed: {exc}", status=0, body=exc) from exc

    text = response.text
    elapsed_ms = (time.monotonic() - started) * 1000

    parsed: Any = None
    parse_failed = False
    if text != "":
        try:
            parsed = json.loads(text)
        except ValueError:
            parse_failed = True

    envelope = None if parse_failed else parsed
    request_id = envelope.get("requestId") if isinstance(envelope, dict) else None

    config.logger.debug(
        f"HIGH <- {response.status_code} in {elapsed_ms:.0f}ms {redact_url(url)}",
        {"requestId": request_id, "body": redact_body(text[:200] if parse_failed else parsed)},
    )

    if not response.is_success:
        error = error_from_response(response.status_code, None if parse_failed else parsed, text)
        config.logger.error(
            f"HIGH <- {response.status_code} {error.code or 'no code'} in {elapsed_ms:.0f}ms {redact_url(url)}",
            {"requestId": error.request_id, "messages": error.messages},
        )
        return response.status_code, None, error, retry_after_ms(response.headers.get("retry-after"))

    if parse_failed:
        error = HighApiError("Expected JSON but the response was not parseable", status=response.status_code, body=text)
        return response.status_code, None, error, None

    data = envelope.get("data") if isinstance(envelope, dict) else None
    return response.status_code, data, None, None


async def send_request(
    client: httpx.AsyncClient,
    config: ResolvedConfig,
    *,
    method: str,
    path: str,
    auth: str,
    query: Optional[Mapping[str, Any]] = None,
    body: Any = None,
    timeout_ms: Optional[float] = None,
) -> Any:
    headers = headers_for(config, auth, body is not None)
    url = url_for(config, path, query)
    content = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None

    retryable = is_retryable_method(method)
    max_attempts = config.max_retries + 1 if retryable else 1

    last_error: Optional[HighApiError] = None
    for index in range(max_attempts):
        status, data, error, retry_after = await _attempt(client, config, method, url, headers, content, timeout_ms)
        if error is None:
            return data
        last_error = error

        if not retryable or status not in RETRYABLE_STATUSES or index == max_attempts - 1:
            raise error

        delay_ms = retry_after if retry_after is not None else backoff_ms(index)

        if delay_ms > config.max_retry_delay_ms:
            config.logger.warn(
                f"HIGH giving up: server asked for {delay_ms:.0f}ms, over the "
                f"{config.max_retry_delay_ms:.0f}ms ceiling {redact_url(url)}"
            )
            raise error

        config.logger.warn(
            f"HIGH retry {index + 1}/{max_attempts - 1} after {delay_ms:.0f}ms (HTTP {status}) {redact_url(url)}"
        )
        # asyncio.sleep is natively cancellable — a cancelled task raises
        # CancelledError here rather than sleeping through to another retry.
        await asyncio.sleep(delay_ms / 1000)

    raise last_error  # pragma: no cover — loop always returns or raises above
