# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Runnable example for the instrument list.

    python examples/instruments.py

Unlike the other examples, this needs no credentials at all — neither
HIGH_API_KEY nor HIGH_ACCESS_TOKEN — so it works with a bare HighClient().
"""

from __future__ import annotations

from high_openapi import HighApiError, HighClient


def main() -> None:
    with HighClient() as high:
        try:
            printed = 0
            for row in high.instruments.stream("equity"):
                print(f"{row.high_trading_symbol:<20} {row.symbol:<12} lot={row.lot_size}")
                printed += 1
                if printed >= 5:
                    break
        except HighApiError as error:
            print(f"HIGH API error: status={error.status} code={error.code} request_id={error.request_id}")
            raise

        # The eager form, for when you want every row in memory at once —
        # fine for the smaller categories, best avoided for "all"/"derivatives".
        etfs = high.instruments.list("etfs")
        print(f"\n{len(etfs)} ETFs in total; first one: {etfs[0].high_trading_symbol if etfs else 'none'}")


if __name__ == "__main__":
    main()
