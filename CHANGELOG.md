# Changelog

All notable changes to this package are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.0.1] — 2026-09-28

First release. Pre-1.0: the surface may still change.

### Added

- `HighClient` (sync) and `AsyncHighClient` (async) covering 24 of the 27
  HIGH Open API operations across five namespaces: `auth`, `orders`,
  `portfolio`, `scrips` and `market`.
- Pydantic v2 models generated from the canonical OpenAPI contract with
  `datamodel-code-generator`, pinned by commit in `spec.lock.json` and
  regenerated with `python scripts/regenerate.py`. Request bodies accept a
  plain `dict` or the generated request model, validated against the pinned
  spec either way.
- Configuration by `environment` (`production` / `sandbox`) or explicit
  `base_url`, with an independently settable `version_path`, and environment
  variable fallbacks. An unknown environment or a bad numeric option fails at
  construction, never mid-request.
- One `HighApiError` for every failure, including timeouts and transport
  failures, carrying `status`, `code`, `request_id`, `messages` and `body`.
- Retries for `GET` and `HEAD` only, on 429 and 5xx, honouring `Retry-After`
  in both its forms, capped by `max_retry_delay_ms`. Writes, transport
  failures and timeouts are never retried.
- Configurable logging (`silent` to `debug`) with ISO-8601 timestamps, request
  and response bodies at `debug`, and credential redaction throughout.
- Cancellation: `asyncio.Task.cancel()` on the async client (native, covers
  mid-request and mid-retry-delay); an optional `cancel_event`
  (`threading.Event`) on the sync client, honoured before each attempt and
  during a retry delay (documented limitation: cannot abort an in-flight
  synchronous request — see the README's Cancellation section).
- Credentials (`api_key`, `access_token`) are never attributes of the
  resolved config's own `__dict__`, so they never appear in `repr()`,
  `str()` or `vars()` of the client, its config, or its resources.
- Only two runtime dependencies: `httpx` and `pydantic` (v2).

### Notes

- The redirect consent flow and token introspection are not wrapped. Auth is
  the TOTP endpoint only.
- No datafeed socket client. `ws_base_url` is resolved but unused.
- Models are generated with `datamodel-code-generator`, not
  `openapi-python-client` — the latter only emits `attrs` dataclasses and
  cannot produce the pydantic v2 models this SDK's stack requires. See
  `scripts/regenerate.py`.
