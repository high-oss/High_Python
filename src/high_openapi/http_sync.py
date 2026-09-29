# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Sends one HIGH operation and returns its unwrapped ``data``, synchronously.

Retries apply to idempotent reads only (GET/HEAD), on 429 and 5xx, honouring
``Retry-After`` when present and backing off exponentially when it is not.
Writes are never retried. Transport failures and timeouts are never retried
either — they raise immediately, matching the reference Node SDK, which
raises out of its per-attempt helper before the retry decision ever runs.

Cancellation: an optional ``cancel_event`` (``threading.Event``) is checked
before each attempt is sent and is interruptible during a retry delay. Python
synchronous socket I/O has no cooperative-cancellation hook (unlike JS's
``AbortSignal``), so setting the event cannot abort a request already handed
to ``httpx``'s blocking ``send()`` — this is a documented limitation, not an
oversight. See the README's Cancellation section.
"""

from __future__ import annotations

import json
import time
from typing import Any, Mapping, Optional

import httpx

from ._engine import RETRYABLE_STATUSES, backoff_ms, encode_query, is_retryable_method, retry_after_ms
from .config import ResolvedConfig, build_url
from .errors import HighApiError, OperationCancelled, error_from_response
from .logger import redact_body, redact_url


def new_client(config: ResolvedConfig) -> httpx.Client:
    """The default transport, used when no ``http_client`` override is given.
    A single client is reused for a `HighClient`'s whole lifetime, so
    connections are pooled across calls."""
    return httpx.Client(timeout=httpx.Timeout(config.timeout_ms / 1000))


def headers_for(config: ResolvedConfig, auth: str, has_body: bool) -> dict:
    headers = {"accept": "application/json", "user-agent": config.user_agent}
    if auth == "bearer":
        if not config.access_token:
            raise HighApiError(
                "This operation needs an access_token. Pass it to the client, or set HIGH_ACCESS_TOKEN.",
                status=0,
            )
        headers["authorization"] = f"Bearer {config.access_token}"
    elif auth == "none":
        # The instrument list manifest and its CSV downloads: no credential
        # of any kind, even when the client was constructed with one — the
        # CSV host is a third-party CDN and a bearer token sent to it would
        # leak it.
        pass
    else:
        if not config.api_key:
            raise HighApiError(
                "This operation needs an api_key. Pass it to the client, or set HIGH_API_KEY.",
                status=0,
            )
        headers["x-api-key"] = config.api_key
    if has_body:
        headers["content-type"] = "application/json"
    return headers


def url_for(config: ResolvedConfig, path: str, query: Optional[Mapping[str, Any]]) -> str:
    url = build_url(config, path)
    qs = encode_query(query)
    return f"{url}?{qs}" if qs else url


def _sleep(seconds: float, cancel_event) -> None:
    if cancel_event is None:
        time.sleep(seconds)
        return
    # Event.wait returns True the moment the event is set, unlike an
    # uninterruptible time.sleep — an uninterruptible sleep would let a
    # cancelled call go on to issue its next retry, exactly what a caller
    # asked not to happen.
    if cancel_event.wait(seconds):
        raise OperationCancelled("Operation cancelled during a retry delay.")


def _attempt(
    client: httpx.Client,
    config: ResolvedConfig,
    method: str,
    url: str,
    headers: dict,
    content: Optional[bytes],
    timeout_ms: Optional[float] = None,
):
    # Headers are never logged — they carry the bearer token and the api key.
    config.logger.debug(
        f"HIGH -> {method.upper()} {redact_url(url)}",
        None if content is None else {"body": redact_body(json.loads(content))},
    )
    config.logger.info(f"HIGH {method.upper()} {redact_url(url)}")

    effective_timeout_ms = timeout_ms if timeout_ms is not None else config.timeout_ms
    started = time.monotonic()
    try:
        # The per-request timeout goes on build_request (it lands in the
        # Request's own extensions), not on send() — httpx.Client.send()
        # takes no timeout keyword of its own.
        request_obj = client.build_request(
            method, url, headers=headers, content=content, timeout=httpx.Timeout(effective_timeout_ms / 1000),
        )
        response = client.send(request_obj)
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


def send_request(
    client: httpx.Client,
    config: ResolvedConfig,
    *,
    method: str,
    path: str,
    auth: str,
    query: Optional[Mapping[str, Any]] = None,
    body: Any = None,
    cancel_event=None,
    timeout_ms: Optional[float] = None,
) -> Any:
    """``timeout_ms`` overrides ``config.timeout_ms`` for this call only — the
    instrument list manifest is a small JSON response, but its caller may
    already be working under a raised per-call ceiling for the CSV download
    that follows it (see resources/instruments.py), and the two should agree."""
    headers = headers_for(config, auth, body is not None)
    url = url_for(config, path, query)
    content = json.dumps(body, separators=(",", ":")).encode("utf-8") if body is not None else None

    retryable = is_retryable_method(method)
    max_attempts = config.max_retries + 1 if retryable else 1

    last_error: Optional[HighApiError] = None
    for index in range(max_attempts):
        if cancel_event is not None and cancel_event.is_set():
            raise OperationCancelled("Operation cancelled before the request was sent.")

        status, data, error, retry_after = _attempt(client, config, method, url, headers, content, timeout_ms)
        if error is None:
            return data
        last_error = error

        if not retryable or status not in RETRYABLE_STATUSES or index == max_attempts - 1:
            raise error

        delay_ms = retry_after if retry_after is not None else backoff_ms(index)

        # A Retry-After past the ceiling means "come back much later", not
        # "block this call" — a misconfigured rate limiter can legally send
        # Retry-After: 86400, and waiting it out is worse than failing now.
        if delay_ms > config.max_retry_delay_ms:
            config.logger.warn(
                f"HIGH giving up: server asked for {delay_ms:.0f}ms, over the "
                f"{config.max_retry_delay_ms:.0f}ms ceiling {redact_url(url)}"
            )
            raise error

        config.logger.warn(
            f"HIGH retry {index + 1}/{max_attempts - 1} after {delay_ms:.0f}ms (HTTP {status}) {redact_url(url)}"
        )
        _sleep(delay_ms / 1000, cancel_event)

    raise last_error  # pragma: no cover — loop always returns or raises above
