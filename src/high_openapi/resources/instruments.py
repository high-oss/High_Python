# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""The instrument list: every scrip HIGH knows, as a CSV, one file per
category.

Internally this resolves the download through a small manifest fetch — see
the module docstring on ``_manifest_for`` below — but that indirection is not
part of the public surface: callers only ever see ``stream()`` / ``list()``.

``InstrumentCategory`` is a ``Literal`` derived from the generated
``Instrument`` enum (``generated/models.py``), never hand-widened to ``str``
— ``tests/test_review_findings.py`` asserts the two stay in lockstep, the
runtime analogue of the Node SDK's compile-time derivation (contract §8).

Both the manifest fetch and the CSV download attach no credentials at all —
``auth="none"`` on the manifest call skips ``headers_for``'s credential
branches entirely, and the CSV download builds its own headers by hand. The
CSV host is a third-party CDN; sending it a bearer token would leak it.
"""

from __future__ import annotations

import csv
from datetime import date
from typing import Any, AsyncIterator, Dict, Iterable, Iterator, List, Literal, Optional, Sequence
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

from .. import http_async, http_sync
from ..config import ResolvedConfig
from ..errors import HighApiError, error_from_response
from ..generated.models import InstrumentFile, InstrumentsManifest
from ..logger import redact_url

__all__ = [
    "InstrumentsResource",
    "AsyncInstrumentsResource",
    "InstrumentCategory",
    "InstrumentRow",
]

# Derived from generated.models.Instrument (an Enum, not a Literal, so it
# cannot be referenced directly in a type position) rather than widened to
# str — see the module docstring. test_review_findings.py asserts these
# values stay equal to {member.value for member in Instrument}.
InstrumentCategory = Literal["all", "equity", "derivatives", "commodity", "etfs"]

_KNOWN_CATEGORIES = {"all", "equity", "derivatives", "commodity", "etfs"}


class InstrumentRow(BaseModel):
    """One row of an instrument list CSV.

    Field names and order come from the manifest's own ``columns`` — this
    model is validated by *name*, not position, so a reordering on the server
    is harmless as long as the 17 documented columns are still present.
    Blank CSV fields become ``None``, never an empty string.

    ``price_tick`` is intentionally left exactly as the CSV reports it: its
    scale varies by segment (equity vs. derivatives vs. commodity), and
    normalising it here would be a silent pricing bug for anyone building a
    limit price from it.
    """

    exchange: str
    segment: str
    instrument: Optional[str] = None
    high_trading_symbol: str
    scrip_key: str
    isin: Optional[str] = None
    scrip_code: int
    symbol: str
    name: str
    group_series: Optional[str] = None
    has_fno: int
    underlying_symbol: Optional[str] = None
    expiry: Optional[date] = None
    option_type: Optional[str] = None
    strike_price: Optional[float] = None
    price_tick: int
    lot_size: int


def _blank(value: str) -> Optional[str]:
    return value if value != "" else None


def _row_from_record(record: Dict[str, str], *, category: str, row_index: int) -> InstrumentRow:
    try:
        return InstrumentRow(
            exchange=record["exchange"],
            segment=record["segment"],
            instrument=_blank(record["instrument"]),
            high_trading_symbol=record["high_trading_symbol"],
            scrip_key=record["scrip_key"],
            isin=_blank(record["isin"]),
            scrip_code=int(record["scrip_code"]),
            symbol=record["symbol"],
            name=record["name"],
            group_series=_blank(record["group_series"]),
            has_fno=int(record["has_fno"]),
            underlying_symbol=_blank(record["underlying_symbol"]),
            expiry=_blank(record["expiry"]),
            option_type=_blank(record["option_type"]),
            strike_price=float(record["strike_price"]) if record["strike_price"] != "" else None,
            price_tick=int(record["price_tick"]),
            lot_size=int(record["lot_size"]),
        )
    except (KeyError, ValueError, ValidationError) as exc:
        raise HighApiError(
            f"Instrument list row {row_index} for category {category!r} could not be parsed: {exc}",
            status=0,
            body=record,
        ) from exc


def _row_from_values(header: Sequence[str], values: Sequence[str], *, category: str, row_index: int) -> InstrumentRow:
    if len(values) != len(header):
        raise HighApiError(
            f"Instrument list row {row_index} for category {category!r} has {len(values)} fields, "
            f"expected {len(header)} (the manifest's columns).",
            status=0,
            body=list(values),
        )
    return _row_from_record(dict(zip(header, values)), category=category, row_index=row_index)


def _parse_manifest(raw: Any) -> InstrumentsManifest:
    """Builds the generated ``InstrumentsManifest`` model from the raw
    envelope data, first dropping any ``files`` entry whose ``instrument``
    the SDK does not recognise.

    This has to happen *before* ``model_validate`` because
    ``InstrumentFile.instrument`` is generated as a closed enum: a manifest
    naming a category ahead of this SDK's pinned spec must be tolerated
    (Review Focus #1 — unknown entries ignored, not a crash), and pydantic
    would otherwise raise on the whole response for one entry it does not
    understand.
    """
    if not isinstance(raw, dict):
        raise HighApiError("The instrument list manifest response was not an object.", status=0, body=raw)

    files = raw.get("files")
    known_files = [
        entry for entry in (files or []) if isinstance(entry, dict) and entry.get("instrument") in _KNOWN_CATEGORIES
    ]
    return InstrumentsManifest.model_validate({**raw, "files": known_files})


def _select_file(manifest: InstrumentsManifest, category: str) -> InstrumentFile:
    for file in manifest.files:
        if file.instrument.value == category:
            return file
    known = ", ".join(sorted({file.instrument.value for file in manifest.files})) or "none"
    raise HighApiError(
        f"The instrument list manifest has no entry for category {category!r}. "
        f"Categories it currently lists: {known}.",
        status=0,
    )


def _validate_download_url(url: str, config: ResolvedConfig) -> None:
    """Refused before any request is made — see the module docstring and
    Global Constraint 3 / Review Focus 3 in the build plan."""
    parsed = urlparse(url)
    if parsed.scheme != "https":
        raise HighApiError(
            f"Refusing to download the instrument list from a non-https URL ({url!r}).", status=0,
        )
    if parsed.hostname not in config.instrument_allowed_hosts:
        allowed = ", ".join(config.instrument_allowed_hosts)
        raise HighApiError(
            f"Refusing to download the instrument list from host {parsed.hostname!r}, which is not in "
            f"the allowed hosts ({allowed}). Pass instrument_allowed_hosts to the client to allow it.",
            status=0,
        )


def _non_blank(lines: Iterable[str]) -> Iterator[str]:
    for line in lines:
        if line != "":
            yield line


def _download_headers(config: ResolvedConfig) -> dict:
    # No headers_for() here on purpose — this must never gain a credential
    # branch by accident the way an "auth" string might invite. Explicit and
    # minimal: nothing but what any anonymous HTTP client would send.
    return {"accept": "text/csv", "user-agent": config.user_agent}


class InstrumentsResource:
    def __init__(self, client: httpx.Client, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config
        self._manifest: Optional[InstrumentsManifest] = None

    def _manifest_for(self, *, timeout_ms: Optional[float], cancel_event) -> InstrumentsManifest:
        # Cached for the client's lifetime — the manifest is rebuilt once a
        # trading morning, not per call.
        if self._manifest is None:
            data = http_sync.send_request(
                self._client, self._config, method="GET", path="/instruments", auth="none",
                cancel_event=cancel_event, timeout_ms=timeout_ms,
            )
            self._manifest = _parse_manifest(data)
        return self._manifest

    def stream(
        self,
        category: InstrumentCategory = "all",
        *,
        timeout_ms: Optional[float] = None,
        cancel_event=None,
    ) -> Iterator[InstrumentRow]:
        """The primary form. Streams the CSV row by row — ``all`` and
        ``derivatives`` are 14 MB and 11 MB, so this never buffers the whole
        file in memory. Nothing is fetched until this generator is
        iterated."""
        manifest = self._manifest_for(timeout_ms=timeout_ms, cancel_event=cancel_event)
        file = _select_file(manifest, category)
        url = str(file.url)
        _validate_download_url(url, self._config)

        headers = _download_headers(self._config)
        effective_timeout_ms = timeout_ms if timeout_ms is not None else self._config.timeout_ms
        self._config.logger.info(f"HIGH GET {redact_url(url)}")

        try:
            with self._client.stream(
                "GET", url, headers=headers, timeout=httpx.Timeout(effective_timeout_ms / 1000),
            ) as response:
                if cancel_event is not None and cancel_event.is_set():
                    raise HighApiError("Operation cancelled before the download completed.", status=0)
                if not response.is_success:
                    text = response.read().decode("utf-8", errors="replace")
                    raise error_from_response(response.status_code, None, text)

                lines = _non_blank(response.iter_lines())
                reader = csv.reader(lines)
                try:
                    header = next(reader)
                except StopIteration:
                    raise HighApiError(f"The instrument list for category {category!r} was empty.", status=0)

                if header != list(manifest.columns):
                    raise HighApiError(
                        f"The instrument list CSV header for category {category!r} does not match the "
                        f"manifest's columns. Expected {list(manifest.columns)!r}, got {header!r}.",
                        status=0,
                    )

                for row_index, values in enumerate(reader):
                    if cancel_event is not None and cancel_event.is_set():
                        raise HighApiError("Operation cancelled before the download completed.", status=0)
                    yield _row_from_values(header, values, category=category, row_index=row_index)
        except httpx.TimeoutException as exc:
            raise HighApiError(
                f"Instrument list download timed out after {effective_timeout_ms}ms", status=0, body=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise HighApiError(f"Instrument list download failed: {exc}", status=0, body=exc) from exc

    def list(
        self,
        category: InstrumentCategory = "all",
        *,
        timeout_ms: Optional[float] = None,
        cancel_event=None,
    ) -> List[InstrumentRow]:
        """The eager form: materialises the whole category into a list. For
        ``all`` (14 MB) or ``derivatives`` (11 MB) prefer :meth:`stream`."""
        return list(self.stream(category, timeout_ms=timeout_ms, cancel_event=cancel_event))


class AsyncInstrumentsResource:
    def __init__(self, client: httpx.AsyncClient, config: ResolvedConfig) -> None:
        self._client = client
        self._config = config
        self._manifest: Optional[InstrumentsManifest] = None

    async def _manifest_for(self, *, timeout_ms: Optional[float]) -> InstrumentsManifest:
        if self._manifest is None:
            data = await http_async.send_request(
                self._client, self._config, method="GET", path="/instruments", auth="none", timeout_ms=timeout_ms,
            )
            self._manifest = _parse_manifest(data)
        return self._manifest

    async def stream(
        self,
        category: InstrumentCategory = "all",
        *,
        timeout_ms: Optional[float] = None,
    ) -> AsyncIterator[InstrumentRow]:
        """The primary form — an async generator. Nothing is fetched until
        this is iterated (``async for`` / ``anext``)."""
        manifest = await self._manifest_for(timeout_ms=timeout_ms)
        file = _select_file(manifest, category)
        url = str(file.url)
        _validate_download_url(url, self._config)

        headers = _download_headers(self._config)
        effective_timeout_ms = timeout_ms if timeout_ms is not None else self._config.timeout_ms
        self._config.logger.info(f"HIGH GET {redact_url(url)}")

        try:
            async with self._client.stream(
                "GET", url, headers=headers, timeout=httpx.Timeout(effective_timeout_ms / 1000),
            ) as response:
                if not response.is_success:
                    text = (await response.aread()).decode("utf-8", errors="replace")
                    raise error_from_response(response.status_code, None, text)

                header: Optional[List[str]] = None
                row_index = 0
                async for line in response.aiter_lines():
                    if line == "":
                        continue
                    parsed = next(csv.reader([line]))
                    if header is None:
                        header = parsed
                        if header != list(manifest.columns):
                            raise HighApiError(
                                f"The instrument list CSV header for category {category!r} does not match "
                                f"the manifest's columns. Expected {list(manifest.columns)!r}, got {header!r}.",
                                status=0,
                            )
                        continue
                    yield _row_from_values(header, parsed, category=category, row_index=row_index)
                    row_index += 1

                if header is None:
                    raise HighApiError(f"The instrument list for category {category!r} was empty.", status=0)
        except httpx.TimeoutException as exc:
            raise HighApiError(
                f"Instrument list download timed out after {effective_timeout_ms}ms", status=0, body=exc,
            ) from exc
        except httpx.HTTPError as exc:
            raise HighApiError(f"Instrument list download failed: {exc}", status=0, body=exc) from exc

    async def list(
        self,
        category: InstrumentCategory = "all",
        *,
        timeout_ms: Optional[float] = None,
    ) -> List[InstrumentRow]:
        """The eager form: materialises the whole category into a list. For
        ``all`` (14 MB) or ``derivatives`` (11 MB) prefer :meth:`stream`."""
        return [row async for row in self.stream(category, timeout_ms=timeout_ms)]
