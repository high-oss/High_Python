# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Runnable example for intraday candles: the most recent trading session.

    HIGH_ENVIRONMENT=sandbox HIGH_API_KEY=... HIGH_ACCESS_TOKEN=... python examples/intraday_candles.py

The instrument is named either by tradingSymbol, or by exchangeSegment +
scripCode. Both forms are shown below; each call uses one of them.

Needs the market data plan on your HIGH account. The request is a POST, so
it is never retried by the SDK.
"""

from __future__ import annotations

from high_openapi import HighApiError, HighClient


def print_candles(label: str, candles) -> None:
    # Columnar: index i across the arrays is one candle.
    print(f"{label}: {candles.tradingSymbol} interval={candles.interval} candles={len(candles.timestamp)}")
    for i in range(max(0, len(candles.timestamp) - 3), len(candles.timestamp)):
        print(f"  ts={candles.timestamp[i]} O={candles.open[i]} H={candles.high[i]} "
              f"L={candles.low[i]} C={candles.close[i]} V={candles.volume[i]}")


def main() -> None:
    with HighClient() as high:  # picks up HIGH_* environment variables
        try:
            # Form 1: by trading symbol.
            by_symbol = high.scrips.intraday({"tradingSymbol": "RELIANCE-EQ", "interval": "5m"})
            print_candles("by tradingSymbol", by_symbol)

            # Form 2: by exchange segment and scrip code (Reliance, NSE token 2885).
            by_code = high.scrips.intraday({"exchangeSegment": "NSE", "scripCode": "2885", "interval": "1h"})
            print_candles("by exchangeSegment + scripCode", by_code)
        except HighApiError as error:
            print(f"HIGH API error: status={error.status} code={error.code} request_id={error.request_id}")
            raise


if __name__ == "__main__":
    main()
