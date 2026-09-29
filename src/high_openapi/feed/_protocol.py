# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Pure, I/O-free wire-protocol logic: frame builders, message
classification, and the delta-merge engine. Kept separate from client.py —
which owns the socket, the reconnect loop and the two public client shapes —
so this can be unit tested without a network at all, mirroring how
``_engine.py`` holds the REST engine's pure retry/backoff decisions.

Delivery routing is by the wire's ``t`` discriminator on each tick item —
``"sf"`` scrip (quote), ``"dp"`` depth, ``"if"`` index — never by guessing
from which keys happen to be present on the object (datafeed plan, "One
frame, two events").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple

from .errors import auth_error_from_ack
from .models import (
    INDEX_FIELDS,
    QUOTE_FIELDS,
    TOP_OF_BOOK_ASK_PRICE_KEY,
    TOP_OF_BOOK_ASK_QTY_KEY,
    TOP_OF_BOOK_BID_PRICE_KEY,
    TOP_OF_BOOK_BID_QTY_KEY,
    TOP_OF_BOOK_WIRE_KEYS,
    DEPTH_ASK_ORDER_KEYS,
    DEPTH_ASK_PRICE_KEYS,
    DEPTH_ASK_QTY_KEYS,
    DEPTH_BID_ORDER_KEYS,
    DEPTH_BID_PRICE_KEYS,
    DEPTH_BID_QTY_KEYS,
    DEPTH_KEY_PARSERS,
    Depth,
    DepthLevel,
    IndexTick,
    Quote,
    parse_decimal,
    parse_int,
)

# Subscription kind -> request type prefix (datafeed plan, "Subscribe").
TYPE_PREFIX = {"quote": "mw", "depth": "dp", "index": "if"}

# Subscription kind -> the `t` discriminator a delivered tick carries.
ROUTE_TAG = {"quote": "sf", "depth": "dp", "index": "if"}

_META_KEYS = frozenset({"t", "e", "tk"})


# --------------------------------------------------------------------------
# Frame builders — every one is a plain dict, JSON-encoded by the caller.
# --------------------------------------------------------------------------


def auth_frame(session_id: str) -> dict:
    # No "mode": it is filled in server-side from the customer's data plan —
    # see the datafeed plan, "`mode` follows the data plan".
    return {"type": "cn", "sessionid": session_id}


def subscribe_frame(kind: str, feed_keys: Sequence[str], channel_num: int) -> dict:
    return {"type": f"{TYPE_PREFIX[kind]}s", "scrips": "&".join(feed_keys), "channelnum": channel_num}


def unsubscribe_frame(kind: str, feed_keys: Sequence[str], channel_num: int) -> dict:
    return {"type": f"{TYPE_PREFIX[kind]}u", "scrips": "&".join(feed_keys), "channelnum": channel_num}


def snapshot_frame(kind: str, feed_keys: Sequence[str], channel_num: int) -> dict:
    return {"type": f"{TYPE_PREFIX[kind]}sp", "scrips": "&".join(feed_keys), "channelnum": channel_num}


def chunk(items: Sequence[Any], size: int) -> Iterator[Sequence[Any]]:
    """Splits ``items`` into chunks of at most ``size`` — used to honour
    ``maxScripPerReq`` when a subscription is larger than one request may
    carry (datafeed plan, "There are two limits, not one")."""
    if size <= 0:
        yield items
        return
    for start in range(0, len(items), size):
        yield items[start:start + size]


# --------------------------------------------------------------------------
# Message classification
# --------------------------------------------------------------------------


def classify_message(raw: Any) -> dict:
    """Classifies one decoded JSON message from the socket.

    - ``{"kind": "auth_ack", "ok", "st_code", "msg", "max_scrip_per_conn",
      "max_scrip_per_req"}`` — the response to the ``cn`` auth frame, a bare
      object (datafeed plan, Phase 0 "Settled").
    - ``{"kind": "sub_ack", "items": [...]}`` — the response to a
      subscribe/unsubscribe frame, an array of ``{"stat", "type", ...}``.
    - ``{"kind": "ticks", "items": [...]}`` — a delta tick frame, an array of
      per-instrument objects.
    - ``{"kind": "unknown", "raw": raw}`` — anything else, never raised on;
      the caller logs and moves on rather than crashing the socket loop over
      a frame shape it does not recognise.
    """
    if isinstance(raw, dict) and raw.get("type") == "cn":
        return {
            "kind": "auth_ack",
            "ok": raw.get("stat") == "Ok",
            "st_code": raw.get("stCode"),
            "msg": raw.get("msg"),
            "max_scrip_per_conn": raw.get("maxScripPerConn"),
            "max_scrip_per_req": raw.get("maxScripPerReq"),
        }

    if isinstance(raw, list):
        items = [item for item in raw if isinstance(item, dict)]
        if items and all(item.get("type") in ("sub", "unsub") and "stat" in item for item in items):
            return {"kind": "sub_ack", "items": items}
        return {"kind": "ticks", "items": items}

    return {"kind": "unknown", "raw": raw}


def auth_ack_error(classified: dict):
    """Builds the typed error for a ``"kind": "auth_ack", "ok": False``
    classification. Returns ``None`` when ``ok`` is true."""
    if classified["ok"]:
        return None
    return auth_error_from_ack(classified.get("st_code"), classified.get("msg"))


# --------------------------------------------------------------------------
# Per-instrument merge state and tick application
# --------------------------------------------------------------------------


@dataclass
class InstrumentState:
    """Mutable per-instrument merge state. One instance per (route tag,
    feed segment, feed identifier) — see client.py's subscription registry.
    Ticks are deltas, so every field here is "last known good", overwritten
    only when a new tick actually carries that field."""

    scrip_key: str
    quote_fields: Dict[str, Any] = field(default_factory=dict)
    quote_extra: Dict[str, Any] = field(default_factory=dict)
    top_of_book: Dict[str, Any] = field(default_factory=dict)
    depth_fields: Dict[str, Any] = field(default_factory=dict)
    depth_extra: Dict[str, Any] = field(default_factory=dict)
    index_fields: Dict[str, Any] = field(default_factory=dict)
    index_extra: Dict[str, Any] = field(default_factory=dict)


def apply_quote_tick(state: InstrumentState, tick: Dict[str, Any]) -> Tuple[Optional[Quote], Optional[Depth]]:
    """One ``sf`` tick item. A FULL-mode market-watch tick carries quote
    fields and top-of-book fields together; they are merged into separate
    state and emitted as two independent, independently-triggered events —
    a tick that only moves ``ltp`` yields a quote event and no depth event
    at all (datafeed plan, "One frame, two events")."""
    quote_changed = set()
    for wire_key, raw_value in tick.items():
        if wire_key in _META_KEYS or wire_key in TOP_OF_BOOK_WIRE_KEYS:
            continue
        mapped = QUOTE_FIELDS.get(wire_key)
        if mapped is None:
            state.quote_extra[wire_key] = raw_value
            continue
        name, parser = mapped
        state.quote_fields[name] = parser(raw_value)
        quote_changed.add(name)

    top_changed = set()
    for wire_key in (
        TOP_OF_BOOK_BID_PRICE_KEY, TOP_OF_BOOK_BID_QTY_KEY, TOP_OF_BOOK_ASK_PRICE_KEY, TOP_OF_BOOK_ASK_QTY_KEY,
    ):
        if wire_key in tick:
            state.top_of_book[wire_key] = tick[wire_key]
            top_changed.add(wire_key)

    quote_event = None
    if quote_changed:
        quote_event = Quote(
            scrip_key=state.scrip_key, changed_fields=frozenset(quote_changed),
            extra=dict(state.quote_extra), **state.quote_fields,
        )

    depth_event = None
    if top_changed:
        bid_price = parse_decimal(state.top_of_book.get(TOP_OF_BOOK_BID_PRICE_KEY))
        bid_qty = parse_int(state.top_of_book.get(TOP_OF_BOOK_BID_QTY_KEY))
        ask_price = parse_decimal(state.top_of_book.get(TOP_OF_BOOK_ASK_PRICE_KEY))
        ask_qty = parse_int(state.top_of_book.get(TOP_OF_BOOK_ASK_QTY_KEY))
        depth_event = Depth(
            scrip_key=state.scrip_key, level_count=1, source="quote",
            bids=[DepthLevel(price=bid_price, quantity=bid_qty, orders=None)],
            asks=[DepthLevel(price=ask_price, quantity=ask_qty, orders=None)],
            changed_fields=frozenset(top_changed),
        )

    return quote_event, depth_event


def apply_depth_tick(state: InstrumentState, tick: Dict[str, Any]) -> Optional[Depth]:
    """One ``dp`` tick item: five bid/ask levels. Level *n* pairs the price
    at ``bp``/``bp{n-1}`` with the order count at ``bno{n}`` — the two
    numbering bases the datafeed plan warns about getting wrong."""
    changed = set()
    for wire_key, raw_value in tick.items():
        if wire_key in _META_KEYS:
            continue
        parser = DEPTH_KEY_PARSERS.get(wire_key)
        if parser is None:
            state.depth_extra[wire_key] = raw_value
            continue
        state.depth_fields[wire_key] = parser(raw_value)
        changed.add(wire_key)

    if not changed:
        return None

    def levels(price_keys, qty_keys, order_keys) -> List[DepthLevel]:
        return [
            DepthLevel(
                price=state.depth_fields.get(p), quantity=state.depth_fields.get(q),
                orders=state.depth_fields.get(o),
            )
            for p, q, o in zip(price_keys, qty_keys, order_keys)
        ]

    return Depth(
        scrip_key=state.scrip_key, level_count=5, source="depth",
        bids=levels(DEPTH_BID_PRICE_KEYS, DEPTH_BID_QTY_KEYS, DEPTH_BID_ORDER_KEYS),
        asks=levels(DEPTH_ASK_PRICE_KEYS, DEPTH_ASK_QTY_KEYS, DEPTH_ASK_ORDER_KEYS),
        extra=dict(state.depth_extra), changed_fields=frozenset(changed),
    )


def apply_index_tick(state: InstrumentState, tick: Dict[str, Any]) -> Optional[IndexTick]:
    """One ``if`` tick item."""
    changed = set()
    for wire_key, raw_value in tick.items():
        if wire_key in _META_KEYS:
            continue
        mapped = INDEX_FIELDS.get(wire_key)
        if mapped is None:
            state.index_extra[wire_key] = raw_value
            continue
        name, parser = mapped
        state.index_fields[name] = parser(raw_value)
        changed.add(name)

    if not changed:
        return None

    return IndexTick(
        scrip_key=state.scrip_key, changed_fields=frozenset(changed),
        extra=dict(state.index_extra), **state.index_fields,
    )
