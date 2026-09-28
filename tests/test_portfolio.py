# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import json

from high_openapi.client import HighClient
from high_openapi.errors import HighApiError

from .server import send_json, start_server


def sync_client(server):
    return HighClient(base_url=server.base_url, access_token="tok")


def ok(data):
    return {"requestId": "r", "data": data}


class TestPortfolioResource:
    def test_positions_returns_the_account_snapshot_and_the_list(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "totalStocks": 1,
            "snapshot": {
                "bookedPL": 100, "unrealisedPL": 123, "totalPL": 223,
                "bookedPLPercent": 0.71, "unrealisedPLPercent": 0.88, "totalPLPercent": 0.8,
            },
            "positions": [], "scrips": {},
        })))
        try:
            with sync_client(s) as high:
                positions = high.portfolio.positions()
            assert positions.snapshot.totalPL == 223
            assert s.requests[0].url == "/v1/portfolio/positions"
        finally:
            s.close()

    def test_holdings_uses_the_investment_snapshot_not_the_pl_one(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "totalStocks": 1,
            "snapshot": {
                "investment": 13000, "currentValue": 14123, "previousDayValue": 14058,
                "totalPL": 1123, "dayPL": 65, "totalPLPercent": 8.64, "dayPLPercent": 0.46,
            },
            "holdings": [], "scrips": {},
        })))
        try:
            with sync_client(s) as high:
                holdings = high.portfolio.holdings()
            assert holdings.snapshot.investment == 13000
            assert s.requests[0].url == "/v1/portfolio/holdings"
        finally:
            s.close()

    def test_funds_returns_balances(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "availableBalance": 125000.5, "ledgerBalance": 150000, "todaysBalance": 155000.5,
            "marginUtilized": 30000, "marginAgainstAssets": 50000, "todaysPayIn": 10000, "todaysPayout": 5000,
            "mtfFunds": {"mtfCash": 0, "mtfFunded": 0, "totalMTFFunding": 0},
            "charges": {"delayedPaymentCharges": 0, "dpCharges": 0, "totalCharges": 0},
            "unsettledFutureAmount": 0,
        })))
        try:
            with sync_client(s) as high:
                funds = high.portfolio.funds()
            assert funds.availableBalance == 125000.5
        finally:
            s.close()

    def test_convert_position_patches_the_convert_endpoint(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "tradingSymbol": "RELIANCE-EQ", "exchangeSegment": "NSE", "scripCode": "2885",
            "quantity": 50, "isSubmitted": True,
        })))
        try:
            with sync_client(s) as high:
                high.portfolio.convert_position({
                    "tradingSymbol": "RELIANCE-EQ", "quantity": 50, "tradeSide": "B",
                    "sourceProductType": "INTRADAY", "targetProductType": "DELIVERY",
                })
            assert s.requests[0].method == "PATCH"
            assert s.requests[0].url == "/v1/portfolio/positions/convert"
        finally:
            s.close()

    def test_exit_all_positions_deletes_with_no_body(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "totalCount": 0, "successCount": 0, "failureCount": 0, "positions": [],
        })))
        try:
            with sync_client(s) as high:
                high.portfolio.exit_all_positions()
            assert s.requests[0].method == "DELETE"
            assert s.requests[0].url == "/v1/portfolio/positions/exit/all"
            assert s.requests[0].body == ""
        finally:
            s.close()

    def test_exit_position_deletes_with_a_body(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "tradingSymbol": "RELIANCE-EQ", "exchangeSegment": "NSE", "scripCode": "2885",
            "quantity": 50, "flavor": "REGULAR", "isSubmitted": True,
        })))
        try:
            with sync_client(s) as high:
                high.portfolio.exit_position({
                    "tradingSymbol": "RELIANCE-EQ", "productType": "INTRADAY", "flavor": "REGULAR",
                    "tradeSide": "S", "quantity": 50,
                })
            assert s.requests[0].method == "DELETE"
            assert s.requests[0].url == "/v1/portfolio/positions/exit"
            assert json.loads(s.requests[0].body)["tradingSymbol"] == "RELIANCE-EQ"
        finally:
            s.close()

    def test_never_retries_a_square_off_even_on_503(self):
        s = start_server(lambda h, i: send_json(h, 503, {"code": "SERVICE_UNAVAILABLE"}))
        try:
            with sync_client(s) as high:
                try:
                    high.portfolio.exit_all_positions()
                    raise AssertionError("expected HighApiError")
                except HighApiError:
                    pass
            assert len(s.requests) == 1
        finally:
            s.close()

    def test_exit_position_rejects_a_flavor_the_spec_does_not_allow_for_it(self):
        # ExitPositionRequest.flavor has no GTT, unlike PlaceOrderRequest.flavor
        # — this is the exact class of bug the shared contract's "never widen a
        # spec enum" rule exists to catch.
        s = start_server(lambda h, i: send_json(h, 200, ok({})))
        try:
            with sync_client(s) as high:
                try:
                    high.portfolio.exit_position({
                        "tradingSymbol": "RELIANCE-EQ", "productType": "INTRADAY", "flavor": "GTT",
                        "tradeSide": "S", "quantity": 50,
                    })
                    raise AssertionError("expected a validation error")
                except Exception as exc:
                    assert exc.__class__.__name__ == "ValidationError"
            assert s.requests == []
        finally:
            s.close()
