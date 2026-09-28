# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import json

import pytest

from high_openapi.client import AsyncHighClient, HighClient

from .server import send_json, start_server


def sync_client(server):
    return HighClient(base_url=server.base_url, access_token="tok")


PLACE_BODY = {
    "tradeSide": "B", "tradingSymbol": "RELIANCE-EQ", "productType": "DELIVERY",
    "flavor": "REGULAR", "orderType": "LIMIT", "validity": "DAY", "quantity": 10,
    "price": 1410, "isAMO": False,
}

MODIFY_BODY = {
    "orderId": "2609250000123502",
    "tradeSide": "B", "tradingSymbol": "RELIANCE-EQ", "productType": "DELIVERY",
    "flavor": "REGULAR", "orderType": "LIMIT", "validity": "DAY", "quantity": 5,
    "price": 1400, "isAMO": False,
}


def ok(data):
    return {"requestId": "r", "data": data}


class TestOrdersResourceSync:
    def test_place_posts_the_body_to_orders(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"orderId": "1", "error": ""})))
        try:
            with sync_client(s) as high:
                result = high.orders.place(PLACE_BODY)
            assert result.orderId == "1"
            assert s.requests[0].method == "POST"
            assert s.requests[0].url == "/v1/orders"
            assert json.loads(s.requests[0].body)["tradingSymbol"] == "RELIANCE-EQ"
        finally:
            s.close()

    def test_modify_patches_orders(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"orderId": "1", "error": ""})))
        try:
            with sync_client(s) as high:
                high.orders.modify(MODIFY_BODY)
            assert s.requests[0].method == "PATCH"
            assert s.requests[0].url == "/v1/orders"
        finally:
            s.close()

    def test_cancel_deletes_the_order_by_id(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"orderId": "1", "error": ""})))
        try:
            with sync_client(s) as high:
                high.orders.cancel("2609250000123502")
            assert s.requests[0].method == "DELETE"
            assert s.requests[0].url == "/v1/orders/2609250000123502"
        finally:
            s.close()

    def test_get_fetches_one_order_and_returns_the_book_shape(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"orders": [], "scrips": {}})))
        try:
            with sync_client(s) as high:
                book = high.orders.get("2609250000123456")
            assert book.orders == []
            assert s.requests[0].url == "/v1/orders/2609250000123456"
        finally:
            s.close()

    def test_list_fetches_the_order_book(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"orders": [], "scrips": {}})))
        try:
            with sync_client(s) as high:
                high.orders.list()
            assert s.requests[0].url == "/v1/orders/list"
        finally:
            s.close()

    def test_trades_fetches_the_trade_book(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"trades": [], "scrips": {}})))
        try:
            with sync_client(s) as high:
                high.orders.trades()
            assert s.requests[0].url == "/v1/orders/trades"
        finally:
            s.close()

    def test_trades_for_fetches_the_trades_of_one_order(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"trades": [], "scrips": {}})))
        try:
            with sync_client(s) as high:
                high.orders.trades_for("2609250000123456")
            assert s.requests[0].url == "/v1/orders/2609250000123456/trades"
        finally:
            s.close()

    def test_charges_posts_an_estimate_request(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "quantity": 10, "price": 1410, "productType": "DELIVERY", "tradeSide": "B",
            "tradedValue": 14100,
            "charges": {
                "brokerage": 5, "stt": 14.1, "clearingCharges": 0.141, "dpCharges": 0,
                "stampDuty": 2.115, "transactionCharges": 0.423, "turnoverCharges": 0.014,
                "gst": 1.002, "totalBuyCharges": 22.795, "totalSellCharges": 35.43,
                "breakevenPrice": 1415.823,
            },
        })))
        try:
            with sync_client(s) as high:
                charges = high.orders.charges({
                    "tradingSymbol": "RELIANCE-EQ", "quantity": 10, "price": 1410,
                    "productType": "DELIVERY", "tradeSide": "B",
                })
            assert charges.tradedValue == 14100
            assert s.requests[0].method == "POST"
            assert s.requests[0].url == "/v1/orders/charges"
        finally:
            s.close()

    def test_margin_posts_an_array_of_orders(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"margins": [], "spanSummary": {"span": 0, "exposureMargin": 0, "optionPremium": 0, "marginBenefit": 0, "totalMargin": 0}})))
        try:
            with sync_client(s) as high:
                high.orders.margin([
                    {"tradingSymbol": "RELIANCE-EQ", "quantity": 10, "price": 1410, "productType": "DELIVERY", "tradeSide": "B"},
                ])
            assert s.requests[0].url == "/v1/orders/margin"
            assert isinstance(json.loads(s.requests[0].body), list)
        finally:
            s.close()

    def test_encodes_an_order_id_that_would_otherwise_alter_the_path(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"orderId": "x", "error": ""})))
        try:
            with sync_client(s) as high:
                high.orders.cancel("a/b")
            assert s.requests[0].url == "/v1/orders/a%2Fb"
        finally:
            s.close()

    def test_place_rejects_a_payload_that_disagrees_with_the_spec(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"orderId": "1", "error": ""})))
        try:
            bad = dict(PLACE_BODY, flavor="NOT_A_REAL_FLAVOR")
            with sync_client(s) as high:
                with pytest.raises(Exception):  # pydantic.ValidationError
                    high.orders.place(bad)
            assert s.requests == []
        finally:
            s.close()


class TestOrdersResourceAsync:
    async def test_place_posts_the_body_to_orders(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"orderId": "1", "error": ""})))
        try:
            async with AsyncHighClient(base_url=s.base_url, access_token="tok") as high:
                result = await high.orders.place(PLACE_BODY)
            assert result.orderId == "1"
            assert s.requests[0].method == "POST"
        finally:
            s.close()

    async def test_margin_posts_an_array_of_orders(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"margins": [], "spanSummary": {"span": 0, "exposureMargin": 0, "optionPremium": 0, "marginBenefit": 0, "totalMargin": 0}})))
        try:
            async with AsyncHighClient(base_url=s.base_url, access_token="tok") as high:
                await high.orders.margin([
                    {"tradingSymbol": "RELIANCE-EQ", "quantity": 10, "price": 1410, "productType": "DELIVERY", "tradeSide": "B"},
                ])
            assert isinstance(json.loads(s.requests[0].body), list)
        finally:
            s.close()
