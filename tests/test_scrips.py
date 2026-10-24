# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import json

import pytest
from pydantic import ValidationError

from high_openapi.client import AsyncHighClient, HighClient
from high_openapi.errors import HighApiError

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


CANDLES = {
    "tradingSymbol": "NSE@2885", "interval": "5m",
    "timestamp": [1789929000, 1789929300], "open": [1398.5, 1402], "high": [1406.2, 1409.8],
    "low": [1394.1, 1399.3], "close": [1401.7, 1407.4], "volume": [7215430, 6532180],
}


class TestHistoricalInstrumentForms:
    def test_historical_accepts_exchange_segment_and_scrip_code_without_a_symbol(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(CANDLES)))
        try:
            with sync_client(s) as high:
                candles = high.scrips.historical({
                    "exchangeSegment": "NSE", "scripCode": "2885", "interval": "5m",
                    "fromTime": 1789929000, "toTime": 1789930000,
                })
            assert len(candles.close) == 2
            body = json.loads(s.requests[0].body)
            assert body["exchangeSegment"] == "NSE" and body["scripCode"] == "2885"
            assert "tradingSymbol" not in body
        finally:
            s.close()

    def test_historical_rejects_a_body_naming_no_instrument_before_sending(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(CANDLES)))
        try:
            with sync_client(s) as high:
                with pytest.raises(ValidationError):
                    high.scrips.historical({"exchangeSegment": "NSE", "interval": "1D",
                                            "fromTime": 1, "toTime": 2})
                with pytest.raises(ValidationError):
                    high.scrips.historical({"scripCode": "2885", "interval": "1D",
                                            "fromTime": 1, "toTime": 2})
            assert s.requests == []
        finally:
            s.close()


class TestIntradayScrips:
    def test_intraday_posts_to_the_intraday_path_and_returns_columnar_candles(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(CANDLES)))
        try:
            with sync_client(s) as high:
                candles = high.scrips.intraday({"tradingSymbol": "RELIANCE-EQ", "interval": "5m"})
            assert s.requests[0].method == "POST"
            assert s.requests[0].url == "/v1/scrips/intraday"
            assert candles.timestamp == [1789929000, 1789929300]
            assert len(candles.open) == len(candles.timestamp)
        finally:
            s.close()

    def test_intraday_accepts_exchange_segment_and_scrip_code(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(CANDLES)))
        try:
            with sync_client(s) as high:
                high.scrips.intraday({"exchangeSegment": "NSE", "scripCode": "2885", "interval": "1h"})
            body = json.loads(s.requests[0].body)
            assert body == {"exchangeSegment": "NSE", "scripCode": "2885", "interval": "1h"}
        finally:
            s.close()

    def test_intraday_rejects_an_interval_the_spec_does_not_list(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(CANDLES)))
        try:
            with sync_client(s) as high:
                with pytest.raises(ValidationError):
                    high.scrips.intraday({"tradingSymbol": "RELIANCE-EQ", "interval": "1D"})
            assert s.requests == []
        finally:
            s.close()

    def test_intraday_rejects_a_body_naming_no_instrument_before_sending(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(CANDLES)))
        try:
            with sync_client(s) as high:
                with pytest.raises(ValidationError):
                    high.scrips.intraday({"interval": "5m"})
            assert s.requests == []
        finally:
            s.close()

    def test_intraday_is_a_post_so_it_is_never_retried(self):
        s = start_server(lambda h, i: send_json(h, 503, {"code": "SERVICE_UNAVAILABLE"}))
        try:
            with sync_client(s) as high:
                with pytest.raises(HighApiError):
                    high.scrips.intraday({"tradingSymbol": "RELIANCE-EQ", "interval": "5m"})
            assert len(s.requests) == 1
        finally:
            s.close()


class TestAsyncScrips:
    async def test_async_intraday_posts_and_returns_columnar_candles(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(CANDLES)))
        try:
            async with AsyncHighClient(base_url=s.base_url, access_token="tok") as high:
                candles = await high.scrips.intraday({"tradingSymbol": "RELIANCE-EQ", "interval": "5m"})
            assert s.requests[0].url == "/v1/scrips/intraday"
            assert len(candles.close) == 2
        finally:
            s.close()

    async def test_async_historical_accepts_exchange_segment_and_scrip_code(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(CANDLES)))
        try:
            async with AsyncHighClient(base_url=s.base_url, access_token="tok") as high:
                await high.scrips.historical({
                    "exchangeSegment": "NSE", "scripCode": "2885", "interval": "5m",
                    "fromTime": 1789929000, "toTime": 1789930000,
                })
            assert json.loads(s.requests[0].body)["scripCode"] == "2885"
        finally:
            s.close()

    async def test_async_intraday_rejects_a_body_naming_no_instrument_before_sending(self):
        s = start_server(lambda h, i: send_json(h, 200, ok(CANDLES)))
        try:
            async with AsyncHighClient(base_url=s.base_url, access_token="tok") as high:
                with pytest.raises(ValidationError):
                    await high.scrips.intraday({"interval": "5m"})
            assert s.requests == []
        finally:
            s.close()
