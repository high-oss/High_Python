# high-openapi

Official Python SDK for the [HIGH Open API](https://openapi.high.live). Typed
against the canonical OpenAPI contract with pydantic v2 models, with sync and
async clients.

## Install

```bash
pip install high-openapi
```

Python 3.9 or newer. Runtime dependencies: [`httpx`](https://www.python-httpx.org/)
(sync and async transport) and [`pydantic`](https://docs.pydantic.dev/) v2
(request validation and response models). Nothing else.

## Quickstart

```python
import os
from high_openapi import HighClient

high = HighClient(
    environment="sandbox",        # or "production" (the default)
    api_key=os.environ["HIGH_API_KEY"],
    access_token=os.environ["HIGH_ACCESS_TOKEN"],
)

funds = high.portfolio.funds()
print(funds.availableBalance)
```

Async:

```python
import asyncio
from high_openapi import AsyncHighClient

async def main():
    async with AsyncHighClient(access_token=access_token) as high:
        funds = await high.portfolio.funds()
        print(funds.availableBalance)

asyncio.run(main())
```

`HighClient` owns one pooled `httpx.Client` for its lifetime; `AsyncHighClient`
owns one pooled `httpx.AsyncClient`. Use them as context managers (`with` /
`async with`), or call `.close()` / `await .aclose()` yourself.

## Configuration

| Option | Default | Notes |
|---|---|---|
| `environment` | `production` | `production` or `sandbox` |
| `base_url` | from `environment` | Overrides the REST host |
| `ws_base_url` | from `environment` | Datafeed socket host, reserved for the feed client |
| `version_path` | `v1` | The segment between host and operation path |
| `api_key` | `HIGH_API_KEY` | Sent as `x-api-key`, for `auth.generate_access_token` |
| `access_token` | `HIGH_ACCESS_TOKEN` | Sent as `Authorization: Bearer` |
| `timeout_ms` | `30000` | Per request, covering headers and body |
| `max_retries` | `2` | Idempotent reads only |
| `max_retry_delay_ms` | `30000` | Ceiling on one retry delay; a longer `Retry-After` fails fast |
| `log_level` | `silent` | `silent`, `error`, `warn`, `info`, `debug` |
| `log_sink` | stderr/stdout | Where log lines go |
| `user_agent` | — | Appended to the SDK's own |
| `http_client` | a new `httpx.Client`/`httpx.AsyncClient` | Transport override, for tests or a proxy-aware client |
| `instrument_allowed_hosts` | the instrument list's usual CDN host | Hosts `high.instruments` may download the CSV files from |

Options can be passed as a mapping (`HighClient({"api_key": ...})`) or as
keyword arguments (`HighClient(api_key=...)`) — both are equivalent.

Host resolution order: explicit `base_url`, then explicit `environment`, then
`HIGH_BASE_URL`, then `HIGH_ENVIRONMENT`, then production. **An explicit
`environment` suppresses the environment-variable hosts entirely** — a client
written as `environment="sandbox"` is never silently rerouted to production by
a stray `HIGH_BASE_URL` left in a shell profile. An unknown environment raises
at construction, naming the valid values — never at request time.

Sandbox and production issue **separate API keys**. Switching environment
means switching credentials too; the SDK does not rewrite them for you.

## Authentication

The SDK covers the **TOTP flow**, which is one call:

```python
high = HighClient(api_key=api_key)

token = high.auth.generate_access_token(client_id="C1", t_otp="123456")

# Use it for everything else.
trading = HighClient(access_token=token.accessToken)
```

A HIGH access token lasts 24 hours. The SDK attaches whatever you give it and
**does not refresh** — minting the next one needs a fresh TOTP, so the timing
is yours to choose. Configuration is settled at construction, so a new token
means a new client.

### What this SDK does not do

It wraps the TOTP endpoint and nothing else from the auth area. The redirect
consent flow (`/auth/generate-consent`, `/auth/login`, `/auth/consume-consent`)
is built around a browser page only a human can complete, and token
introspection (`/auth/validate-token`) is not wrapped either — a caller learns
a token is invalid from the next call's 401. If you need those endpoints, call
them directly.

## Errors

Every failure is a `HighApiError`, including timeouts and transport failures
(which carry `status=0`). No raw `httpx` exception and no JSON decode error
escapes the SDK.

```python
from high_openapi import HighApiError

try:
    high.orders.place(order)
except HighApiError as error:
    error.status       # HTTP status, or 0 for transport failures
    error.code          # e.g. "ORDER_REJECTED" — see ERROR_CODES
    error.request_id     # quote this in support tickets
    error.messages         # validation errors return several
    error.body               # the parsed payload, for a non-standard error
```

`ERROR_CODES` holds the documented catalogue. The gateway can return codes
outside it, so `code` is a plain string — compare against the constants, but
do not assume the set is closed.

A caller-cancelled operation is **not** a `HighApiError`: the sync client
raises `high_openapi.OperationCancelled`, and the async client lets
`asyncio.CancelledError` propagate — see Cancellation below.

Request and response bodies are also validated against the pinned spec by
pydantic. A payload that disagrees with the spec (a bad enum value, a missing
required field) raises `pydantic.ValidationError` before anything is sent —
a stronger guarantee than a purely static type system gives, since it also
catches a caller building a dict by hand.

## Retries

Retried: `GET` and `HEAD` only, on 429, 500, 502, 503 and 504, honouring
`Retry-After` in both its seconds and HTTP-date forms, with exponential
backoff otherwise. A `Retry-After` longer than `max_retry_delay_ms` (30s by
default) is not waited out — the SDK gives up and raises, rather than
blocking your call inside a wait you cannot interrupt.

Never retried: `POST`, `PATCH`, `DELETE` — a retried `orders.place` would be a
duplicate order, and a retried square-off would be a second square-off.
Transport failures and timeouts are never retried either, on any method: they
raise immediately rather than going through the retry decision.

## Logging

Off by default. Each level prints itself and everything more severe.

```python
high = HighClient(access_token=access_token, log_level="debug")
# 2026-09-28T17:05:12.345Z DEBUG HIGH -> POST https://openapi.high.live/v1/orders
#   {'body': {'tradeSide': 'B', 'tradingSymbol': 'RELIANCE-EQ', 'quantity': 1, ...}}
# 2026-09-28T17:05:12.488Z DEBUG HIGH <- 200 in 143ms https://openapi.high.live/v1/orders
#   {'requestId': 'a1b2c3', 'body': {'orderId': '2609250000123456', 'error': ''}}
```

| Level | What it prints |
|---|---|
| `error` | API error responses (status, code, requestId), timeouts, transport failures |
| `warn` | Each retry, and giving up when `Retry-After` exceeds the ceiling |
| `info` | One line per request: method and URL |
| `debug` | The above plus request and response bodies, and response timing |

Every line is prefixed with an ISO-8601 timestamp and the level.

Credentials never reach the log. Headers are not logged at all, and the
`tOtp`, `apiKey`, `accessToken`, `tokenId` and `stepToken` query parameters
are replaced with `REDACTED` — so debug logs are safe to ship to an
aggregator. Pass `log_sink` (an object with `error`/`warn`/`info`/`debug`
methods) to route lines somewhere other than stderr/stdout.

## Cancellation

Python has no single cancellation primitive shared by sync and async code, so
the two clients use the idiomatic mechanism for each:

- **Async** (`AsyncHighClient`): no explicit parameter. Cancel the enclosing
  `asyncio.Task` (`task.cancel()`) and `asyncio.CancelledError` propagates
  unchanged — honoured both mid-request and mid-retry-delay, the full
  realisation of the contract's cancellation guarantee.
- **Sync** (`HighClient`): every method takes an optional `cancel_event`
  (a `threading.Event`) as a keyword argument, checked before each attempt is
  sent and interruptible during a retry delay:

  ```python
  import threading

  cancel_event = threading.Event()
  threading.Timer(1.0, cancel_event.set).start()
  high.scrips.quotes({"symbols": ["RELIANCE-EQ"]}, cancel_event=cancel_event)
  ```

  **Known limitation**: Python's synchronous socket I/O has no
  cooperative-cancellation hook (unlike JS's `AbortSignal`), so setting the
  event cannot abort a request already handed to `httpx`'s blocking `send()`
  — only the request timeout bounds that case. If you need a hard mid-request
  cancellation guarantee, use `AsyncHighClient`.

## Resources

24 operations across five namespaces, methods named per PEP 8:

| Namespace | Methods |
|---|---|
| `auth` | `generate_access_token` |
| `orders` | `place` · `modify` · `get` · `cancel` · `list` · `trades` · `trades_for` · `charges` · `margin` |
| `portfolio` | `positions` · `holdings` · `funds` · `convert_position` · `exit_all_positions` · `exit_position` |
| `scrips` | `quotes` · `ohlc` · `depth` · `expiries` · `future_data` · `historical` · `option_chain` |
| `market` | `status` |

Each method returns a parsed pydantic model — the `{requestId, data}`
envelope is unwrapped for you, and `request_id` reaches you on the error. A
request body can be passed as a plain `dict` or as the exact generated
request model (`high_openapi.resources.orders.PlaceOrderRequest`, etc.);
either way it is validated against the pinned spec before anything is sent.

A few shapes worth knowing, because they are not what you might guess:

```python
# quotes and ohlc return a dict keyed by trading symbol, not a list
quotes = high.scrips.quotes({"symbols": ["RELIANCE-EQ"]})
quotes["RELIANCE-EQ"].LTP

# historical returns COLUMNAR lists — index i across them is one candle
c = high.scrips.historical({
    "tradingSymbol": "RELIANCE-EQ",
    "interval": "1D",
    "fromTime": 1789929000,   # epoch seconds
    "toTime": 1790330400,
})
c.close[0]                   # not c[0].close

# positions and holdings both have `snapshot`, with different shapes
high.portfolio.positions().snapshot.totalPL
high.portfolio.holdings().snapshot.investment
```

### Instrument list

`high.instruments` fetches the scrip master — every instrument HIGH knows —
as one of five categories:

| Category | Contents |
|---|---|
| `all` | Every scrip, all exchanges |
| `equity` | NSE/BSE cash equity |
| `derivatives` | NSE/BSE futures and options |
| `commodity` | MCX futures, options and spot |
| `etfs` | NSE/BSE exchange-traded funds |

It needs **no credentials** — neither `api_key` nor `access_token` is sent
for this call, so it works even on a client constructed with neither. The
streaming form is the primary API; `all` and `derivatives` run to 14 MB and
11 MB, so avoid `list()` for those unless you actually need every row in
memory at once.

```python
# Streaming (primary) — never buffers the whole file in memory.
for row in high.instruments.stream("equity"):
    print(row.high_trading_symbol, row.symbol, row.lot_size)

# Eager — materialises the whole category into a list.
equities = high.instruments.list("equity")
```

Async:

```python
async for row in high.instruments.stream("equity"):
    print(row.high_trading_symbol)

equities = await high.instruments.list("equity")
```

Every row has these 17 columns. A blank CSV field comes back as `None`, not
an empty string:

| Column | Type | Notes |
|---|---|---|
| `exchange` | `str` | |
| `segment` | `str` | |
| `instrument` | `str \| None` | |
| `high_trading_symbol` | `str` | |
| `scrip_key` | `str` | |
| `isin` | `str \| None` | |
| `scrip_code` | `int` | |
| `symbol` | `str` | |
| `name` | `str` | |
| `group_series` | `str \| None` | |
| `has_fno` | `int` | |
| `underlying_symbol` | `str \| None` | Derivatives only |
| `expiry` | `date \| None` | Derivatives only |
| `option_type` | `str \| None` | Options only |
| `strike_price` | `float \| None` | Options only |
| `price_tick` | `int` | **Not normalised** — its scale varies by segment; do not rescale it yourself without checking which segment a row belongs to |
| `lot_size` | `int` | |

The files are rebuilt once each trading morning and do not change
intraday — download once a day and cache the result rather than fetching it
on every call. `stream()` / `list()` both take an optional `timeout_ms` to
raise the ceiling for a single call, without changing the client's global
`timeout_ms`:

```python
equities = high.instruments.list("equity", timeout_ms=60_000)
```

## Live datafeed

No socket client ships in this release. `ws_base_url` is resolved and exposed
on `client.config`, but nothing consumes it yet.

## Regenerating from the spec

Models come from the canonical spec at the commit pinned in `spec.lock.json`,
generated with [`datamodel-code-generator`](https://github.com/koxudaxi/datamodel-code-generator)
as pydantic v2 (not `openapi-python-client`, which only emits `attrs`
dataclasses and cannot satisfy the pydantic v2 requirement — see
`scripts/regenerate.py`'s docstring for the full reasoning).

```bash
python scripts/regenerate.py   # rewrites src/high_openapi/generated/ from that commit
```

`generated/` is committed and never hand-edited. To move to a newer contract,
update `spec.lock.json`, regenerate, and commit both.

## Development

Python is not required on the host; everything runs in Docker.

```bash
docker run --rm -v "$(pwd):/w" -w //w python:3.12-slim bash -lc \
  "pip install -q -e '.[dev]' && pytest -q"
```

Tests run against a real local `http.server.ThreadingHTTPServer` rather than a
mocked transport, so a change in how the SDK builds requests is caught rather
than asserted around.

## Licence

MIT. See [LICENSE](./LICENSE).
