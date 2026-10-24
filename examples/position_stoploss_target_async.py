# Copyright (c) 2026 Truestock
# SPDX-License-Identifier: MIT

"""Runnable example for placing a stop-loss and a target on an open position,
async client.

    HIGH_ENVIRONMENT=sandbox HIGH_API_KEY=... HIGH_ACCESS_TOKEN=... python examples/position_stoploss_target_async.py

Read before running:

- This places REAL exit orders on the position named below. Confirm the
  symbol, flavor, productType and prices, and confirm before running against
  production (HIGH_ENVIRONMENT=production, the default). The prices below are
  placeholders: the stop-loss trigger must sit below LTP for a long position
  (above it for a short), and the target must sit above LTP for a long
  (below it for a short).
- Both calls require a static IP registered with HIGH.
- Both are PATCH requests and are never retried by the SDK. If a call fails
  with a transport error or timeout, check the order book before sending it
  again, or you may end up with a duplicate exit order.
"""

from __future__ import annotations

import asyncio

from high_openapi import AsyncHighClient, HighApiError

# The open position to protect. flavor and productType must match what
# GET /portfolio/positions reports for it.
POSITION = {
    "tradingSymbol": "RELIANCE-EQ",
    "flavor": "REGULAR",
    "productType": "INTRADAY",
}
STOPLOSS_TRIGGER_PRICE = 2400
TARGET_PRICE = 2600


async def main() -> None:
    async with AsyncHighClient() as high:  # picks up HIGH_* environment variables
        try:
            # Sequential on purpose: each exit is a separate order, and a failure
            # on the stop-loss should stop the target from being placed.
            stoploss = await high.portfolio.set_stoploss({**POSITION, "triggerPrice": STOPLOSS_TRIGGER_PRICE})
            print(f"stop-loss: action={stoploss.action.value} orderId={stoploss.orderId} "
                  f"triggerPrice={stoploss.price} limitPrice={stoploss.limitPrice} quantity={stoploss.quantity}")

            target = await high.portfolio.set_target({**POSITION, "targetPrice": TARGET_PRICE})
            print(f"target: action={target.action.value} orderId={target.orderId} "
                  f"targetPrice={target.price} quantity={target.quantity}")
        except HighApiError as error:
            print(f"HIGH API error: status={error.status} code={error.code} request_id={error.request_id}")
            raise


if __name__ == "__main__":
    asyncio.run(main())
