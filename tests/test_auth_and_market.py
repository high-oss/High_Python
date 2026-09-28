# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

from high_openapi.client import HighClient

from .server import send_json, start_server


def client_for(server, **overrides):
    options = {"base_url": server.base_url, "api_key": "key", "access_token": "tok"}
    options.update(overrides)
    return HighClient(options)


def ok(data):
    return {"requestId": "r", "data": data}


class TestAuthResource:
    def test_generate_access_token_sends_client_id_and_totp_with_the_api_key(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({"accessToken": "jwt", "expiresAt": "2026-09-28T06:30:56.123Z"})))
        try:
            with client_for(s) as high:
                token = high.auth.generate_access_token("C1", "123456")
            assert token.accessToken == "jwt"
            assert "clientId=C1" in s.requests[0].url
            assert "tOtp=123456" in s.requests[0].url
            assert s.requests[0].headers["x-api-key"] == "key"
            assert "authorization" not in s.requests[0].headers
        finally:
            s.close()

    def test_exposes_only_generate_access_token(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({})))
        try:
            with client_for(s) as high:
                for name in ["generate_consent", "consume_consent", "validate_token", "login", "login_url"]:
                    assert not hasattr(high.auth, name), f"auth.{name} must not exist"
                assert callable(high.auth.generate_access_token)
        finally:
            s.close()


class TestMarketResource:
    def test_status_returns_the_exchange_status_map(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "isHoliday": False, "date": "2026-09-25",
            "exchangeStatus": {"NSE": {"status": "OPEN", "timeRemainingInSeconds": 1}},
        })))
        try:
            with client_for(s) as high:
                status = high.market.status()
            assert status.exchangeStatus["NSE"].status == "OPEN"
            assert s.requests[0].url == "/v1/market/status"
        finally:
            s.close()


class TestClient:
    def test_honours_an_explicit_version_path(self):
        s = start_server(lambda h, i: send_json(h, 200, ok({
            "isHoliday": False, "date": "2026-09-25", "exchangeStatus": {},
        })))
        try:
            with HighClient(base_url=s.base_url, version_path="v2", access_token="tok") as high:
                high.market.status()
            assert s.requests[0].url == "/v2/market/status"
        finally:
            s.close()
