# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Key translation (datafeed plan, Phase 1) — pure, no socket involved.

Covers: the index table running first, the prefix rule for every supported
segment, MCX spot's explicit non-support, an unknown prefix, and the
two-way rejection the coordinator's surface change asked for — an index key
must not reach the quote/depth prefix rule (it would silently produce a
token the feed does not know), and a non-index key must not reach
``subscribe_indices``.
"""

import pytest

from high_openapi.feed.errors import HighFeedKeyError
from high_openapi.feed.translate import is_index_key, translate_index, translate_instrument


class TestNonIndexPrefixRule:
    def test_nse_cash(self):
        assert translate_instrument("NSE@15563") == ("nse_cm", "15563")

    def test_bse_cash(self):
        assert translate_instrument("BSE@532540") == ("bse_cm", "532540")

    def test_nse_derivatives(self):
        assert translate_instrument("NSEFO@52190") == ("nse_fo", "52190")

    def test_bse_derivatives(self):
        assert translate_instrument("BSEFO@842150") == ("bse_fo", "842150")

    def test_mcx_derivatives(self):
        assert translate_instrument("MCXFO@227915") == ("mcx_fo", "227915")


class TestUnsupportedAndUnknownSegments:
    def test_mcx_spot_has_no_feed_code_and_is_rejected_by_name(self):
        with pytest.raises(HighFeedKeyError, match="MCX@227915"):
            translate_instrument("MCX@227915")

    def test_an_unknown_prefix_is_rejected_naming_the_key(self):
        with pytest.raises(HighFeedKeyError, match="XSE@123"):
            translate_instrument("XSE@123")

    def test_a_malformed_key_with_no_at_sign_is_rejected(self):
        with pytest.raises(HighFeedKeyError, match="RELIANCE-EQ"):
            translate_instrument("RELIANCE-EQ")


class TestIndexTable:
    def test_a_known_index_resolves_by_name_not_token(self):
        assert translate_index("NSE@26000") == ("nse_cm", "Nifty 50")

    def test_another_known_index(self):
        assert translate_index("BSE@19000") == ("bse_cm", "SENSEX")

    def test_an_index_row_the_feed_does_not_carry_is_rejected(self):
        # NSE@26016 (HANGSENG BEES-NAV) is one of the four upstream rows
        # deliberately absent from the committed table.
        with pytest.raises(HighFeedKeyError, match="NSE@26016"):
            translate_index("NSE@26016")

    def test_a_non_index_key_is_rejected_by_the_index_lookup(self):
        with pytest.raises(HighFeedKeyError, match="NSE@2885"):
            translate_index("NSE@2885")

    def test_is_index_key_helper(self):
        assert is_index_key("NSE@26000") is True
        assert is_index_key("NSE@2885") is False


class TestTwoWayRejectionBetweenInstrumentAndIndexMethods:
    """The surface change: subscribe_quotes/subscribe_depth must never fall
    through to the prefix rule for a key that is actually an index — that
    would silently produce e.g. nse_cm|26000 (a token the feed does not
    know) and the subscription would just never tick."""

    def test_an_index_key_is_rejected_by_translate_instrument_naming_the_key(self):
        with pytest.raises(HighFeedKeyError, match="NSE@26000") as exc_info:
            translate_instrument("NSE@26000")
        assert "index" in str(exc_info.value).lower()
        assert "subscribe_indices" in str(exc_info.value)

    def test_a_non_index_key_is_rejected_by_translate_index_naming_the_key(self):
        with pytest.raises(HighFeedKeyError, match="NSE@2885"):
            translate_index("NSE@2885")

    def test_the_key_is_available_on_the_raised_error(self):
        try:
            translate_instrument("NSE@26000")
            assert False, "expected HighFeedKeyError"
        except HighFeedKeyError as exc:
            assert exc.key == "NSE@26000"
