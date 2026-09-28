# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from high_openapi.client import HighClient

from .server import send_json, start_server


def sync_client(server):
    return HighClient(base_url=server.base_url, access_token="tok")


def ok(data):
    return {"requestId": "r", "data": data}


class TestScripsResource:
    def test_quotes_returns_a_map_keyed_by_trading_symbol_not_a_list(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "RELIANCE-EQ": {"scrip": "NSE@2885", "LTP": 1412.3, "prevClose": 1405.8, "change": 6.5, "changePer": 0.46},
        })))
        try:
            with sync_client(s) as high:
                quotes = high.scrips.quotes({"symbols": ["RELIANCE-EQ"]})
            assert isinstance(quotes, dict)
            assert quotes["RELIANCE-EQ"].LTP == 1412.3
            assert s.requests[0].url == "/v1/scrips/quotes"
        finally:
            s.close()

    def test_ohlc_returns_the_same_map_shape_with_an_ohlcv_block(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "RELIANCE-EQ": {
                "scrip": "NSE@2885", "LTP": 1412.3, "prevClose": 1405.8, "change": 6.5, "changePer": 0.46,
                "ohlcv": {"open": 1407, "high": 1418.6, "low": 1403.2, "close": 1412.3, "volume": 6843210},
            },
        })))
        try:
            with sync_client(s) as high:
                ohlc = high.scrips.ohlc({"symbols": ["RELIANCE-EQ"]})
            assert ohlc["RELIANCE-EQ"].ohlcv.volume == 6843210
        finally:
            s.close()

    def test_depth_encodes_the_symbol_into_the_path(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "tradingSymbol": "M&M-EQ", "bids": [], "asks": [],
            "totalBidQuantity": 0, "totalAskQuantity": 0, "totalAskPercentage": 0, "totalBidsPercentage": 0,
        })))
        try:
            with sync_client(s) as high:
                high.scrips.depth("M&M-EQ")
            assert s.requests[0].url == "/v1/scrips/M%26M-EQ/depth"
        finally:
            s.close()

    def test_expiries_returns_a_list_and_encodes_both_parameters(self):
        s = start_server(lambda h, i: send_json(h, 200, ok([{"expiry": "2026-09-29", "type": "M"}])))
        try:
            with sync_client(s) as high:
                expiries = high.scrips.expiries("NIFTY 50", "options")
            assert len(expiries) == 1
            assert expiries[0].type.value == "M"
            assert s.requests[0].url == "/v1/scrips/NIFTY%2050/options/expiries"
        finally:
            s.close()

    def test_future_data_returns_a_list_of_scrips(self):
        s = start_server(lambda h, i: send_json(h, 200, ok([])))
        try:
            with sync_client(s) as high:
                futures = high.scrips.future_data("RELIANCE-EQ")
            assert futures == []
            assert s.requests[0].url == "/v1/scrips/RELIANCE-EQ/future-data"
        finally:
            s.close()

    def test_historical_returns_parallel_columns_of_equal_length(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "tradingSymbol": "NSE@2885", "interval": "1D",
            "timestamp": [1789929000, 1790015400], "open": [1398.5, 1402], "high": [1406.2, 1409.8],
            "low": [1394.1, 1399.3], "close": [1401.7, 1407.4], "volume": [7215430, 6532180],
        })))
        try:
            with sync_client(s) as high:
                candles = high.scrips.historical({
                    "tradingSymbol": "RELIANCE-EQ", "interval": "1D",
                    "fromTime": 1789929000, "toTime": 1790330400,
                })
            assert len(candles.timestamp) == 2
            assert len(candles.close) == len(candles.timestamp)
            assert isinstance(candles.open, list)
        finally:
            s.close()

    def test_option_chain_returns_rows_with_call_and_put_legs(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "baseStockInfo": {
                "tradingSymbol": "RELIANCE-EQ", "scripCode": 2885, "exchange": "NSE", "segment": "ES",
                "scripKey": "NSE@2885", "symbol": "RELIANCE", "scripName": "Reliance", "marketLot": 1, "priceTick": 10,
            },
            "optionChain": [{"strikePrice": 1400, "call": {}, "put": {}}],
            "marketLot": 500, "maxOrderLots": 36,
        })))
        try:
            with sync_client(s) as high:
                chain = high.scrips.option_chain({"tradingSymbol": "RELIANCE-EQ", "expiry": "2026-09-29"})
            assert chain.optionChain[0].strikePrice == 1400
        finally:
            s.close()

    def test_quotes_is_a_post_so_it_is_never_retried(self):
        s = start_server(lambda h, i: send_json(h, 503, {"code": "SERVICE_UNAVAILABLE"}))
        try:
            with sync_client(s) as high:
                try:
                    high.scrips.quotes({"symbols": ["RELIANCE-EQ"]})
                    raise AssertionError("expected an error")
                except Exception:
                    pass
            assert len(s.requests) == 1
        finally:
            s.close()
