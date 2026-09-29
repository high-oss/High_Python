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
- `high.instruments`: the scrip master as five categories (`all`, `equity`,
  `derivatives`, `commodity`, `etfs`), each downloadable as a typed,
  17-column row model. `stream()` (sync generator / async generator) is the
  primary form; `list()` materialises the same rows eagerly. Needs no
  credentials. Blank CSV fields become `None`; `price_tick` is left exactly
  as reported, never rescaled. Takes an optional per-call `timeout_ms` for
  the larger categories. A new `instrument_allowed_hosts` client option
  restricts which hosts the CSV may be downloaded from.
- `HighFeed` (sync) / `AsyncHighFeed` (async): the live datafeed client, a
  second pair of clients beside `HighClient`/`AsyncHighClient`, built from
  the same options. Production only (`openapi-feed.high.live`) — a client
  resolved to `sandbox` raises `ValueError` at construction, since there is
  no sandbox feed. Auth (`{"type":"cn","sessionid":...}`, no caller-settable
  `mode`) is a gate: nothing else is sent until its acknowledgement arrives,
  and a rejected auth (`HighFeedAuthError`, with `HighFeedNoDataPlanError`/
  `HighFeedInvalidTokenError` subtypes) is never retried or reconnected.
  `subscribe_quotes`/`subscribe_depth`/`subscribe_indices` (plus
  `unsubscribe_*`/`snapshot_*`) take HIGH scrip keys only; indices get their
  own methods and are validated both ways against the committed index table
  (`scripts/regenerate_index_map.py`, `src/high_openapi/feed/_index_map.py`,
  rendered from the canonical `index-feed-map.json`'s 93 rows — 87 after
  resolving 6 scripKeys the source lists twice with conflicting symbols;
  last row wins, consistently with how every SDK renders the same file) —
  an index key on the quote/depth methods, or a non-index key on the index
  methods, raises `HighFeedKeyError` naming the key. `maxScripPerConn`/`maxScripPerReq` from
  the auth acknowledgement are honoured, splitting large subscriptions and
  raising `HighFeedLimitError` rather than exceeding the connection cap.
  Ticks are deltas, merged into typed `Quote`/`Depth`/`IndexTick` snapshots
  keyed by the caller's own scrip key, with `changed_fields`, `Decimal`
  prices, per-field timestamp parsing, and unknown fields preserved in
  `extra`. A FULL-mode quote tick's top-of-book fields are split into a
  separate one-level `Depth` event, never presented as the five-level book
  the dedicated depth feed carries. Reconnects on transport failure only,
  with backoff, re-authenticating and fully re-subscribing before reporting
  connected again. Delivery: `async for event in feed` on `AsyncHighFeed`;
  `feed.add_listener(callback)` on the synchronous `HighFeed`. The one new
  runtime dependency this adds is `websockets`.

### Notes

- The redirect consent flow and token introspection are not wrapped. Auth is
  the TOTP endpoint only.
- Models are generated with `datamodel-code-generator`, not
  `openapi-python-client` — the latter only emits `attrs` dataclasses and
  cannot produce the pydantic v2 models this SDK's stack requires. See
  `scripts/regenerate.py`.
