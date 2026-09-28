# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Runnable quickstart for the async client.

    HIGH_ENVIRONMENT=sandbox HIGH_API_KEY=... HIGH_ACCESS_TOKEN=... python examples/quickstart_async.py
"""

from __future__ import annotations

import asyncio

from high_openapi import AsyncHighClient, HighApiError


async def main() -> None:
    async with AsyncHighClient() as high:  # picks up HIGH_* environment variables
        try:
            funds = await high.portfolio.funds()
        except HighApiError as error:
            print(f"HIGH API error: status={error.status} code={error.code} request_id={error.request_id}")
            raise

        print(f"Available balance: {funds.availableBalance}")

        quotes, status = await asyncio.gather(
            high.scrips.quotes({"symbols": ["RELIANCE-EQ"]}),
            high.market.status(),
        )
        reliance = quotes.get("RELIANCE-EQ")
        if reliance is not None:
            print(f"RELIANCE-EQ LTP: {reliance.LTP}")
        print(f"Market status: {status.exchangeStatus}")


if __name__ == "__main__":
    asyncio.run(main())
