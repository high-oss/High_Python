# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import pytest

from high_openapi.config import resolve_config
from high_openapi.errors import HighApiError
from high_openapi.http_sync import new_client, send_request

from .server import send_json, start_server


def config_for(server, **overrides):
    options = {"base_url": server.base_url, "access_token": "tok", "api_key": "key"}
    options.update(overrides)
    return resolve_config(options, env={})


class Sink:
    def __init__(self):
        self.lines = []

    def _push(self, m, d=None):
        self.lines.append(m if d is None else f"{m} {d}")

    def error(self, m, d=None): self._push(m, d)
    def warn(self, m, d=None): self._push(m, d)
    def info(self, m, d=None): self._push(m, d)
    def debug(self, m, d=None): self._push(m, d)


def test_unwraps_the_envelope_and_returns_only_data():
    s = start_server(lambda h, i: send_json(h, 200, {"requestId": "a1b2c3", "data": {"orderId": "1"}}))
    try:
        client = new_client(config_for(s))
        data = send_request(client, config_for(s), method="GET", path="/orders/list", auth="bearer")
        assert data == {"orderId": "1"}
    finally:
        s.close()


def test_sends_bearer_token_for_bearer_auth_and_no_api_key():
    s = start_server(lambda h, i: send_json(h, 200, {"requestId": "r", "data": True}))
    try:
        cfg = config_for(s)
        send_request(new_client(cfg), cfg, method="GET", path="/orders/list", auth="bearer")
        assert s.requests[0].headers["authorization"] == "Bearer tok"
        assert "x-api-key" not in s.requests[0].headers
    finally:
        s.close()


def test_sends_api_key_for_api_key_auth_and_no_bearer_token():
    s = start_server(lambda h, i: send_json(h, 200, {"requestId": "r", "data": True}))
    try:
        cfg = config_for(s)
        send_request(new_client(cfg), cfg, method="GET", path="/auth/generate-access-token", auth="apiKey")
        assert s.requests[0].headers["x-api-key"] == "key"
        assert "authorization" not in s.requests[0].headers
    finally:
        s.close()


def test_fails_before_sending_when_the_required_credential_is_missing():
    s = start_server(lambda h, i: send_json(h, 200, {"requestId": "r", "data": True}))
    try:
        cfg = resolve_config({"base_url": s.base_url}, env={})
        with pytest.raises(HighApiError, match="access_token"):
            send_request(new_client(cfg), cfg, method="GET", path="/orders/list", auth="bearer")
        assert s.requests == []
    finally:
        s.close()


def test_serialises_a_json_body_and_sets_content_type():
    s = start_server(lambda h, i: send_json(h, 200, {"requestId": "r", "data": {}}))
    try:
        cfg = config_for(s)
        send_request(new_client(cfg), cfg, method="POST", path="/orders", auth="bearer", body={"quantity": 10})
        assert s.requests[0].body == '{"quantity":10}'
        assert "application/json" in s.requests[0].headers["content-type"]
    finally:
        s.close()


def test_appends_defined_query_parameters_and_skips_undefined_ones():
    s = start_server(lambda h, i: send_json(h, 200, {"requestId": "r", "data": True}))
    try:
        cfg = config_for(s)
        send_request(
            new_client(cfg), cfg, method="GET", path="/auth/generate-access-token", auth="apiKey",
            query={"clientId": "C1", "tOtp": 123456, "unused": None},
        )
        assert "clientId=C1" in s.requests[0].url
        assert "tOtp=123456" in s.requests[0].url
        assert "unused" not in s.requests[0].url
    finally:
        s.close()


def test_maps_an_error_envelope_to_high_api_error():
    s = start_server(
        lambda h, i: send_json(h, 400, {"requestId": "a1b2c3", "code": "ORDER_REJECTED", "message": "Insufficient funds"})
    )
    try:
        cfg = config_for(s)
        with pytest.raises(HighApiError) as excinfo:
            send_request(new_client(cfg), cfg, method="POST", path="/orders", auth="bearer")
        assert excinfo.value.code == "ORDER_REJECTED"
        assert excinfo.value.request_id == "a1b2c3"
    finally:
        s.close()


def test_turns_a_non_json_error_body_into_high_api_error():
    def handler(h, i):
        body = b"<html><body>502 Bad Gateway</body></html>"
        h.send_response(502)
        h.send_header("Content-Type", "text/html")
        h.send_header("Content-Length", str(len(body)))
        h.end_headers()
        h.wfile.write(body)

    s = start_server(handler)
    try:
        cfg = config_for(s, max_retries=0)
        with pytest.raises(HighApiError) as excinfo:
            send_request(new_client(cfg), cfg, method="GET", path="/orders/list", auth="bearer")
        assert excinfo.value.status == 502
        assert excinfo.value.__class__.__name__ != "JSONDecodeError"
    finally:
        s.close()


def test_turns_a_204_with_no_body_into_none_rather_than_a_parse_error():
    def handler(h, i):
        h.send_response(204)
        h.end_headers()

    s = start_server(handler)
    try:
        cfg = config_for(s)
        data = send_request(new_client(cfg), cfg, method="DELETE", path="/orders/1", auth="bearer")
        assert data is None
    finally:
        s.close()


def test_times_out_with_high_api_error_rather_than_hanging():
    s = start_server(lambda h, i: None)  # never responds
    try:
        cfg = config_for(s, timeout_ms=50, max_retries=0)
        with pytest.raises(HighApiError) as excinfo:
            send_request(new_client(cfg), cfg, method="GET", path="/orders/list", auth="bearer")
        assert excinfo.value.status == 0
        assert "timed out" in str(excinfo.value).lower()
    finally:
        s.close()


def test_sends_a_user_agent_identifying_the_sdk():
    s = start_server(lambda h, i: send_json(h, 200, {"requestId": "r", "data": True}))
    try:
        cfg = config_for(s)
        send_request(new_client(cfg), cfg, method="GET", path="/orders/list", auth="bearer")
        assert "high-sdk-python" in s.requests[0].headers["user-agent"]
    finally:
        s.close()


class TestLogging:
    def test_prints_nothing_by_default(self):
        s = start_server(lambda h, i: send_json(h, 200, {"requestId": "r", "data": True}))
        try:
            sink = Sink()
            cfg = config_for(s, log_sink=sink)
            send_request(new_client(cfg), cfg, method="GET", path="/orders/list", auth="bearer")
            assert sink.lines == []
        finally:
            s.close()

    def test_logs_request_and_response_status_at_debug(self):
        s = start_server(lambda h, i: send_json(h, 200, {"requestId": "a1b2c3", "data": True}))
        try:
            sink = Sink()
            cfg = config_for(s, log_level="debug", log_sink=sink)
            send_request(new_client(cfg), cfg, method="GET", path="/orders/list", auth="bearer")
            joined = "\n".join(sink.lines)
            assert "GET" in joined
            assert "orders/list" in joined
            assert "200" in joined
        finally:
            s.close()

    def test_never_logs_the_bearer_token_the_api_key_or_the_totp(self):
        s = start_server(lambda h, i: send_json(h, 200, {"requestId": "r", "data": True}))
        try:
            sink = Sink()
            cfg = config_for(
                s, log_level="debug", log_sink=sink, access_token="SECRET-TOKEN", api_key="SECRET-KEY"
            )
            send_request(
                new_client(cfg), cfg, method="GET", path="/auth/generate-access-token", auth="apiKey",
                query={"clientId": "C1", "tOtp": "123456"},
            )
            joined = "\n".join(sink.lines)
            assert "SECRET-TOKEN" not in joined
            assert "SECRET-KEY" not in joined
            assert "123456" not in joined
            assert "REDACTED" in joined
        finally:
            s.close()

    def test_warns_when_it_retries(self):
        def handler(h, i):
            if i == 0:
                return send_json(h, 503, {"code": "SERVICE_UNAVAILABLE"})
            return send_json(h, 200, {"requestId": "r", "data": True})

        s = start_server(handler)
        try:
            sink = Sink()
            cfg = config_for(s, log_level="warn", log_sink=sink)
            send_request(new_client(cfg), cfg, method="GET", path="/orders/list", auth="bearer")
            assert "retry" in "\n".join(sink.lines).lower()
        finally:
            s.close()
