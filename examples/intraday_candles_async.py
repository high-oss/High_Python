# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Runnable example for intraday candles, async client.

    HIGH_ENVIRONMENT=sandbox HIGH_API_KEY=... HIGH_ACCESS_TOKEN=... python examples/intraday_candles_async.py

Both forms of the instrument reference are shown: tradingSymbol, and
exchangeSegment + scripCode. Needs the market data plan on your HIGH account.
The request is a POST, so it is never retried by the SDK.
"""

from __future__ import annotations

import asyncio

from high_openapi import AsyncHighClient, HighApiError


async def main() -> None:
    async with AsyncHighClient() as high:  # picks up HIGH_* environment variables
        try:
            by_symbol, by_code = await asyncio.gather(
                high.scrips.intraday({"tradingSymbol": "RELIANCE-EQ", "interval": "5m"}),
                high.scrips.intraday({"exchangeSegment": "NSE", "scripCode": "2885", "interval": "1h"}),
            )
        except HighApiError as error:
            print(f"HIGH API error: status={error.status} code={error.code} request_id={error.request_id}")
            raise

        for label, candles in (("by tradingSymbol", by_symbol), ("by exchangeSegment + scripCode", by_code)):
            print(f"{label}: {candles.tradingSymbol} interval={candles.interval} candles={len(candles.timestamp)}")
            if candles.timestamp:
                last = len(candles.timestamp) - 1  # index i across the arrays is one candle
                print(f"  last candle ts={candles.timestamp[last]} C={candles.close[last]} V={candles.volume[last]}")


if __name__ == "__main__":
    asyncio.run(main())
