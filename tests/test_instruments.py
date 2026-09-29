# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""The instrument list: streaming/eager forms on both clients, resolved
internally through an unauthenticated manifest lookup — see
high_openapi/resources/instruments.py.

Covers the plan's Review Focus list end to end:
 1. unknown manifest categories ignored; a missing requested category errors
 2. a CSV header that disagrees with the manifest's columns fails loudly
 3. a non-https or non-allow-listed download URL is refused before any request
 4. a per-call timeout_ms works when the 30s default would not
 5. (server-side; not this SDK's concern) — not applicable here

Runs against real local servers only (tests/server.py), never a mocked
transport. Points 3 needs an actual TLS handshake to prove a *successful*
download still works once the gate passes, so those tests use the checked-in
self-signed loopback certificate (tests/fixtures/tls-*.pem) via
``start_server(..., tls=True)``; the refusal tests need no such thing, since
refusing happens before any connection is attempted at all.
"""

from __future__ import annotations

import time
from datetime import date

import httpx
import pytest

from high_openapi.client import AsyncHighClient, HighClient
from high_openapi.errors import HighApiError
from high_openapi.resources.instruments import _validate_download_url
from high_openapi.config import resolve_config

from .server import send_json, send_text, start_server

COLUMNS = [
    "exchange", "segment", "instrument", "high_trading_symbol", "scrip_key", "isin", "scrip_code", "symbol",
    "name", "group_series", "has_fno", "underlying_symbol", "expiry", "option_type", "strike_price",
    "price_tick", "lot_size",
]

# Row 1: a plain equity — exercises blanks in the derivative-only columns.
# Row 2: a future — blank isin/group_series/option_type/strike_price, a real expiry.
# Row 3: an option — a real strike_price, proving it comes back as a float
#        and price_tick (25) comes back exactly as printed, unnormalised.
_ROWS = [
    'NSE,ES,EQUITY,RELIANCE-EQ,NSE@2885,INE002A01018,2885,RELIANCE,"Reliance Industries, Ltd",EQ,1,,,,,5,1',
    'NSE,FO,FUTSTK,RELIANCE29JANFUT,NSE@43021,,43021,RELIANCE,"Reliance Industries Futures",,0,RELIANCE,'
    '2026-09-25,,,25,505',
    'NSE,FO,OPTSTK,RELIANCE29JAN2500CE,NSE@43099,,43099,RELIANCE,"Reliance Industries Options",,0,RELIANCE,'
    '2026-09-25,CE,2500.5,25,505',
]
CSV_TEXT = ",".join(COLUMNS) + "\n" + "\n".join(_ROWS) + "\n"
BAD_HEADER_CSV = ",".join(COLUMNS[:-1]) + "\n" + _ROWS[0] + "\n"  # missing lot_size


def _manifest(files, columns=COLUMNS):
    return {
        "requestId": "r",
        "data": {"generatedAt": "2026-09-29T02:53:10.000Z", "columns": columns, "files": files},
    }


def _file_entry(instrument, url, rows=3):
    return {
        "instrument": instrument, "url": url, "bytes": len(CSV_TEXT), "rows": rows,
        "checksum": "771b15b7351dbf791ec181da97dc1206", "updatedAt": "2026-09-29T02:53:09.000Z",
    }


def _router(routes):
    def handler(h, i):
        route = routes.get(h.path)
        if route is None:
            send_json(h, 404, {"requestId": "r", "code": "NOT_FOUND", "message": f"no route for {h.path}"})
            return
        route(h, i)

    return handler


def tls_sync_client(server, **overrides):
    options = {
        "base_url": server.base_url, "access_token": "tok",
        "instrument_allowed_hosts": ["127.0.0.1"],
        "http_client": httpx.Client(verify=False),
    }
    options.update(overrides)
    return HighClient(options)


def tls_async_client(server, **overrides):
    options = {
        "base_url": server.base_url, "access_token": "tok",
        "instrument_allowed_hosts": ["127.0.0.1"],
        "http_client": httpx.AsyncClient(verify=False),
    }
    options.update(overrides)
    return AsyncHighClient(options)


class TestSyncStreamAndList:
    def test_stream_yields_typed_rows_blanks_as_none_and_price_tick_untouched(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT),
        }), tls=True)
        try:
            with tls_sync_client(s) as high:
                rows = list(high.instruments.stream("equity"))
            assert len(rows) == 3

            equity, future, option = rows
            assert equity.high_trading_symbol == "RELIANCE-EQ"
            assert equity.name == "Reliance Industries, Ltd"  # quoted, comma preserved
            assert equity.scrip_code == 2885 and isinstance(equity.scrip_code, int)
            assert equity.has_fno == 1 and isinstance(equity.has_fno, int)
            assert equity.underlying_symbol is None
            assert equity.expiry is None
            assert equity.strike_price is None

            assert future.isin is None
            assert future.group_series is None
            assert future.option_type is None
            assert future.expiry == date(2026, 9, 25)
            assert future.price_tick == 25  # not rescaled

            assert option.strike_price == 2500.5 and isinstance(option.strike_price, float)
            assert option.option_type == "CE"
            assert option.price_tick == 25  # same tick value, different segment — left alone
        finally:
            s.close()

    def test_list_materialises_the_same_rows_eagerly(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT),
        }), tls=True)
        try:
            with tls_sync_client(s) as high:
                rows = high.instruments.list("equity")
            assert isinstance(rows, list)
            assert len(rows) == 3
        finally:
            s.close()

    def test_neither_the_manifest_request_nor_the_csv_request_carries_credentials(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT),
        }), tls=True)
        try:
            with tls_sync_client(s, access_token="SECRET-TOKEN", api_key="SECRET-KEY") as high:
                high.instruments.list("equity")
            assert len(s.requests) == 2
            for received in s.requests:
                assert "authorization" not in received.headers
                assert "x-api-key" not in received.headers
        finally:
            s.close()

    def test_manifest_is_fetched_once_and_cached_for_the_clients_lifetime(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT),
        }), tls=True)
        try:
            with tls_sync_client(s) as high:
                high.instruments.list("equity")
                high.instruments.list("equity")
            manifest_hits = [r for r in s.requests if r.url == "/v1/instruments"]
            csv_hits = [r for r in s.requests if r.url == "/csv/equity.csv"]
            assert len(manifest_hits) == 1
            assert len(csv_hits) == 2
        finally:
            s.close()

    def test_a_requested_category_the_manifest_does_not_list_is_a_clear_error(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
        }), tls=True)
        try:
            with tls_sync_client(s) as high:
                with pytest.raises(HighApiError, match="etfs"):
                    high.instruments.list("etfs")
        finally:
            s.close()

    def test_a_manifest_category_this_sdk_does_not_know_is_ignored_not_a_crash(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([
                {"instrument": "bonds", "url": f"{s.base_url}/csv/bonds.csv", "bytes": 1, "rows": 0,
                 "checksum": "x", "updatedAt": "2026-09-29T02:53:09.000Z"},
                _file_entry("equity", f"{s.base_url}/csv/equity.csv"),
            ])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT),
        }), tls=True)
        try:
            with tls_sync_client(s) as high:
                rows = high.instruments.list("equity")  # would raise if the unknown entry crashed parsing
            assert len(rows) == 3
        finally:
            s.close()

    def test_a_csv_header_that_disagrees_with_the_manifests_columns_fails_loudly(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", BAD_HEADER_CSV),
        }), tls=True)
        try:
            with tls_sync_client(s) as high:
                with pytest.raises(HighApiError, match="header"):
                    high.instruments.list("equity")
        finally:
            s.close()

    def test_a_timeout_ms_override_covers_the_whole_download_not_just_headers(self):
        def slow_csv(h, i):
            time.sleep(0.3)
            send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT)

        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
            "/csv/equity.csv": slow_csv,
        }), tls=True)
        try:
            with tls_sync_client(s) as high:
                with pytest.raises(HighApiError, match="(?i)timed out"):
                    high.instruments.list("equity", timeout_ms=50)
        finally:
            s.close()


class TestAsyncStreamAndList:
    async def test_stream_yields_typed_rows_via_async_for(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT),
        }), tls=True)
        try:
            high = tls_async_client(s)
            rows = []
            async for row in high.instruments.stream("equity"):
                rows.append(row)
            await high.aclose()
            assert len(rows) == 3
            assert rows[0].name == "Reliance Industries, Ltd"
            assert rows[1].expiry == date(2026, 9, 25)
            assert rows[2].strike_price == 2500.5
        finally:
            s.close()

    async def test_list_materialises_the_same_rows_eagerly(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT),
        }), tls=True)
        try:
            high = tls_async_client(s)
            rows = await high.instruments.list("equity")
            await high.aclose()
            assert len(rows) == 3
        finally:
            s.close()

    async def test_neither_request_carries_credentials(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT),
        }), tls=True)
        try:
            high = tls_async_client(s, access_token="SECRET-TOKEN", api_key="SECRET-KEY")
            await high.instruments.list("equity")
            await high.aclose()
            assert len(s.requests) == 2
            for received in s.requests:
                assert "authorization" not in received.headers
                assert "x-api-key" not in received.headers
        finally:
            s.close()

    async def test_a_requested_category_the_manifest_does_not_list_is_a_clear_error(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([_file_entry("equity", f"{s.base_url}/csv/equity.csv")])),
        }), tls=True)
        try:
            high = tls_async_client(s)
            with pytest.raises(HighApiError, match="etfs"):
                await high.instruments.list("etfs")
            await high.aclose()
        finally:
            s.close()


class TestSafetyGateRefusesBeforeAnyRequest:
    """Uses a plain (non-TLS) server on purpose: the point of these tests is
    that the CSV path is never hit, so there is nothing to serve there."""

    def test_refuses_a_non_https_download_url_and_never_requests_it(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([
                _file_entry("equity", f"{s.base_url}/csv/equity.csv"),  # http://, not https
            ])),
            "/csv/equity.csv": lambda h, i: send_text(h, 200, "text/csv; charset=utf-8", CSV_TEXT),
        }))
        try:
            with HighClient(base_url=s.base_url, access_token="tok", instrument_allowed_hosts=["127.0.0.1"]) as high:
                with pytest.raises(HighApiError, match="https"):
                    high.instruments.list("equity")
            # Only the manifest fetch happened — the CSV was never requested.
            assert [r.url for r in s.requests] == ["/v1/instruments"]
        finally:
            s.close()

    def test_refuses_a_host_outside_the_allowlist_and_never_requests_it(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([
                _file_entry("equity", "https://evil.example.invalid/scrip-master/equity.csv"),
            ])),
        }))
        try:
            with HighClient(base_url=s.base_url, access_token="tok") as high:  # default allowlist only
                with pytest.raises(HighApiError, match="allowed hosts"):
                    high.instruments.list("equity")
            assert [r.url for r in s.requests] == ["/v1/instruments"]
        finally:
            s.close()

    async def test_async_client_refuses_the_same_way(self):
        s = start_server(_router({
            "/v1/instruments": lambda h, i: send_json(h, 200, _manifest([
                _file_entry("equity", "https://evil.example.invalid/scrip-master/equity.csv"),
            ])),
        }))
        try:
            high = AsyncHighClient(base_url=s.base_url, access_token="tok")
            with pytest.raises(HighApiError, match="allowed hosts"):
                await high.instruments.list("equity")
            await high.aclose()
            assert [r.url for r in s.requests] == ["/v1/instruments"]
        finally:
            s.close()


class TestValidateDownloadUrlDirectly:
    """Pure decision logic (no I/O) — mirrors how tests/test_engine.py covers
    _engine.py's pure helpers directly rather than through a server."""

    def _config(self, **overrides):
        return resolve_config({"access_token": "tok", **overrides}, env={})

    def test_accepts_https_on_an_allowed_host(self):
        _validate_download_url(
            "https://high-space.blr1.cdn.digitaloceanspaces.com/scrip-master/x.csv", self._config(),
        )  # does not raise

    def test_rejects_http(self):
        with pytest.raises(HighApiError, match="https"):
            _validate_download_url(
                "http://high-space.blr1.cdn.digitaloceanspaces.com/scrip-master/x.csv", self._config(),
            )

    def test_rejects_an_unlisted_host(self):
        with pytest.raises(HighApiError, match="allowed hosts"):
            _validate_download_url("https://not-the-cdn.example.com/x.csv", self._config())

    def test_honours_a_custom_allowlist(self):
        cfg = self._config(instrument_allowed_hosts=["files.example.com"])
        _validate_download_url("https://files.example.com/x.csv", cfg)  # does not raise
        with pytest.raises(HighApiError, match="allowed hosts"):
            _validate_download_url("https://high-space.blr1.cdn.digitaloceanspaces.com/x.csv", cfg)
