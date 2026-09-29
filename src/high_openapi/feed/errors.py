# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Errors raised by the datafeed client.

Deliberately not ``HighApiError`` — the feed is not an HTTP resource, it has
no ``status`` code, no ``requestId``, and its own auth gate carries a
different shape (``stCode``/``msg``, not the REST envelope). Giving it its
own hierarchy keeps a caller from writing ``except HighApiError`` and
accidentally swallowing a feed failure it did not mean to catch, or vice
versa.
"""

from __future__ import annotations

from typing import Optional


class HighFeedError(Exception):
    """Base of every error this client raises."""


class HighFeedKeyError(HighFeedError):
    """A scrip key could not be translated to a feed instrument, or was
    passed to the wrong subscription method. Always names the offending key.

    Raised for: an unsupported or unknown key prefix, a segment the feed does
    not cover (MCX spot), an index key missing from the committed table, an
    index key passed to ``subscribe_quotes``/``subscribe_depth`` (must use
    ``subscribe_indices``), and a non-index key passed to
    ``subscribe_indices``. See :class:`HighFeedAmbiguousIndexError` for the
    fourth, more specific case.
    """

    def __init__(self, message: str, *, key: str) -> None:
        super().__init__(message)
        self.key = key


class HighFeedAmbiguousIndexError(HighFeedKeyError):
    """A scrip key the scrip master maps to more than one distinct index —
    a confirmed data defect, not a translation bug (six keys, as of this
    writing; see ``feed/_index_map.py``'s ``AMBIGUOUS_INDEX_KEYS``).

    Deliberately never resolved automatically. Any resolution — first
    match, last match, alphabetical — is a coin flip a caller cannot detect:
    the wrong index streams under the right scrip key, with plausible-looking
    prices, and nothing about the response says so. Raising by name, with
    both candidates, is the only safe behaviour until the scrip master's own
    data is fixed upstream.
    """

    def __init__(self, message: str, *, key: str, candidates) -> None:
        super().__init__(message, key=key)
        self.candidates = tuple(candidates)


class HighFeedLimitError(HighFeedError):
    """A subscription would exceed the connection's ``maxScripPerConn``,
    read off the auth acknowledgement. Never silently truncated."""

    def __init__(self, message: str, *, requested: int, limit: int) -> None:
        super().__init__(message)
        self.requested = requested
        self.limit = limit


class HighFeedAuthError(HighFeedError):
    """The auth frame's acknowledgement carried ``"stat":"NotOk"``. Carries
    the gateway's own ``stCode`` and ``msg`` intact — a failed auth is never
    retried and never triggers a reconnect, because the server will keep
    refusing (see :class:`~high_openapi.feed.client.AsyncHighFeed`).

    The exact ``stCode`` the gateway uses for a missing data plan versus an
    invalid token is not yet pinned (see the datafeed plan, Phase 0) — the
    two named subclasses below are selected from the acknowledgement's ``msg``
    text on a best-effort basis. Anything that does not match either pattern
    raises this base class directly, with ``stCode``/``msg`` intact rather
    than flattened into a generic message, exactly as an unrecognised code
    should.
    """

    def __init__(self, message: str, *, st_code: int, msg: str) -> None:
        super().__init__(message)
        self.st_code = st_code
        self.msg = msg


class HighFeedNoDataPlanError(HighFeedAuthError):
    """The account has no active Data API subscription."""


class HighFeedInvalidTokenError(HighFeedAuthError):
    """The access token was rejected — missing, malformed, or expired."""


def auth_error_from_ack(st_code: int, msg: Optional[str]) -> HighFeedAuthError:
    """Classifies a ``"stat":"NotOk"`` auth acknowledgement. See
    :class:`HighFeedAuthError` for why this is a best-effort text match
    rather than a closed code table."""
    text = (msg or "").strip()
    lowered = text.lower()

    if "plan" in lowered or "subscription" in lowered or "not subscribed" in lowered:
        return HighFeedNoDataPlanError(
            f"HIGH feed auth failed (no data plan): {text or 'no message'} (stCode {st_code})",
            st_code=st_code, msg=text,
        )
    # "invalid field count" (documented stCode 11002) is a malformed request,
    # not a bad token — excluded here so it falls through to the generic case.
    if ("token" in lowered or "session" in lowered or "expired" in lowered) or (
        "invalid" in lowered and "field" not in lowered
    ):
        return HighFeedInvalidTokenError(
            f"HIGH feed auth failed (invalid or expired token): {text or 'no message'} (stCode {st_code})",
            st_code=st_code, msg=text,
        )
    return HighFeedAuthError(
        f"HIGH feed auth failed: {text or 'no message'} (stCode {st_code})", st_code=st_code, msg=text,
    )
