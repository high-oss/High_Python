# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Settles where requests go and what they carry, once, at client construction.

Resolution order: an explicit ``base_url`` wins outright; then an explicit
``environment``; then ``HIGH_BASE_URL`` / ``HIGH_ENVIRONMENT``; then
production. An unknown environment fails here rather than at request time.

The trap: an explicit ``environment`` suppresses the environment-variable
hosts entirely, so a client written as ``environment="sandbox"`` is never
silently rerouted to production by a stray ``HIGH_BASE_URL`` left in a shell
profile.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, List, Literal, Mapping, Optional, Tuple, TypedDict
from weakref import WeakKeyDictionary

from .logger import LOG_LEVELS, Logger, LogSink, create_logger

ENVIRONMENTS = {
    "production": {"api": "https://openapi.high.live", "ws": "wss://openapi.high.live"},
    "sandbox": {"api": "https://sandbox.high.live", "ws": "wss://sandbox.high.live"},
}

Environment = Literal["production", "sandbox"]

_DEFAULT_USER_AGENT = "high-sdk-python/0.0.1"

# The CDN host the instrument list manifest normally points at. Overridable
# via instrument_allowed_hosts, e.g. to point a sandbox client at a fixture
# host in tests — but the default is what protects a caller who never
# thinks about it from a manifest response redirecting the download
# somewhere unexpected.
_DEFAULT_INSTRUMENT_HOSTS: Tuple[str, ...] = ("high-space.blr1.cdn.digitaloceanspaces.com",)

# Credentials never live in a ResolvedConfig instance's own __dict__ — they
# live here, keyed by object identity, so repr(), str(), vars() and anything
# that walks __dict__ (dataclasses.asdict, pickle's default reducer, a crash
# reporter) cannot print them. api_key/access_token stay ordinary attribute
# reads for the SDK itself via the properties below.
_SECRETS: "WeakKeyDictionary[ResolvedConfig, tuple]" = WeakKeyDictionary()


class HighClientOptions(TypedDict, total=False):
    """Options accepted by :func:`resolve_config` / ``HighClient``. A plain
    dict (or any mapping) is accepted — this type is for documentation and
    static checking, not a required construction path."""

    environment: str
    base_url: str
    ws_base_url: str
    version_path: str
    api_key: str
    access_token: str
    timeout_ms: float
    max_retries: int
    max_retry_delay_ms: float
    user_agent: str
    log_level: str
    log_sink: LogSink
    http_client: Any
    instrument_allowed_hosts: List[str]


@dataclass(frozen=True)
class ResolvedConfig:
    """Where requests go and what they carry. Immutable after construction —
    a new access token means a new client, never a mutation in place."""

    base_url: str
    # Reserved for the datafeed client. Unused by the REST resources.
    ws_base_url: str
    version_path: str
    timeout_ms: float
    max_retries: int
    max_retry_delay_ms: float
    user_agent: str
    log_level: str
    # Ready to use; already honours log_level.
    logger: Logger
    # Transport override, for tests or a proxy-aware client.
    http_client: Optional[Any] = field(default=None)
    # Hosts the instrument-list CSV download may come from. Checked against
    # the manifest's per-category url before any download request is made —
    # see resources/instruments.py.
    instrument_allowed_hosts: Tuple[str, ...] = field(default=_DEFAULT_INSTRUMENT_HOSTS)

    @property
    def api_key(self) -> Optional[str]:
        return _SECRETS.get(self, (None, None))[0]

    @property
    def access_token(self) -> Optional[str]:
        return _SECRETS.get(self, (None, None))[1]


def _assert_environment(value: str, source: str) -> None:
    if value not in ENVIRONMENTS:
        valid = ", ".join(ENVIRONMENTS.keys())
        raise ValueError(f'Unknown HIGH environment "{value}" ({source}). Valid values: {valid}.')


def _assert_log_level(value: str, source: str) -> None:
    if value not in LOG_LEVELS:
        valid = ", ".join(LOG_LEVELS)
        raise ValueError(f'Unknown HIGH log level "{value}" ({source}). Valid values: {valid}.')


def _trim_slashes(value: str) -> str:
    return value.strip("/")


def _require_positive(value: float, name: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"{name} must be a positive number, received {value!r}.")
    return value


def _require_non_negative_int(value: int, name: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"{name} must be a non-negative integer, received {value!r}.")
    return value


def resolve_config(
    options: Optional[Mapping[str, Any]] = None,
    env: Optional[Mapping[str, str]] = None,
) -> ResolvedConfig:
    options = options or {}
    env = os.environ if env is None else env

    environment = "production"
    explicit_environment = "environment" in options and options["environment"] is not None
    if explicit_environment:
        _assert_environment(options["environment"], "options['environment']")
        environment = options["environment"]
    elif env.get("HIGH_ENVIRONMENT"):
        from_env = env["HIGH_ENVIRONMENT"]
        _assert_environment(from_env, "HIGH_ENVIRONMENT")
        environment = from_env

    hosts = ENVIRONMENTS[environment]

    base_url = options.get("base_url") or (
        hosts["api"] if explicit_environment else (env.get("HIGH_BASE_URL") or hosts["api"])
    )
    ws_base_url = options.get("ws_base_url") or (
        hosts["ws"] if explicit_environment else (env.get("HIGH_WS_BASE_URL") or hosts["ws"])
    )

    user_agent = (
        f"{_DEFAULT_USER_AGENT} {options['user_agent']}" if options.get("user_agent") else _DEFAULT_USER_AGENT
    )

    log_level = "silent"
    if options.get("log_level") is not None:
        _assert_log_level(options["log_level"], "options['log_level']")
        log_level = options["log_level"]
    elif env.get("HIGH_LOG_LEVEL"):
        from_env = env["HIGH_LOG_LEVEL"]
        _assert_log_level(from_env, "HIGH_LOG_LEVEL")
        log_level = from_env

    # Validated here rather than mid-request, so a bad number cannot surface
    # as a raw exception from deep inside the retry loop.
    timeout_ms = _require_positive(options.get("timeout_ms", 30_000), "timeout_ms")
    max_retries = _require_non_negative_int(options.get("max_retries", 2), "max_retries")
    max_retry_delay_ms = _require_positive(options.get("max_retry_delay_ms", 30_000), "max_retry_delay_ms")

    config = ResolvedConfig(
        base_url=base_url.rstrip("/"),
        ws_base_url=ws_base_url.rstrip("/"),
        version_path=_trim_slashes(options.get("version_path", "v1")),
        timeout_ms=timeout_ms,
        max_retries=max_retries,
        max_retry_delay_ms=max_retry_delay_ms,
        user_agent=user_agent,
        log_level=log_level,
        logger=create_logger(log_level, options.get("log_sink")),
        http_client=options.get("http_client"),
        instrument_allowed_hosts=tuple(options.get("instrument_allowed_hosts") or _DEFAULT_INSTRUMENT_HOSTS),
    )

    api_key = options.get("api_key") or env.get("HIGH_API_KEY")
    access_token = options.get("access_token") or env.get("HIGH_ACCESS_TOKEN")
    _SECRETS[config] = (api_key, access_token)

    return config


def build_url(config: ResolvedConfig, path: str) -> str:
    """``base_url`` + ``version_path`` + operation path, with no doubled or
    missing slashes."""
    segments = [config.base_url, config.version_path, _trim_slashes(path)]
    return "/".join(segment for segment in segments if segment != "")
