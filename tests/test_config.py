# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

import pytest

from high_openapi.config import ENVIRONMENTS, build_url, resolve_config


def test_defaults_to_production_v1():
    config = resolve_config({}, env={})
    assert config.base_url == "https://openapi.high.live"
    assert config.version_path == "v1"
    assert config.timeout_ms == 30_000
    assert config.max_retries == 2


def test_maps_the_sandbox_environment_to_its_host():
    assert resolve_config({"environment": "sandbox"}, env={}).base_url == ENVIRONMENTS["sandbox"]["api"]


def test_resolves_a_websocket_host_alongside_the_api_host():
    assert resolve_config({}, env={}).ws_base_url == ENVIRONMENTS["production"]["ws"]
    assert resolve_config({}, env={}).ws_base_url == "wss://openapi-feed.high.live"


def test_sandbox_has_no_websocket_host_there_is_no_sandbox_feed():
    # ENVIRONMENTS["sandbox"] deliberately carries no "ws" entry — see
    # config.py and the datafeed plan/contract §9.
    assert "ws" not in ENVIRONMENTS["sandbox"]
    assert resolve_config({"environment": "sandbox"}, env={}).ws_base_url is None


def test_exposes_the_resolved_environment_name():
    assert resolve_config({}, env={}).environment == "production"
    assert resolve_config({"environment": "sandbox"}, env={}).environment == "sandbox"


def test_lets_ws_base_url_be_overridden_without_touching_base_url():
    config = resolve_config({"ws_base_url": "ws://127.0.0.1:9001"}, env={})
    assert config.ws_base_url == "ws://127.0.0.1:9001"
    assert config.base_url == ENVIRONMENTS["production"]["api"]


def test_lets_an_explicit_base_url_win_over_the_environment():
    config = resolve_config({"environment": "sandbox", "base_url": "http://localhost:8080"}, env={})
    assert config.base_url == "http://localhost:8080"


def test_reads_environment_and_credentials_from_env_vars_when_not_passed():
    config = resolve_config(
        {}, env={"HIGH_ENVIRONMENT": "sandbox", "HIGH_API_KEY": "k", "HIGH_ACCESS_TOKEN": "t"}
    )
    assert config.base_url == ENVIRONMENTS["sandbox"]["api"]
    assert config.api_key == "k"
    assert config.access_token == "t"


def test_prefers_explicit_options_over_env_vars():
    config = resolve_config({"api_key": "explicit"}, env={"HIGH_API_KEY": "from-env"})
    assert config.api_key == "explicit"


def test_rejects_an_unknown_environment_at_construction_naming_valid_values():
    with pytest.raises(ValueError, match="(?s)staging.*production.*sandbox"):
        resolve_config({"environment": "staging"}, env={})


def test_defaults_logging_to_silent():
    assert resolve_config({}, env={}).log_level == "silent"


def test_takes_a_log_level_from_options_or_env_options_winning():
    assert resolve_config({"log_level": "debug"}, env={}).log_level == "debug"
    assert resolve_config({}, env={"HIGH_LOG_LEVEL": "warn"}).log_level == "warn"
    assert resolve_config({"log_level": "info"}, env={"HIGH_LOG_LEVEL": "warn"}).log_level == "info"


def test_rejects_an_unknown_log_level_at_construction_naming_valid_values():
    with pytest.raises(ValueError, match="(?s)verbose.*silent.*error.*warn.*info.*debug"):
        resolve_config({"log_level": "verbose"}, env={})
    with pytest.raises(ValueError, match="trace"):
        resolve_config({}, env={"HIGH_LOG_LEVEL": "trace"})


def test_exposes_a_ready_logger_honouring_that_level():
    assert resolve_config({"log_level": "warn"}, env={}).logger.enabled("warn") is True
    assert resolve_config({"log_level": "warn"}, env={}).logger.enabled("debug") is False


def test_rejects_an_unknown_high_environment_value_too():
    with pytest.raises(ValueError, match="prod"):
        resolve_config({}, env={"HIGH_ENVIRONMENT": "prod"})


def test_rejects_negative_max_retries():
    with pytest.raises(ValueError, match="max_retries"):
        resolve_config({"max_retries": -1}, env={})


def test_rejects_non_positive_timeout():
    with pytest.raises(ValueError, match="timeout_ms"):
        resolve_config({"timeout_ms": 0}, env={})
    with pytest.raises(ValueError, match="timeout_ms"):
        resolve_config({"timeout_ms": -1}, env={})


def test_rejects_non_positive_max_retry_delay():
    with pytest.raises(ValueError, match="max_retry_delay_ms"):
        resolve_config({"max_retry_delay_ms": 0}, env={})


# Resolution order and its trap: an explicit environment must beat env vars.
def test_explicit_environment_beats_high_base_url():
    config = resolve_config(
        {"environment": "sandbox"}, env={"HIGH_BASE_URL": "https://openapi.high.live"}
    )
    assert config.base_url == ENVIRONMENTS["sandbox"]["api"]


def test_explicit_environment_beats_high_ws_base_url_too():
    config = resolve_config(
        {"environment": "sandbox"},
        env={"HIGH_BASE_URL": "https://openapi.high.live", "HIGH_WS_BASE_URL": "wss://openapi.high.live"},
    )
    assert config.base_url == ENVIRONMENTS["sandbox"]["api"]
    # Suppressed just like HIGH_BASE_URL — and sandbox has no "ws" host to
    # fall back to regardless, so this stays None rather than picking up
    # the env var or borrowing production's.
    assert config.ws_base_url is None


def test_high_base_url_still_applies_when_no_environment_given():
    assert resolve_config({}, env={"HIGH_BASE_URL": "http://localhost:9999"}).base_url == "http://localhost:9999"


def test_explicit_base_url_still_wins_over_everything():
    config = resolve_config(
        {"environment": "sandbox", "base_url": "http://localhost:1"},
        env={"HIGH_BASE_URL": "https://openapi.high.live"},
    )
    assert config.base_url == "http://localhost:1"


class TestBuildUrl:
    def test_joins_base_version_and_path(self):
        config = resolve_config({}, env={})
        assert build_url(config, "/orders/list") == "https://openapi.high.live/v1/orders/list"

    def test_tolerates_stray_slashes_on_every_part(self):
        config = resolve_config({"base_url": "https://h.example/", "version_path": "/v2/"}, env={})
        assert build_url(config, "/orders") == "https://h.example/v2/orders"
        assert build_url(config, "orders") == "https://h.example/v2/orders"

    def test_supports_a_base_url_that_already_carries_a_path_prefix(self):
        config = resolve_config({"base_url": "https://h.example/api/"}, env={})
        assert build_url(config, "/orders") == "https://h.example/api/v1/orders"

    def test_allows_an_empty_version_path_for_an_unversioned_host(self):
        config = resolve_config({"version_path": ""}, env={})
        assert build_url(config, "/orders") == "https://openapi.high.live/orders"


class TestCredentialContainment:
    def test_credentials_absent_from_repr_and_str(self):
        config = resolve_config({"api_key": "SECRET-KEY", "access_token": "SECRET-TOKEN"}, env={})
        assert "SECRET-KEY" not in repr(config)
        assert "SECRET-TOKEN" not in repr(config)
        assert "SECRET-KEY" not in str(config)
        assert "SECRET-TOKEN" not in str(config)

    def test_credentials_absent_from_vars(self):
        config = resolve_config({"api_key": "SECRET-KEY", "access_token": "SECRET-TOKEN"}, env={})
        dumped = repr(vars(config))
        assert "SECRET-KEY" not in dumped
        assert "SECRET-TOKEN" not in dumped

    def test_credentials_still_usable_despite_being_hidden(self):
        config = resolve_config({"api_key": "SECRET-KEY", "access_token": "SECRET-TOKEN"}, env={})
        assert config.api_key == "SECRET-KEY"
        assert config.access_token == "SECRET-TOKEN"
