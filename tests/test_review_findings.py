# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""The conformance list from the shared SDK contract (§11), the checks not
already covered by their own module's test file. Mirrors
high-sdk-node/tests/review-findings.test.ts's role: one file pinning the
guarantees the README and the contract make.
"""

import json
from pathlib import Path

import pytest

from high_openapi.client import AsyncHighClient, HighClient
from high_openapi.config import ENVIRONMENTS
from high_openapi.errors import ERROR_CODES
from high_openapi.resources.scrips import ExpiryType

SPEC_PATH = Path(__file__).resolve().parent.parent / "src" / "high_openapi" / "generated" / "openapi.json"


def _spec():
    return json.loads(SPEC_PATH.read_text(encoding="utf-8"))


# Point 15: ENVIRONMENTS still matches the pinned spec's servers block.
class TestEnvironmentsMatchesTheSpec:
    def test_has_one_entry_per_server_with_the_host_the_spec_declares(self):
        spec = _spec()
        from_spec = {}
        for server in spec["servers"]:
            from urllib.parse import urlparse

            parsed = urlparse(server["url"])
            from_spec[server["x-environment"]] = f"{parsed.scheme}://{parsed.netloc}"
        from_code = {name: hosts["api"] for name, hosts in ENVIRONMENTS.items()}
        assert from_code == from_spec


# Point 15 (continued): ERROR_CODES still matches the pinned spec's catalogue.
class TestErrorCodesMatchesTheSpec:
    def test_matches_the_x_error_codes_catalogue(self):
        spec = _spec()
        catalogue = spec["components"]["schemas"]["Error"]["properties"]["code"]["x-error-codes"]
        assert set(ERROR_CODES) == set(catalogue)


# ExpiryType is hand-written (see resources/scrips.py docstring) because no
# datamodel-code-generator scope turns this inline path parameter into a
# named type. This is the runtime check standing in for what a static type
# system would catch at compile time in Node/Go/etc.
class TestExpiryTypeMatchesTheSpec:
    def test_matches_the_enum_the_pinned_spec_declares(self):
        spec = _spec()
        params = spec["paths"]["/scrips/{symbol}/{type}/expiries"]["get"]["parameters"]
        type_param = next(p for p in params if p["name"] == "type")
        assert set(type_param["schema"]["enum"]) == {"futures", "options"}
        assert ExpiryType.__args__ == ("futures", "options")


# Point 12: credentials absent from a serialised client, at the HighClient
# level (config.py's own containment is covered by test_config.py).
class TestCredentialContainmentOnTheClient:
    def test_sync_client_repr_str_and_vars_never_show_credentials(self):
        client = HighClient(access_token="SECRET-TOKEN", api_key="SECRET-KEY")
        try:
            for dump in (repr(client), str(client), repr(vars(client))):
                assert "SECRET-TOKEN" not in dump
                assert "SECRET-KEY" not in dump
        finally:
            client.close()

    def test_async_client_repr_str_and_vars_never_show_credentials(self):
        client = AsyncHighClient(access_token="SECRET-TOKEN", api_key="SECRET-KEY")
        for dump in (repr(client), str(client), repr(vars(client))):
            assert "SECRET-TOKEN" not in dump
            assert "SECRET-KEY" not in dump

    def test_resources_never_show_credentials_either(self):
        client = HighClient(access_token="SECRET-TOKEN", api_key="SECRET-KEY")
        try:
            for resource in (client.auth, client.orders, client.portfolio, client.scrips, client.market):
                dump = repr(vars(resource))
                assert "SECRET-TOKEN" not in dump
                assert "SECRET-KEY" not in dump
        finally:
            client.close()

    def test_credentials_remain_usable_despite_being_hidden(self):
        from .server import send_json, start_server

        s = start_server(lambda h, i: send_json(h, 200, {
            "requestId": "r",
            "data": {"isHoliday": False, "date": "2026-09-25", "exchangeStatus": {}},
        }))
        try:
            with HighClient(base_url=s.base_url, access_token="SECRET-TOKEN") as client:
                client.market.status()
            assert s.requests[0].headers["authorization"] == "Bearer SECRET-TOKEN"
        finally:
            s.close()


# Point 14: the excluded auth operations do not exist, on both clients.
class TestExcludedAuthMethodsDoNotExist:
    @pytest.mark.parametrize("make_client", [
        lambda: HighClient(access_token="tok"),
        lambda: AsyncHighClient(access_token="tok"),
    ])
    def test_neither_client_wraps_the_excluded_operations(self, make_client):
        client = make_client()
        for name in ["login", "generate_consent", "consume_consent", "validate_token"]:
            assert not hasattr(client.auth, name)


# Point 11: path parameters percent-encoded, exercised through the resource
# layer rather than path_of() directly (test_paths.py covers path_of itself).
class TestPathParameterEncodingThroughTheResourceLayer:
    def test_a_slash_in_a_path_parameter_never_adds_a_path_segment(self):
        from .server import send_json, start_server

        s = start_server(lambda h, i: send_json(h, 200, {"requestId": "r", "data": {"orderId": "x", "error": ""}}))
        try:
            with HighClient(base_url=s.base_url, access_token="tok") as client:
                client.orders.cancel("a/b")
            assert s.requests[0].url == "/v1/orders/a%2Fb"
        finally:
            s.close()
