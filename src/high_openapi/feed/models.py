# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Typed tick models and the wire-to-model field maps (datafeed plan,
"Field names").

Every model carries the caller's own ``scrip_key`` (never the feed's ``e``/
``tk``), and ``changed_fields`` — the set of *this model's own* snake_case
field names that arrived in the tick that produced it, since ticks are
deltas and a caller who wants to know what just moved needs that separately
from the merged, always-complete snapshot. Unknown wire fields are preserved
in ``extra`` rather than dropped, so a vendor addition still reaches a
caller instead of vanishing silently.

Prices are ``Decimal`` — the wire sends them as already-scaled decimal
strings, and parsing them to a binary ``float`` would be a silent precision
bug for anyone downstream doing arithmetic on money. Quantities are ``int``.
Timestamps are parsed with the field's own explicit format (they differ
between fields) after trimming leading whitespace — a raw value like
``" 9408.60"`` or an untrimmed timestamp is a real example from the vendor
material, not a hypothetical.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Dict, FrozenSet, List, Literal, Optional

from pydantic import BaseModel, ConfigDict

# --------------------------------------------------------------------------
# Parsing helpers. Every wire value arrives as a string (or is absent); None
# in, None out, and a malformed value never crashes the socket loop.
# --------------------------------------------------------------------------


def parse_decimal(raw: Any) -> Optional[Decimal]:
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "":
        return None
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_int(raw: Any) -> Optional[int]:
    if raw is None:
        return None
    text = str(raw).strip()
    if text == "":
        return None
    try:
        return int(Decimal(text))
    except InvalidOperation:
        return None


def parse_str(raw: Any) -> Optional[str]:
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def make_timestamp_parser(fmt: str):
    """Returns a parser bound to one explicit ``strptime`` format — the three
    feed timestamps (``ltt``, ``fdtm``, ``tvalue``) use three different
    formats and none carries a timezone; they are IST wall-clock values,
    parsed as naive ``datetime`` rather than mislabelled as UTC."""

    def _parse(raw: Any) -> Optional[datetime]:
        if raw is None:
            return None
        text = str(raw).strip()
        if text == "":
            return None
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            return None

    return _parse


parse_ltt = make_timestamp_parser("%d/%m/%Y %H:%M:%S")
parse_fdtm = make_timestamp_parser("%d-%b-%Y %H:%M:%S")
parse_tvalue = make_timestamp_parser("%d-%b-%Y %H:%M:%S")


# --------------------------------------------------------------------------
# Quote (market watch, frame `sf`)
# --------------------------------------------------------------------------

# wire key -> (our field name, parser). `e`/`tk` are the join key, used
# internally to route a tick back to the caller's scrip_key, and never
# reach the model. `ts` here is the trading symbol, per the field table.
QUOTE_FIELDS: Dict[str, tuple] = {
    "ts": ("trading_symbol", parse_str),
    "ltp": ("last_traded_price", parse_decimal),
    "ltq": ("last_traded_quantity", parse_int),
    "ltt": ("last_traded_time", parse_ltt),
    "v": ("volume", parse_int),
    "to": ("turnover", parse_decimal),
    "ap": ("average_trade_price", parse_decimal),
    "op": ("open", parse_decimal),
    "h": ("high", parse_decimal),
    "lo": ("low", parse_decimal),
    "c": ("previous_close", parse_decimal),
    "yh": ("year_high", parse_decimal),
    "yl": ("year_low", parse_decimal),
    # cng/nc are swapped relative to the vendor's own sample README — the
    # apiDoc's worked example (ltp 1905.65, c 1859.05) settles it: cng is the
    # absolute difference (46.60), nc is that as a percentage (2.51). See
    # test_models.py::test_pins_the_cng_nc_arithmetic_against_the_apidoc_example.
    "cng": ("change", parse_decimal),
    "nc": ("change_percent", parse_decimal),
    "tbq": ("total_buy_quantity", parse_int),
    "tsq": ("total_sell_quantity", parse_int),
    "oi": ("open_interest", parse_int),
    "lcl": ("lower_circuit_limit", parse_decimal),
    "ucl": ("upper_circuit_limit", parse_decimal),
    "fdtm": ("feed_time", parse_fdtm),
    "mul": ("multiplier", parse_decimal),
    "prec": ("precision", parse_int),
}

# Top-of-book fields carried on the *same* `sf` tick as the quote fields
# above, in FULL mode. Split into their own event — see models.Depth. The
# vendor's own naming: bid price/qty are `bp`/`bq`; ask price is `sp` (sell
# price), but ask *quantity* is `bs`, not `sq` — the same odd pairing the
# five-level `dp` feed uses (see DEPTH_ASK_QTY_KEYS below).
TOP_OF_BOOK_BID_PRICE_KEY = "bp"
TOP_OF_BOOK_BID_QTY_KEY = "bq"
TOP_OF_BOOK_ASK_PRICE_KEY = "sp"
TOP_OF_BOOK_ASK_QTY_KEY = "bs"

QUOTE_WIRE_KEYS = frozenset(QUOTE_FIELDS)
TOP_OF_BOOK_WIRE_KEYS = frozenset(
    {TOP_OF_BOOK_BID_PRICE_KEY, TOP_OF_BOOK_BID_QTY_KEY, TOP_OF_BOOK_ASK_PRICE_KEY, TOP_OF_BOOK_ASK_QTY_KEY}
)

# --------------------------------------------------------------------------
# Depth (frame `dp`) — five levels, built from two different numbering bases
# --------------------------------------------------------------------------

# Bid side: price/qty are unnumbered at level 1, then bp1..bp4/bq1..bq4 for
# levels 2-5. Order counts are bno1..bno5 for ALL five levels, including the
# first — so level n pairs price key f(n) with order-count key `bno{n}`,
# never `bno{n-1}`. Getting this off by one silently attributes every
# level's order count to the wrong price (see the plan's own warning).
DEPTH_BID_PRICE_KEYS = ["bp", "bp1", "bp2", "bp3", "bp4"]
DEPTH_BID_QTY_KEYS = ["bq", "bq1", "bq2", "bq3", "bq4"]
DEPTH_BID_ORDER_KEYS = ["bno1", "bno2", "bno3", "bno4", "bno5"]

# Ask side: same shape, using the vendor's sp/bs/sno triad (bs = ask
# quantity — see TOP_OF_BOOK_FIELDS above).
DEPTH_ASK_PRICE_KEYS = ["sp", "sp1", "sp2", "sp3", "sp4"]
DEPTH_ASK_QTY_KEYS = ["bs", "bs1", "bs2", "bs3", "bs4"]
DEPTH_ASK_ORDER_KEYS = ["sno1", "sno2", "sno3", "sno4", "sno5"]

DEPTH_WIRE_KEYS = frozenset(
    DEPTH_BID_PRICE_KEYS + DEPTH_BID_QTY_KEYS + DEPTH_BID_ORDER_KEYS
    + DEPTH_ASK_PRICE_KEYS + DEPTH_ASK_QTY_KEYS + DEPTH_ASK_ORDER_KEYS
)

# wire key -> parser, for every depth key above — prices are Decimal,
# quantities and order counts are int.
DEPTH_KEY_PARSERS: Dict[str, Any] = {}
for _key in DEPTH_BID_PRICE_KEYS + DEPTH_ASK_PRICE_KEYS:
    DEPTH_KEY_PARSERS[_key] = parse_decimal
for _key in DEPTH_BID_QTY_KEYS + DEPTH_ASK_QTY_KEYS + DEPTH_BID_ORDER_KEYS + DEPTH_ASK_ORDER_KEYS:
    DEPTH_KEY_PARSERS[_key] = parse_int
del _key

# --------------------------------------------------------------------------
# Index (frame `if`)
# --------------------------------------------------------------------------

INDEX_FIELDS: Dict[str, tuple] = {
    "ts": ("index_name", parse_str),
    "iv": ("index_value", parse_decimal),
    "ic": ("previous_close", parse_decimal),
    "openingprice": ("open", parse_decimal),
    "highprice": ("high", parse_decimal),
    "lowprice": ("low", parse_decimal),
    "cng": ("change", parse_decimal),
    "nc": ("change_percent", parse_decimal),
    "tvalue": ("feed_time", parse_tvalue),
}

INDEX_WIRE_KEYS = frozenset(INDEX_FIELDS)


# --------------------------------------------------------------------------
# Public models
# --------------------------------------------------------------------------


class Quote(BaseModel):
    """A complete market-watch snapshot, merged from every delta tick seen so
    far for this instrument — never a partial tick. ``extra`` preserves any
    wire field this SDK does not (yet) name."""

    model_config = ConfigDict(frozen=True)

    scrip_key: str
    trading_symbol: Optional[str] = None
    last_traded_price: Optional[Decimal] = None
    last_traded_quantity: Optional[int] = None
    last_traded_time: Optional[datetime] = None
    volume: Optional[int] = None
    turnover: Optional[Decimal] = None
    average_trade_price: Optional[Decimal] = None
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    previous_close: Optional[Decimal] = None
    year_high: Optional[Decimal] = None
    year_low: Optional[Decimal] = None
    change: Optional[Decimal] = None
    change_percent: Optional[Decimal] = None
    total_buy_quantity: Optional[int] = None
    total_sell_quantity: Optional[int] = None
    open_interest: Optional[int] = None
    lower_circuit_limit: Optional[Decimal] = None
    upper_circuit_limit: Optional[Decimal] = None
    feed_time: Optional[datetime] = None
    multiplier: Optional[Decimal] = None
    precision: Optional[int] = None
    extra: Dict[str, Any] = {}
    changed_fields: FrozenSet[str] = frozenset()


class DepthLevel(BaseModel):
    model_config = ConfigDict(frozen=True)

    price: Optional[Decimal] = None
    quantity: Optional[int] = None
    orders: Optional[int] = None


class Depth(BaseModel):
    """A book snapshot, either one level (top-of-book, split out of a FULL
    market-watch tick) or five (the dedicated ``dp`` feed). ``level_count``
    states which, so a caller can never mistake a one-level book for a
    five-level one with four empty rows — see the datafeed plan's warning
    that doing so reads as a suddenly-illiquid instrument."""

    model_config = ConfigDict(frozen=True)

    scrip_key: str
    level_count: Literal[1, 5]
    source: Literal["quote", "depth"]
    bids: List[DepthLevel]
    asks: List[DepthLevel]
    extra: Dict[str, Any] = {}
    changed_fields: FrozenSet[str] = frozenset()


class IndexTick(BaseModel):
    model_config = ConfigDict(frozen=True)

    scrip_key: str
    index_name: Optional[str] = None
    index_value: Optional[Decimal] = None
    previous_close: Optional[Decimal] = None
    open: Optional[Decimal] = None
    high: Optional[Decimal] = None
    low: Optional[Decimal] = None
    change: Optional[Decimal] = None
    change_percent: Optional[Decimal] = None
    feed_time: Optional[datetime] = None
    extra: Dict[str, Any] = {}
    changed_fields: FrozenSet[str] = frozenset()
