# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import asyncio
import time

import pytest

from high_openapi.config import resolve_config
from high_openapi.errors import HighApiError
from high_openapi.http_async import new_client, send_request

from .server import send_json, start_server


def config_for(server, **overrides):
    options = {"base_url": server.base_url, "access_token": "tok", "timeout_ms": 2000}
    options.update(overrides)
    return resolve_config(options, env={})


class TestRetryPolicy:
    async def test_retries_an_idempotent_get_on_503_and_returns_the_eventual_success(self):
        def handler(h, i):
            if i == 0:
                return send_json(h, 503, {"code": "SERVICE_UNAVAILABLE", "message": "try later"})
            return send_json(h, 200, {"requestId": "r", "data": {"ok": True}})

        s = start_server(handler)
        try:
            cfg = config_for(s)
            async with new_client(cfg) as client:
                data = await send_request(client, cfg, method="GET", path="/orders/list", auth="bearer")
            assert data == {"ok": True}
            assert len(s.requests) == 2
        finally:
            s.close()

    async def test_never_retries_a_write_even_on_503(self):
        s = start_server(lambda h, i: send_json(h, 503, {"code": "SERVICE_UNAVAILABLE"}))
        try:
            cfg = config_for(s)
            async with new_client(cfg) as client:
                with pytest.raises(HighApiError):
                    await send_request(client, cfg, method="POST", path="/orders", auth="bearer", body={})
            assert len(s.requests) == 1
        finally:
            s.close()

    async def test_gives_up_after_max_retries_and_raises_the_last_error(self):
        s = start_server(lambda h, i: send_json(h, 500, {"code": "UNHANDLED_ERROR"}))
        try:
            cfg = config_for(s, max_retries=2)
            async with new_client(cfg) as client:
                with pytest.raises(HighApiError) as excinfo:
                    await send_request(client, cfg, method="GET", path="/orders/list", auth="bearer")
            assert excinfo.value.status == 500
            assert len(s.requests) == 3
        finally:
            s.close()

    async def test_honours_a_numeric_retry_after_on_429(self):
        def handler(h, i):
            if i == 0:
                body = b'{"code":"SERVICE_UNAVAILABLE"}'
                h.send_response(429)
                h.send_header("Content-Type", "application/json")
                h.send_header("Retry-After", "0")
                h.send_header("Content-Length", str(len(body)))
                h.end_headers()
                h.wfile.write(body)
                return
            return send_json(h, 200, {"requestId": "r", "data": True})

        s = start_server(handler)
        try:
            cfg = config_for(s)
            async with new_client(cfg) as client:
                data = await send_request(client, cfg, method="GET", path="/orders/list", auth="bearer")
            assert data is True
            assert len(s.requests) == 2
        finally:
            s.close()


class TestRetryDelayCeiling:
    async def test_gives_up_rather_than_sleeping_past_max_retry_delay_ms(self):
        def handler(h, i):
            body = b'{"code":"SERVICE_UNAVAILABLE"}'
            h.send_response(429)
            h.send_header("Content-Type", "application/json")
            h.send_header("Retry-After", "86400")
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body)

        s = start_server(handler)
        try:
            cfg = config_for(s, max_retries=2, max_retry_delay_ms=100)
            started = time.monotonic()
            async with new_client(cfg) as client:
                with pytest.raises(HighApiError) as excinfo:
                    await send_request(client, cfg, method="GET", path="/orders/list", auth="bearer")
            assert excinfo.value.status == 429
            assert time.monotonic() - started < 2
            assert len(s.requests) == 1
        finally:
            s.close()


class TestTimeoutCoversTheBody:
    async def test_times_out_when_the_body_stalls_after_headers_arrive(self):
        def handler(h, i):
            full = b'{"requestId":"r","data":true}'
            h.send_response(200)
            h.send_header("Content-Type", "application/json")
            h.send_header("Content-Length", str(len(full)))
            h.end_headers()
            h.wfile.write(full[:20])
            h.wfile.flush()
            time.sleep(3)
            h.wfile.write(full[20:])

        s = start_server(handler)
        try:
            cfg = config_for(s, timeout_ms=150, max_retries=0)
            started = time.monotonic()
            async with new_client(cfg) as client:
                with pytest.raises(HighApiError) as excinfo:
                    await send_request(client, cfg, method="GET", path="/orders/list", auth="bearer")
            assert "timed out" in str(excinfo.value).lower()
            assert time.monotonic() - started < 2
        finally:
            s.close()


class TestCancellation:
    async def test_surfaces_a_caller_cancellation_during_the_request_unchanged(self):
        s = start_server(lambda h, i: time.sleep(1))
        try:
            cfg = config_for(s, timeout_ms=5000)
            async with new_client(cfg) as client:
                task = asyncio.ensure_future(
                    send_request(client, cfg, method="GET", path="/orders/list", auth="bearer")
                )
                await asyncio.sleep(0.05)
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert len(s.requests) == 1
        finally:
            s.close()

    async def test_does_not_send_another_request_after_cancel_mid_retry_sleep(self):
        def handler(h, i):
            body = b'{"code":"SERVICE_UNAVAILABLE"}'
            h.send_response(429)
            h.send_header("Content-Type", "application/json")
            h.send_header("Retry-After", "3")
            h.send_header("Content-Length", str(len(body)))
            h.end_headers()
            h.wfile.write(body)

        s = start_server(handler)
        try:
            cfg = config_for(s)
            async with new_client(cfg) as client:
                task = asyncio.ensure_future(
                    send_request(client, cfg, method="GET", path="/orders/list", auth="bearer")
                )
                await asyncio.sleep(0.1)  # let the first attempt land and the retry sleep begin
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            assert len(s.requests) == 1
        finally:
            s.close()
