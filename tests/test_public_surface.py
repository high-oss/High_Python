# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import high_openapi as sdk


def test_exports_the_clients_the_error_type_and_the_catalogues():
    assert callable(sdk.HighClient)
    assert callable(sdk.AsyncHighClient)
    assert issubclass(sdk.HighApiError, Exception)
    assert isinstance(sdk.ERROR_CODES, tuple)
    assert isinstance(sdk.LOG_LEVELS, tuple)
    assert sdk.ENVIRONMENTS["production"]["api"] == "https://openapi.high.live"
    assert sdk.ENVIRONMENTS["sandbox"]["api"] == "https://sandbox.high.live"


def test_wraps_neither_the_browser_login_page_the_consent_flow_nor_introspection():
    client = sdk.HighClient(access_token="tok")
    for name in ["login", "login_url", "render_login", "generate_consent", "consume_consent", "validate_token"]:
        assert not hasattr(client.auth, name), f"auth.{name} must not exist"


def test_exposes_all_five_resources_on_a_constructed_client():
    client = sdk.HighClient(access_token="tok")
    for name in ["auth", "orders", "portfolio", "scrips", "market"]:
        assert getattr(client, name, None) is not None, f"client.{name} is missing"


def test_exposes_all_five_resources_on_the_async_client_too():
    client = sdk.AsyncHighClient(access_token="tok")
    for name in ["auth", "orders", "portfolio", "scrips", "market"]:
        assert getattr(client, name, None) is not None, f"client.{name} is missing"


# The instrument list is a sixth resource, added alongside the original five.
# It is deliberately not part of EXPECTED_METHODS / the "24 operations" count
# below: it is not one of the wrapped request/response operations from the
# contract's table, it is a facade over an internal manifest lookup — see
# resources/instruments.py's module docstring.
def test_exposes_the_instruments_resource_with_exactly_a_streaming_and_an_eager_form():
    for client in (sdk.HighClient(access_token="tok"), sdk.AsyncHighClient(access_token="tok")):
        assert callable(client.instruments.stream)
        assert callable(client.instruments.list)


EXPECTED_METHODS = {
    "auth": ["generate_access_token"],
    "orders": ["place", "modify", "get", "cancel", "list", "trades", "trades_for", "charges", "margin"],
    "portfolio": ["positions", "holdings", "funds", "convert_position", "exit_all_positions", "exit_position"],
    "scrips": ["quotes", "ohlc", "depth", "expiries", "future_data", "historical", "option_chain"],
    "market": ["status"],
}


def test_exposes_every_operation_the_sdk_covers_as_a_method():
    client = sdk.HighClient(access_token="tok")
    count = 0
    for resource, methods in EXPECTED_METHODS.items():
        target = getattr(client, resource)
        for method in methods:
            assert callable(getattr(target, method, None)), f"{resource}.{method}"
            count += 1
    # The spec has 27 operations; the SDK covers 24 — login, the two consent
    # operations and token introspection are deliberately excluded.
    assert count == 24


def test_exposes_every_operation_on_the_async_client_too():
    client = sdk.AsyncHighClient(access_token="tok")
    count = 0
    for resource, methods in EXPECTED_METHODS.items():
        target = getattr(client, resource)
        for method in methods:
            assert callable(getattr(target, method, None)), f"{resource}.{method}"
            count += 1
    assert count == 24


def test_ships_minimal_runtime_dependencies():
    try:
        import tomllib  # Python 3.11+
    except ModuleNotFoundError:
        import tomli as tomllib  # Python 3.9/3.10
    from pathlib import Path

    pyproject = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())
    deps = pyproject["project"]["dependencies"]
    names = {d.split(">=")[0].split("<")[0].strip() for d in deps}
    assert names == {"httpx", "pydantic"}
    assert pyproject["project"]["name"] == "high-openapi"
