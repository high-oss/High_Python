# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Key translation: a HIGH scrip key in, a feed instrument identifier out.

Per the datafeed plan's Phase 1, this never makes a network call and never
parses JSON at runtime — the index table is the committed
:mod:`high_openapi.feed._index_map` module, generated ahead of time by
``scripts/regenerate_index_map.py``.

**The index lookup runs first.** Indices share the ``NSE@``/``BSE@`` prefix
with cash scrips (``NSE@26000`` is Nifty 50, not a token), so a key is
checked against the index table before the prefix rule is even considered.

This module also enforces the split the public surface asks for:
``translate_index`` only ever succeeds for a key in the index table, and
``translate_instrument`` (used by the quote and depth subscription methods)
refuses a key that *is* an index — including an ambiguous one — a caller
must use the index methods for those, not fall through to a prefix guess
that would silently subscribe to a token the feed does not know (see the
module docstring on ``high_openapi.feed.client``).

**A third, distinct rejection**, alongside "not an index" and "an index the
feed does not carry": a scrip key the live scrip master maps to more than
one different index (a confirmed data defect — see
``_index_map.AMBIGUOUS_INDEX_KEYS`` and
:class:`~high_openapi.feed.errors.HighFeedAmbiguousIndexError`). These are
never resolved automatically, in either direction: ``translate_index``
raises naming both candidates, and ``translate_instrument`` treats the key
as an index too (not a plain token) so it is never silently subscribed
under the ordinary prefix rule.
"""

from __future__ import annotations

from typing import Tuple

from ._index_map import AMBIGUOUS_INDEX_KEYS, INDEX_FEED_MAP
from .errors import HighFeedAmbiguousIndexError, HighFeedKeyError

# Key prefix -> feed segment, for every non-index key. Closed set, checked
# before any translation — an unknown prefix is an error, never a guess.
# MCX spot (`MCX@`) is a recognised prefix with a *known-absent* feed code:
# it gets its own message rather than falling into "unknown prefix".
_PREFIX_SEGMENTS = {
    "NSE": "nse_cm",
    "BSE": "bse_cm",
    "NSEFO": "nse_fo",
    "BSEFO": "bse_fo",
    "MCXFO": "mcx_fo",
}

_NO_FEED_CODE = {
    "MCX": "MCX spot has no known feed code",
}


def _split(scrip_key: str) -> Tuple[str, str]:
    if not isinstance(scrip_key, str) or "@" not in scrip_key:
        raise HighFeedKeyError(
            f"{scrip_key!r} is not a HIGH scrip key (expected \"EXCHANGE@identifier\", e.g. \"NSE@15563\").",
            key=scrip_key,
        )
    exchange, _, identifier = scrip_key.partition("@")
    if exchange == "" or identifier == "":
        raise HighFeedKeyError(
            f"{scrip_key!r} is not a HIGH scrip key (expected \"EXCHANGE@identifier\", e.g. \"NSE@15563\").",
            key=scrip_key,
        )
    return exchange, identifier


def is_index_key(scrip_key: str) -> bool:
    """True for any key the scrip master treats as an index — including an
    ambiguous one. Deliberately not limited to ``INDEX_FEED_MAP``:
    ``translate_instrument`` relies on this to keep an ambiguous key out of
    the ordinary prefix rule too, not just an unambiguous one."""
    return scrip_key in INDEX_FEED_MAP or scrip_key in AMBIGUOUS_INDEX_KEYS


def translate_index(scrip_key: str) -> Tuple[str, str]:
    """``scripKey`` -> ``(feedSegment, feedSymbol)`` for an index.

    Three distinct rejections, all :class:`HighFeedKeyError` naming the key:

    - the key is not an index at all, or is one of the handful of upstream
      index rows the feed does not carry (absent from the committed table);
    - the key is **ambiguous** — the scrip master maps it to more than one
      different index — raised as the more specific
      :class:`~high_openapi.feed.errors.HighFeedAmbiguousIndexError`,
      carrying both candidate names, rather than guessing.
    """
    if scrip_key in AMBIGUOUS_INDEX_KEYS:
        candidates = AMBIGUOUS_INDEX_KEYS[scrip_key]
        raise HighFeedAmbiguousIndexError(
            f"{scrip_key!r} is ambiguous: the scrip master maps it to more than one index "
            f"({', '.join(candidates)}), and there is no safe way to pick one automatically. "
            f"This is a data defect to resolve upstream, not something subscribe_indices can guess at.",
            key=scrip_key, candidates=candidates,
        )

    entry = INDEX_FEED_MAP.get(scrip_key)
    if entry is None:
        raise HighFeedKeyError(
            f"{scrip_key!r} is not a known index (or the feed does not carry it — a handful of upstream "
            f"index rows have no feed counterpart and are deliberately absent from the table). "
            f"subscribe_indices only accepts keys from the committed index table.",
            key=scrip_key,
        )
    return entry


def translate_instrument(scrip_key: str) -> Tuple[str, str]:
    """``scripKey`` -> ``(feedSegment, feedToken)`` for a non-index
    instrument (quote or depth). Raises :class:`HighFeedKeyError` naming the
    key for: an index key, ambiguous or not (use
    ``subscribe_indices``/``unsubscribe_indices``/``snapshot_indices``
    instead), an unsupported segment (MCX spot), or an unknown key prefix."""
    if is_index_key(scrip_key):
        raise HighFeedKeyError(
            f"{scrip_key!r} is an index key. Use subscribe_indices / unsubscribe_indices / "
            f"snapshot_indices for it, not the quote or depth methods.",
            key=scrip_key,
        )

    exchange, identifier = _split(scrip_key)

    if exchange in _NO_FEED_CODE:
        raise HighFeedKeyError(
            f"{scrip_key!r} cannot be subscribed on the datafeed: {_NO_FEED_CODE[exchange]}.",
            key=scrip_key,
        )

    segment = _PREFIX_SEGMENTS.get(exchange)
    if segment is None:
        raise HighFeedKeyError(
            f"{scrip_key!r} has an unsupported prefix ({exchange!r}@). The datafeed covers: "
            f"{', '.join(sorted(_PREFIX_SEGMENTS))} (by token), plus index keys from the committed table.",
            key=scrip_key,
        )

    return segment, identifier
