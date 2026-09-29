# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Field parsing and the delta-merge engine — pure, no socket involved.

Covers: the cng/nc arithmetic pin (the vendor's own sample README has them
backwards — the apiDoc's worked example settles it), Decimal-not-float
prices, per-field timestamp formats with leading-space trimming, unknown
fields preserved, the quote/top-of-book split raising independently, and the
depth level-numbering pairing (bp/bp1..bp4 against bno1..bno5 — two
different bases).
"""

from datetime import datetime
from decimal import Decimal

from high_openapi.feed._protocol import InstrumentState, apply_depth_tick, apply_index_tick, apply_quote_tick
from high_openapi.feed.models import parse_decimal, parse_fdtm, parse_ltt, parse_tvalue


class TestCngNcArithmeticPin:
    """apiDoc worked example: ltp 1905.65, c (previous close) 1859.05.
    cng (46.60) is the absolute difference; nc (2.51) is that as a
    percentage — the OPPOSITE of what the vendor's own React sample README
    claims. Getting this backwards is silent: both are just numbers."""

    def test_cng_is_the_absolute_change_not_the_percentage(self):
        state = InstrumentState(scrip_key="NSE@2885")
        quote, _ = apply_quote_tick(state, {"ltp": "1905.65", "c": "1859.05", "cng": "46.60", "nc": "2.51"})
        assert quote.change == Decimal("46.60")
        assert quote.change_percent == Decimal("2.51")
        # And the arithmetic itself holds, pinning the assignment isn't
        # accidental: 46.60 / 1859.05 * 100 rounds to 2.51.
        assert round(quote.change / quote.previous_close * 100, 2) == Decimal("2.51")


class TestDecimalNotFloat:
    def test_prices_parse_to_decimal(self):
        state = InstrumentState(scrip_key="NSE@2885")
        quote, _ = apply_quote_tick(state, {"ltp": "1905.65"})
        assert quote.last_traded_price == Decimal("1905.65")
        assert isinstance(quote.last_traded_price, Decimal)
        assert not isinstance(quote.last_traded_price, float)

    def test_a_leading_space_is_trimmed_before_parsing(self):
        # The vendor's own index sample shows "openingprice": " 9408.60".
        assert parse_decimal(" 9408.60") == Decimal("9408.60")


class TestTimestampsEachWithTheirOwnFormat:
    def test_ltt_format(self):
        assert parse_ltt("29/04/2020 15:59:44") == datetime(2020, 4, 29, 15, 59, 44)

    def test_fdtm_format(self):
        assert parse_fdtm("29-Apr-2020 17:34:36") == datetime(2020, 4, 29, 17, 34, 36)

    def test_tvalue_format(self):
        assert parse_tvalue("29-Apr-2020 14:34:36") == datetime(2020, 4, 29, 14, 34, 36)

    def test_leading_space_trimmed_on_a_timestamp_too(self):
        assert parse_ltt(" 29/04/2020 15:59:44") == datetime(2020, 4, 29, 15, 59, 44)

    def test_feed_time_and_last_traded_time_land_on_the_quote_model(self):
        state = InstrumentState(scrip_key="NSE@2885")
        quote, _ = apply_quote_tick(state, {"ltt": "29/04/2020 15:59:44", "fdtm": "29-Apr-2020 17:34:36"})
        assert quote.last_traded_time == datetime(2020, 4, 29, 15, 59, 44)
        assert quote.feed_time == datetime(2020, 4, 29, 17, 34, 36)


class TestUnknownFieldsPreserved:
    def test_a_wire_field_this_sdk_does_not_name_reaches_extra(self):
        state = InstrumentState(scrip_key="NSE@2885")
        quote, _ = apply_quote_tick(state, {"ltp": "100.00", "eqt": "42"})
        assert quote.extra == {"eqt": "42"}

    def test_extra_accumulates_and_survives_later_ticks_that_dont_repeat_it(self):
        state = InstrumentState(scrip_key="NSE@2885")
        apply_quote_tick(state, {"ltp": "100.00", "emqt": "7"})
        quote, _ = apply_quote_tick(state, {"ltp": "101.00"})
        assert quote.extra == {"emqt": "7"}
        assert quote.last_traded_price == Decimal("101.00")


class TestDeltaMergeAcrossTicks:
    def test_a_field_not_repeated_in_a_later_tick_keeps_its_last_value(self):
        state = InstrumentState(scrip_key="NSE@2885")
        apply_quote_tick(state, {"ltp": "100.00", "op": "99.00", "h": "101.00"})
        quote, _ = apply_quote_tick(state, {"ltp": "100.50"})
        assert quote.last_traded_price == Decimal("100.50")
        assert quote.open == Decimal("99.00")  # from the first tick, unchanged
        assert quote.high == Decimal("101.00")  # likewise

    def test_changed_fields_reflects_only_the_latest_tick(self):
        state = InstrumentState(scrip_key="NSE@2885")
        apply_quote_tick(state, {"ltp": "100.00", "op": "99.00"})
        quote, _ = apply_quote_tick(state, {"ltp": "100.50"})
        assert quote.changed_fields == frozenset({"last_traded_price"})

    def test_a_tick_that_carries_no_quote_fields_raises_no_quote_event(self):
        state = InstrumentState(scrip_key="NSE@2885")
        quote, depth = apply_quote_tick(state, {"bp": "100.00", "bq": "10"})
        assert quote is None
        assert depth is not None


class TestQuoteAndTopOfBookSplitIndependently:
    def test_a_tick_moving_only_ltp_raises_a_quote_event_and_no_depth_event(self):
        state = InstrumentState(scrip_key="NSE@2885")
        quote, depth = apply_quote_tick(state, {"ltp": "100.50"})
        assert quote is not None
        assert depth is None

    def test_a_full_tick_with_both_raises_two_events(self):
        state = InstrumentState(scrip_key="NSE@2885")
        quote, depth = apply_quote_tick(
            state, {"ltp": "100.50", "op": "99.00", "bp": "100.40", "bq": "10", "sp": "100.60", "bs": "20"},
        )
        assert quote is not None
        assert quote.last_traded_price == Decimal("100.50")
        assert depth is not None
        assert depth.level_count == 1
        assert depth.source == "quote"
        assert len(depth.bids) == 1 and len(depth.asks) == 1
        assert depth.bids[0].price == Decimal("100.40")
        assert depth.bids[0].quantity == 10
        assert depth.asks[0].price == Decimal("100.60")
        assert depth.asks[0].quantity == 20
        # A one-level book must never look like a five-level one.
        assert depth.bids[0].orders is None

    def test_top_of_book_state_also_merges_across_ticks(self):
        state = InstrumentState(scrip_key="NSE@2885")
        apply_quote_tick(state, {"bp": "100.00", "bq": "5", "sp": "100.20", "bs": "8"})
        _, depth = apply_quote_tick(state, {"bp": "100.10"})
        assert depth.bids[0].price == Decimal("100.10")
        assert depth.bids[0].quantity == 5  # kept from the first tick
        assert depth.asks[0].price == Decimal("100.20")  # kept too
        assert depth.changed_fields == frozenset({"bp"})


class TestDepthLevelNumberingPairing:
    """bp/bp1..bp4 (price) and bq/bq1..bq4 (qty) are unnumbered at level 1;
    bno1..bno5 (order count) is numbered from 1 for every level. Level n
    must pair the level-n price with bno{n}, not bno{n-1}."""

    def _tick(self):
        tick = {}
        for i, price in enumerate([10.1, 10.2, 10.3, 10.4, 10.5]):
            key = "bp" if i == 0 else f"bp{i}"
            tick[key] = str(price)
        for i, qty in enumerate([1, 2, 3, 4, 5]):
            key = "bq" if i == 0 else f"bq{i}"
            tick[key] = str(qty * 10)
        for i in range(5):
            tick[f"bno{i + 1}"] = str(100 + i)
        for i, price in enumerate([20.1, 20.2, 20.3, 20.4, 20.5]):
            key = "sp" if i == 0 else f"sp{i}"
            tick[key] = str(price)
        for i, qty in enumerate([6, 7, 8, 9, 10]):
            key = "bs" if i == 0 else f"bs{i}"
            tick[key] = str(qty * 10)
        for i in range(5):
            tick[f"sno{i + 1}"] = str(200 + i)
        return tick

    def test_level_1_pairs_bp_with_bno1(self):
        state = InstrumentState(scrip_key="NSE@2885")
        depth = apply_depth_tick(state, self._tick())
        assert depth.level_count == 5
        assert depth.source == "depth"
        assert depth.bids[0].price == Decimal("10.1")
        assert depth.bids[0].quantity == 10
        assert depth.bids[0].orders == 100

    def test_level_5_pairs_bp4_with_bno5(self):
        state = InstrumentState(scrip_key="NSE@2885")
        depth = apply_depth_tick(state, self._tick())
        assert depth.bids[4].price == Decimal("10.5")
        assert depth.bids[4].quantity == 50
        assert depth.bids[4].orders == 104

    def test_every_bid_level_pairs_its_own_price_with_its_own_order_count(self):
        state = InstrumentState(scrip_key="NSE@2885")
        depth = apply_depth_tick(state, self._tick())
        expected_prices = [Decimal(str(x)) for x in [10.1, 10.2, 10.3, 10.4, 10.5]]
        expected_orders = [100, 101, 102, 103, 104]
        assert [level.price for level in depth.bids] == expected_prices
        assert [level.orders for level in depth.bids] == expected_orders

    def test_ask_side_uses_sp_bs_sno_the_same_way(self):
        state = InstrumentState(scrip_key="NSE@2885")
        depth = apply_depth_tick(state, self._tick())
        assert depth.asks[0].price == Decimal("20.1")
        assert depth.asks[0].quantity == 60  # "bs" is the ask quantity field, despite the "b"
        assert depth.asks[0].orders == 200
        assert depth.asks[4].price == Decimal("20.5")
        assert depth.asks[4].orders == 204

    def test_a_depth_tick_never_produces_a_one_level_book(self):
        state = InstrumentState(scrip_key="NSE@2885")
        depth = apply_depth_tick(state, self._tick())
        assert len(depth.bids) == 5
        assert len(depth.asks) == 5


class TestIndexTick:
    def test_maps_index_fields_and_feed_time_uses_tvalue(self):
        state = InstrumentState(scrip_key="NSE@26000")
        index = apply_index_tick(state, {
            "ts": "Nifty 50", "iv": "19500.25", "ic": "19400.10",
            "openingprice": " 19420.00", "highprice": "19510.00", "lowprice": "19410.00",
            "cng": "100.15", "nc": "0.52", "tvalue": "29-Apr-2020 14:34:36",
        })
        assert index.index_name == "Nifty 50"
        assert index.index_value == Decimal("19500.25")
        assert index.previous_close == Decimal("19400.10")
        assert index.open == Decimal("19420.00")
        assert index.high == Decimal("19510.00")
        assert index.low == Decimal("19410.00")
        assert index.change == Decimal("100.15")
        assert index.change_percent == Decimal("0.52")
        assert index.feed_time == datetime(2020, 4, 29, 14, 34, 36)

    def test_a_tick_with_no_recognised_field_raises_no_event(self):
        state = InstrumentState(scrip_key="NSE@26000")
        assert apply_index_tick(state, {"t": "if", "e": "nse_cm", "tk": "Nifty 50"}) is None
